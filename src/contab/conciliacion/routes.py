"""Define las rutas web de conciliación bancaria."""

from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from contab.models import (
    MovimientoBancario,
    MovimientoPrevisto,
)
from contab.conciliacion.importacion import (
    ImportacionBancariaError,
    leer_csv_bancario,
    preparar_movimientos_bancarios,
)
from contab.conciliacion.services import (
    ConciliacionError,
    descartar_movimiento_bancario,
    restaurar_movimiento_bancario,
)
from contab.context import (
    get_bank_name,
    get_database_name,
    get_session_factory,
)



bp = Blueprint(
    "conciliacion",
    __name__,
    url_prefix="/conciliacion",
    template_folder="templates",
)

ESTADOS_MOVIMIENTO = {
    "PENDIENTE": "Pendiente",
    "CONCILIADO": "Conciliado",
    "DESCARTADO": "Descartado",
}

NATURALEZAS_MOVIMIENTO = {
    "INGRESO": "Ingreso",
    "GASTO": "Gasto",
}

ESTADOS_MOVIMIENTO_PREVISTO = {
    "PENDIENTE": "Pendiente",
    "PARCIAL": "Parcial",
    "CONCILIADO": "Conciliado",
    "CANCELADO": "Cancelado",
}



def _intervalo_a_texto(
    movimiento: MovimientoPrevisto,
) -> str:
    """Muestra de forma legible el intervalo previsto."""

    desde = movimiento.fecha_prevista_desde
    hasta = movimiento.fecha_prevista_hasta

    if desde is None:
        return "Sin fecha prevista"

    desde_texto = desde.strftime("%d/%m/%Y")

    if hasta is None:
        return f"Desde {desde_texto}"

    if hasta == desde:
        return desde_texto

    return (
        f"{desde_texto} a "
        f"{hasta.strftime('%d/%m/%Y')}"
    )


def _estado_retorno() -> str:
    """Obtiene un filtro válido al que regresar."""

    estado = request.form.get(
        "estado",
        "PENDIENTE",
    ).strip().upper()

    if estado not in {
        "TODOS",
        *ESTADOS_MOVIMIENTO,
    }:
        return "PENDIENTE"

    return estado


def _importe_a_texto(importe: int) -> str:
    """Convierte un importe en céntimos a texto en euros."""

    euros, centimos = divmod(importe, 100)

    euros_texto = f"{euros:,}".replace(",", ".")

    return f"{euros_texto},{centimos:02d}"


def _render_formulario_importacion(
    *,
    error: str | None = None,
    resultado: str | None = None,
):
    """Muestra el formulario con todo su contexto."""

    return render_template(
        "conciliacion/importar.html",
        banco=get_bank_name(),
        error=error,
        resultado=resultado,
        database_name=get_database_name(),
    )



@bp.get("/")
def listar_movimientos():
    """Muestra los movimientos bancarios ordenados y paginados."""

    estado = request.args.get(
        "estado",
        default="PENDIENTE",
    ).strip().upper()

    estados_validos = {
        "TODOS",
        *ESTADOS_MOVIMIENTO,
    }

    if estado not in estados_validos:
        estado = "PENDIENTE"

    pagina = request.args.get(
        "pagina",
        default=1,
        type=int,
    )
    pagina = max(pagina, 1)
    por_pagina = 25

    session_factory = get_session_factory()

    with session_factory() as session:
        consulta_total = select(
            func.count(MovimientoBancario.id)
        )

        consulta_movimientos = select(
            MovimientoBancario
        )

        if estado != "TODOS":
            consulta_total = consulta_total.where(
                MovimientoBancario.estado == estado
            )
            consulta_movimientos = (
                consulta_movimientos.where(
                    MovimientoBancario.estado == estado
                )
            )

        total = session.scalar(
            consulta_total
        ) or 0

        total_paginas = max(
            1,
            (
                total
                + por_pagina
                - 1
            ) // por_pagina,
        )

        pagina = min(
            pagina,
            total_paginas,
        )

        movimientos = session.scalars(
            consulta_movimientos
            .order_by(
                MovimientoBancario.fecha.desc(),
                MovimientoBancario.id.desc(),
            )
            .offset(
                (pagina - 1) * por_pagina
            )
            .limit(por_pagina)
        ).all()

        return render_template(
            "conciliacion/movimientos_bancarios.html",
            movimientos=movimientos,
            pagina=pagina,
            total_paginas=total_paginas,
            estados=ESTADOS_MOVIMIENTO,
            naturalezas=NATURALEZAS_MOVIMIENTO,
            importe_a_texto=_importe_a_texto,
            database_name=get_database_name(),
            estado_seleccionado=estado,
        )




@bp.route("/importar", methods=["GET", "POST"])
def importar_movimientos():
    """Importa los movimientos del banco configurado."""

    if request.method == "GET":
        return _render_formulario_importacion()

    archivo = request.files.get("archivo")

    if archivo is None or not archivo.filename:
        return (
            _render_formulario_importacion(
                error="Debe seleccionar un archivo CSV.",
            ),
            400,
        )

    try:
        contenido = archivo.read().decode(
            "utf-8-sig"
        )

        importados = leer_csv_bancario(
            banco=get_bank_name(),
            contenido=contenido,
        )

    except UnicodeDecodeError:
        return (
            _render_formulario_importacion(
                error=(
                    "El archivo CSV no está codificado "
                    "en UTF-8."
                ),
            ),
            400,
        )

    except ImportacionBancariaError as exc:
        return (
            _render_formulario_importacion(
                error=str(exc),
            ),
            400,
        )

    session_factory = get_session_factory()

    with session_factory() as session:
        with session.begin():
            nuevos = preparar_movimientos_bancarios(
                session=session,
                movimientos=importados,
            )

            session.add_all(nuevos)

    existentes = len(importados) - len(nuevos)

    resultado = (
        f"Movimientos importados: {len(nuevos)}. "
        f"Ya existentes: {existentes}."
    )

    return _render_formulario_importacion(
        resultado=resultado,
    )


@bp.post("/movimientos/<int:movimiento_id>/descartar")
def descartar_movimiento(movimiento_id: int):
    """Marca como ajeno a Contab un movimiento pendiente."""

    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            with session.begin():
                movimiento = session.get(
                    MovimientoBancario,
                    movimiento_id,
                )

                if movimiento is None:
                    return (
                        "Movimiento bancario no encontrado.",
                        404,
                    )

                descartar_movimiento_bancario(
                    movimiento
                )

    except ConciliacionError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "conciliacion.listar_movimientos",
            estado=_estado_retorno(),
        )
    )


@bp.post("/movimientos/<int:movimiento_id>/restaurar")
def restaurar_movimiento(movimiento_id: int):
    """Devuelve a pendiente un movimiento descartado."""

    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            with session.begin():
                movimiento = session.get(
                    MovimientoBancario,
                    movimiento_id,
                )

                if movimiento is None:
                    return (
                        "Movimiento bancario no encontrado.",
                        404,
                    )

                restaurar_movimiento_bancario(
                    movimiento
                )

    except ConciliacionError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "conciliacion.listar_movimientos",
            estado=_estado_retorno(),
        )
    )


@bp.get("/previstos")
def listar_movimientos_previstos():
    """Muestra los movimientos previstos ordenados y paginados."""

    estado = request.args.get(
        "estado",
        default="PENDIENTE",
    ).strip().upper()

    estados_validos = {
        "TODOS",
        *ESTADOS_MOVIMIENTO_PREVISTO,
    }

    if estado not in estados_validos:
        estado = "PENDIENTE"

    pagina = request.args.get(
        "pagina",
        default=1,
        type=int,
    )
    pagina = max(pagina, 1)
    por_pagina = 25

    consulta_total = select(
        func.count(MovimientoPrevisto.id)
    )
    consulta_movimientos = select(
        MovimientoPrevisto
    ).options(
        joinedload(MovimientoPrevisto.inmueble)
    )

    if estado != "TODOS":
        consulta_total = consulta_total.where(
            MovimientoPrevisto.estado == estado
        )
        consulta_movimientos = (
            consulta_movimientos.where(
                MovimientoPrevisto.estado == estado
            )
        )

    session_factory = get_session_factory()

    with session_factory() as session:
        total = session.scalar(
            consulta_total
        ) or 0

        total_paginas = max(
            1,
            (
                total
                + por_pagina
                - 1
            ) // por_pagina,
        )
        pagina = min(
            pagina,
            total_paginas,
        )

        movimientos = session.scalars(
            consulta_movimientos
            .order_by(
                MovimientoPrevisto.fecha_prevista_desde.desc(),
                MovimientoPrevisto.id.desc(),
            )
            .offset(
                (pagina - 1) * por_pagina
            )
            .limit(por_pagina)
        ).all()

        return render_template(
            "conciliacion/movimientos_previstos.html",
            movimientos=movimientos,
            pagina=pagina,
            total_paginas=total_paginas,
            estado_seleccionado=estado,
            estados=ESTADOS_MOVIMIENTO_PREVISTO,
            naturalezas=NATURALEZAS_MOVIMIENTO,
            importe_a_texto=_importe_a_texto,
            intervalo_a_texto=_intervalo_a_texto,
            database_name=get_database_name(),
        )



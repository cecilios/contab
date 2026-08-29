"""Define las rutas web para consultar y mantener apuntes contables."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from contab.context import (
    get_database_name,
    get_session_factory,
)
from contab.models import ApunteContable, Inmueble

from contab.config import (
    cargar_categorias_contables,
    categorias_contables_activas,
)
from contab.contabilidad.services import (
    ContabilidadError,
    crear_apunte_contable,
    eliminar_apunte_contable,
    modificar_apunte_contable,
)
from contab.conciliacion.services import (
    ConciliacionError,
    crear_movimiento_desde_apunte,
)


bp = Blueprint(
    "contabilidad",
    __name__,
    url_prefix="/contabilidad",
    template_folder="templates",
)


def _importe_a_texto(importe: int) -> str:
    """Convierte un importe en céntimos a texto."""

    euros, centimos = divmod(importe, 100)

    return f"{euros},{centimos:02d} €"


def _fecha(texto: str) -> date:
    """Convierte una fecha dd/mm/aaaa."""

    try:
        return datetime.strptime(
            texto.strip(),
            "%d/%m/%Y",
        ).date()
    except ValueError as exc:
        raise ValueError(
            "La fecha indicada no es válida o no tiene "
            "el formato dd/mm/aaaa."
        ) from exc


def _importe_a_centimos(texto: str) -> int:
    """Convierte un importe escrito en euros a céntimos."""

    texto = texto.strip().replace(",", ".")

    try:
        importe = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(
            "El importe indicado no es válido."
        ) from exc

    return int(
        (importe * 100).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def _separar_clasificacion(
    texto: str,
    categorias,
) -> tuple[str, str, str]:
    """Obtiene naturaleza, categoría y subcategoría."""

    partes = texto.strip().upper().split(".", maxsplit=1)
    categoria_codigo = partes[0]

    categoria = categorias.get(categoria_codigo)

    if categoria is None:
        raise ValueError(
            "La clasificación contable indicada no es válida."
        )

    subcategoria = (
        partes[1]
        if len(partes) == 2
        else ""
    )

    return (
        categoria.naturaleza,
        categoria_codigo,
        subcategoria,
    )


def _mostrar_formulario_apunte(
    *,
    titulo: str,
    datos,
    error: str | None,
    status_code: int = 200,
    permitir_movimiento: bool = False,
):
    """Muestra el formulario con sus opciones."""

    categorias = categorias_contables_activas(
        cargar_categorias_contables()
    )

    session_factory = get_session_factory()

    with session_factory() as session:
        inmuebles = session.scalars(
            select(Inmueble)
            .where(Inmueble.activo.is_(True))
            .order_by(Inmueble.referencia)
        ).all()

        contenido = render_template(
            "contabilidad/formulario.html",
            titulo=titulo,
            datos=datos,
            categorias=categorias,
            inmuebles=inmuebles,
            error=error,
            database_name=get_database_name(),
            permitir_movimiento=permitir_movimiento,
        )

    return contenido, status_code


def _importe_para_formulario(importe: int) -> str:
    """Convierte céntimos al formato utilizado en formularios."""

    euros, centimos = divmod(importe, 100)

    return f"{euros},{centimos:02d}"


def _datos_apunte_formulario(
    datos,
    categorias,
) -> tuple[int, dict]:
    """Interpreta y normaliza los datos enviados por el formulario."""

    inmueble_id = int(datos["inmueble_id"])
    fecha = _fecha(datos["fecha"])

    (
        naturaleza,
        categoria,
        subcategoria,
    ) = _separar_clasificacion(
        datos["clasificacion"],
        categorias,
    )

    valores = {
        "categorias": categorias,
        "fecha": fecha,
        "naturaleza": naturaleza,
        "categoria": categoria,
        "subcategoria": subcategoria,
        "concepto": datos["concepto"],
        "base": _importe_a_centimos(datos["base"]),
        "iva_importe": _importe_a_centimos(
            datos["iva_importe"]
        ),
        "retencion_importe": _importe_a_centimos(
            datos["retencion_importe"]
        ),
        "tercero_nombre": datos["tercero_nombre"],
        "tercero_nif": datos["tercero_nif"],
        "referencia_documento": datos[
            "referencia_documento"
        ],
        "ruta_documento": datos["ruta_documento"],
        "notas": datos["notas"],
    }

    return inmueble_id, valores





@bp.get("/")
def listar_apuntes():
    """Muestra los apuntes contables ordenados por fecha."""

    session_factory = get_session_factory()

    with session_factory() as session:
        apuntes = session.scalars(
            select(ApunteContable)
            .options(
                joinedload(ApunteContable.inmueble)
            )
            .order_by(
                ApunteContable.fecha.desc(),
                ApunteContable.id.desc(),
            )
        ).all()

        return render_template(
            "contabilidad/lista.html",
            apuntes=apuntes,
            importe_a_texto=_importe_a_texto,
            database_name=get_database_name(),
        )


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo_apunte():
    """Permite crear un apunte contable."""

    if request.method == "GET":
        contenido, _ = _mostrar_formulario_apunte(
            titulo="Nuevo apunte contable",
            datos={
                "fecha": date.today().strftime("%d/%m/%Y"),
            },
            error=None,
            permitir_movimiento=True,
        )

        return contenido

    categorias = cargar_categorias_contables()

    try:
        inmueble_id, valores = _datos_apunte_formulario(
            request.form,
            categorias,
        )

        crear_movimiento = (
            "crear_movimiento" in request.form
        )

        fecha_prevista = (
            _fecha(request.form["fecha_prevista"])
            if crear_movimiento
            else None
        )

        session_factory = get_session_factory()

        with session_factory() as session:
            with session.begin():
                inmueble = session.get(
                    Inmueble,
                    inmueble_id,
                )

                if inmueble is None:
                    raise ValueError(
                        "El inmueble seleccionado no existe."
                    )

                apunte = crear_apunte_contable(
                    inmueble=inmueble,
                    **valores,
                )

                session.add(apunte)

                if fecha_prevista is not None:
                    movimiento = (
                        crear_movimiento_desde_apunte(
                            apunte=apunte,
                            fecha_prevista=fecha_prevista,
                        )
                    )

                    session.add(movimiento)

    except (
        KeyError,
        ValueError,
        ContabilidadError,
        ConciliacionError,
    ) as exc:
        return _mostrar_formulario_apunte(
            titulo="Nuevo apunte contable",
            datos=request.form,
            error=str(exc),
            status_code=400,
            permitir_movimiento=True,
        )

    return redirect(
        url_for("contabilidad.listar_apuntes")
    )


@bp.route(
    "/<int:apunte_id>/editar",
    methods=["GET", "POST"],
)
def editar_apunte(apunte_id: int):
    """Permite modificar un apunte contable."""

    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            apunte = session.get(
                ApunteContable,
                apunte_id,
            )

            if apunte is None:
                return "Apunte contable no encontrado.", 404

            clasificacion = apunte.categoria

            if apunte.subcategoria:
                clasificacion += (
                    f".{apunte.subcategoria}"
                )

            hoy = date.today().strftime("%d/%m/%Y")

            datos={
                "fecha": hoy,
                "crear_movimiento": True,
                "fecha_prevista": hoy,
                "inmueble_id": str(apunte.inmueble_id),
                "fecha": apunte.fecha.strftime("%d/%m/%Y"),
                "clasificacion": clasificacion,
                "concepto": apunte.concepto,
                "base": _importe_para_formulario(
                    apunte.base
                ),
                "iva_importe": _importe_para_formulario(
                    apunte.iva_importe
                ),
                "retencion_importe": (
                    _importe_para_formulario(
                        apunte.retencion_importe
                    )
                ),
                "tercero_nombre": apunte.tercero_nombre,
                "tercero_nif": apunte.tercero_nif,
                "referencia_documento": (
                    apunte.referencia_documento
                ),
                "ruta_documento": apunte.ruta_documento,
                "notas": apunte.notas or "",
            }

        contenido, _ = _mostrar_formulario_apunte(
            titulo="Editar apunte contable",
            datos=datos,
            error=None,
        )

        return contenido

    categorias = cargar_categorias_contables()

    try:
        inmueble_id, valores = _datos_apunte_formulario(
            request.form,
            categorias,
        )

        with session_factory() as session:
            with session.begin():
                apunte = session.get(
                    ApunteContable,
                    apunte_id,
                )

                if apunte is None:
                    return (
                        "Apunte contable no encontrado.",
                        404,
                    )

                inmueble = session.get(
                    Inmueble,
                    inmueble_id,
                )

                if inmueble is None:
                    raise ValueError(
                        "El inmueble seleccionado no existe."
                    )

                modificar_apunte_contable(
                    apunte=apunte,
                    inmueble=inmueble,
                    **valores,
                )

    except (KeyError, ValueError, ContabilidadError) as exc:
        return _mostrar_formulario_apunte(
            titulo="Editar apunte contable",
            datos=request.form,
            error=str(exc),
            status_code=400,
        )

    return redirect(
        url_for("contabilidad.listar_apuntes")
    )


@bp.route(
    "/<int:apunte_id>/eliminar",
    methods=["GET", "POST"],
)
def eliminar_apunte(apunte_id: int):
    """Solicita confirmación y elimina un apunte."""

    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            apunte = session.get(
                ApunteContable,
                apunte_id,
            )

            if apunte is None:
                return "Apunte contable no encontrado.", 404

            movimientos_pendientes = sum(
                movimiento.estado == "PENDIENTE"
                for movimiento in apunte.movimientos_previstos
            )

            tiene_conciliados = any(
                movimiento.estado == "CONCILIADO"
                for movimiento in apunte.movimientos_previstos
            )

            return render_template(
                "contabilidad/eliminar.html",
                apunte=apunte,
                movimientos_pendientes=movimientos_pendientes,
                tiene_conciliados=tiene_conciliados,
                error=None,
                database_name=get_database_name(),
            )

    try:
        with session_factory() as session:
            with session.begin():
                apunte = session.get(
                    ApunteContable,
                    apunte_id,
                )

                if apunte is None:
                    return (
                        "Apunte contable no encontrado.",
                        404,
                    )

                eliminar_apunte_contable(
                    session,
                    apunte,
                )

    except ContabilidadError as exc:
        with session_factory() as session:
            apunte = session.get(
                ApunteContable,
                apunte_id,
            )

            if apunte is None:
                return "Apunte contable no encontrado.", 404

            movimientos_pendientes = sum(
                movimiento.estado == "PENDIENTE"
                for movimiento in apunte.movimientos_previstos
            )

            return (
                render_template(
                    "contabilidad/eliminar.html",
                    apunte=apunte,
                    movimientos_pendientes=movimientos_pendientes,
                    tiene_conciliados=True,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )

    return redirect(
        url_for("contabilidad.listar_apuntes")
    )




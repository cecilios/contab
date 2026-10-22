"""Define las rutas web de conciliación bancaria."""

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from contab.formato import (
    fecha_a_texto,
    importe_a_texto,
    texto_a_fecha,
)
from contab.models import (
    Conciliacion,
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
    PropuestaConciliacion,
    buscar_propuestas_conciliacion,
    cancelar_movimiento_previsto,
    clasificar_movimientos_bancarios,
    conciliar_movimiento_previsto_manualmente,
    confirmar_conciliacion,
    confirmar_grupo_conciliacion,
    confirmar_propuesta_conciliacion,
    descartar_movimiento_bancario,
    deshacer_asociacion_bancaria,
    deshacer_conciliacion_manual,
    diagnosticar_emparejamiento,
    diagnosticar_grupo_conciliacion,
    preparar_asociaciones_cronologicas,
    restaurar_movimiento_bancario,
    restaurar_movimiento_previsto,
    saldo_movimiento_bancario,
    saldo_movimiento_previsto,
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




def _rechazos_revision() -> tuple[set[int], set[int]]:
    """Obtiene los movimientos excluidos de propuestas en esta sesión."""

    database_name = get_database_name()

    rechazos = session.get(
        "conciliacion_revision_rechazos",
        {},
    ).get(database_name, {})

    return (
        set(rechazos.get("bancarios", [])),
        set(rechazos.get("previstos", [])),
    )


def _guardar_rechazos_revision(
    bancario_ids: set[int],
    previsto_ids: set[int],
) -> None:
    """Conserva los rechazos para la base de datos activa."""

    database_name = get_database_name()

    rechazos = dict(
        session.get("conciliacion_revision_rechazos", {})
    )

    rechazos[database_name] = {
        "bancarios": sorted(bancario_ids),
        "previstos": sorted(previsto_ids),
    }

    session["conciliacion_revision_rechazos"] = rechazos


def _intervalo_a_texto(
    movimiento: MovimientoPrevisto,
) -> str:
    """Muestra de forma legible el intervalo previsto."""

    desde = movimiento.fecha_prevista_desde
    hasta = movimiento.fecha_prevista_hasta

    if desde is None:
        return "Sin fecha prevista"

    desde_texto = fecha_a_texto(desde)

    if hasta is None:
        return f"Desde {desde_texto}"

    if hasta == desde:
        return desde_texto

    return (
        f"{desde_texto} a "
        f"{fecha_a_texto(hasta)}"
    )


def _estado_bancario_retorno() -> str:
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


def _estado_previsto_retorno() -> str:
    """Obtiene un filtro válido de movimientos previstos al que regresar."""

    estado = request.form.get(
        "estado",
        "PENDIENTE",
    ).strip().upper()

    if estado not in {
        "TODOS",
        *ESTADOS_MOVIMIENTO_PREVISTO,
    }:
        return "PENDIENTE"

    return estado


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


def _obtener_revision_conciliacion(db_session):
    """Carga movimientos y calcula propuestas respetando los rechazos."""

    database_name = get_database_name()

    aliases_por_base = current_app.extensions.get(
        "contab_alias_conciliacion",
        {},
    )
    aliases_configurados = aliases_por_base.get(
        database_name,
        [],
    )

    movimientos_bancarios = db_session.scalars(
        select(MovimientoBancario)
        .where(
            MovimientoBancario.estado.in_(
                ("PENDIENTE", "PARCIAL")
            )
        )
        .order_by(
            MovimientoBancario.fecha.desc(),
            MovimientoBancario.id.desc(),
        )
    ).all()

    movimientos_previstos = db_session.scalars(
        select(MovimientoPrevisto)
        .options(
            joinedload(MovimientoPrevisto.inmueble)
        )
        .where(
            MovimientoPrevisto.estado.in_(
                ("PENDIENTE", "PARCIAL")
            )
        )
        .order_by(
            MovimientoPrevisto.fecha_prevista_desde,
            MovimientoPrevisto.id,
        )
    ).all()

    (
        bancario_ids_rechazados,
        previsto_ids_rechazados,
    ) = _rechazos_revision()

    bancarios_para_propuestas = [
        bancario
        for bancario in movimientos_bancarios
        if bancario.id not in bancario_ids_rechazados
    ]

    previstos_para_propuestas = [
        previsto
        for previsto in movimientos_previstos
        if previsto.id not in previsto_ids_rechazados
    ]

    propuestas = buscar_propuestas_conciliacion(
        bancarios_para_propuestas,
        previstos_para_propuestas,
        aliases_configurados=aliases_configurados,
    )

    return (
        movimientos_bancarios,
        movimientos_previstos,
        propuestas,
    )


@bp.get("/revisar")
def revisar_conciliacion():
    """Muestra propuestas automáticas y movimientos para revisión manual."""

    database_name = get_database_name()
    session_factory = get_session_factory()

    with session_factory() as db_session:
        (
            movimientos_bancarios,
            movimientos_previstos,
            propuestas,
        ) = _obtener_revision_conciliacion(db_session)

        ids_bancarios_propuestos = {
            bancario.id
            for propuesta in propuestas
            for bancario in propuesta.bancarios
        }

        ids_previstos_propuestos = {
            previsto.id
            for propuesta in propuestas
            for previsto in propuesta.previstos
        }

        bancarios_sin_propuesta = [
            bancario
            for bancario in movimientos_bancarios
            if bancario.id not in ids_bancarios_propuestos
        ]

        previstos_sin_propuesta = [
            previsto
            for previsto in movimientos_previstos
            if previsto.id not in ids_previstos_propuestos
        ]

        return render_template(
            "conciliacion/revisar.html",
            propuestas=propuestas,
            bancarios_sin_propuesta=bancarios_sin_propuesta,
            previstos_sin_propuesta=previstos_sin_propuesta,
            importe_a_texto=importe_a_texto,
            intervalo_a_texto=_intervalo_a_texto,
            saldo_movimiento_bancario=saldo_movimiento_bancario,
            saldo_movimiento_previsto=saldo_movimiento_previsto,
            database_name=database_name,
            debug_conciliacion=current_app.config.get("CONTAB_DEBUG_CONCILIACION", False),
        )


@bp.get("/")
def listar_movimientos_bancarios():
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
            importe_a_texto=importe_a_texto,
            database_name=get_database_name(),
            estado_seleccionado=estado,
        )




@bp.route("/importar", methods=["GET", "POST"])
def importar_movimientos_bancarios():
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
def descartar_movimiento_bancario_desde_interfaz(movimiento_id: int):
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


    if request.form.get("origen") == "revision":
        return redirect(
            url_for(
                "conciliacion.revisar_conciliacion"
            )
        )

    return redirect(
        url_for(
            "conciliacion.listar_movimientos_bancarios",
            estado=_estado_bancario_retorno(),
        )
    )


@bp.post("/movimientos/<int:movimiento_id>/restaurar")
def restaurar_movimiento_bancario_desde_interfaz(movimiento_id: int):
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
            "conciliacion.listar_movimientos_bancarios",
            estado=_estado_bancario_retorno(),
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
            importe_a_texto=importe_a_texto,
            intervalo_a_texto=_intervalo_a_texto,
            database_name=get_database_name(),
        )


@bp.post("/previstos/<int:movimiento_id>/cancelar")
def cancelar_movimiento_previsto_desde_interfaz(
    movimiento_id: int,
):
    """Cancela un movimiento previsto todavía pendiente."""

    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            with session.begin():
                movimiento = session.get(
                    MovimientoPrevisto,
                    movimiento_id,
                )

                if movimiento is None:
                    return (
                        "Movimiento previsto no encontrado.",
                        404,
                    )

                cancelar_movimiento_previsto(
                    movimiento
                )

    except ConciliacionError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "conciliacion.listar_movimientos_previstos",
            estado=_estado_previsto_retorno(),
        )
    )


@bp.post("/previstos/<int:movimiento_id>/restaurar")
def restaurar_movimiento_previsto_desde_interfaz(
    movimiento_id: int,
):
    """Devuelve a pendiente un movimiento previsto cancelado."""

    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            with session.begin():
                movimiento = session.get(
                    MovimientoPrevisto,
                    movimiento_id,
                )

                if movimiento is None:
                    return (
                        "Movimiento previsto no encontrado.",
                        404,
                    )

                restaurar_movimiento_previsto(
                    movimiento
                )

    except ConciliacionError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "conciliacion.listar_movimientos_previstos",
            estado=_estado_previsto_retorno(),
        )
    )


@bp.route(
    "/previstos/<int:movimiento_id>/conciliar-manualmente",
    methods=["GET", "POST"],
)
def conciliar_movimiento_previsto_manualmente_desde_interfaz(
    movimiento_id: int,
):
    """Muestra y procesa la conciliación manual de un movimiento previsto."""

    session_factory = get_session_factory()

    with session_factory() as session:
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        if movimiento is None:
            return (
                "Movimiento previsto no encontrado.",
                404,
            )

        if request.method == "GET":
            return render_template(
                "conciliacion/conciliar_manualmente.html",
                movimiento=movimiento,
                importe_a_texto=importe_a_texto,
                intervalo_a_texto=_intervalo_a_texto,
                database_name=get_database_name(),
            )

        try:
            conciliar_movimiento_previsto_manualmente(
                movimiento,
                request.form.get("notas", ""),
            )
            session.commit()

        except ConciliacionError as exc:
            session.rollback()

            return (
                render_template(
                    "conciliacion/conciliar_manualmente.html",
                    movimiento=movimiento,
                    importe_a_texto=importe_a_texto,
                    intervalo_a_texto=_intervalo_a_texto,
                    database_name=get_database_name(),
                    error=str(exc),
                ),
                400,
            )

    return redirect(
        url_for("conciliacion.revisar_conciliacion")
    )


@bp.post(
    "/previstos/<int:movimiento_id>/deshacer-conciliacion-manual"
)
def deshacer_conciliacion_manual_desde_interfaz(
    movimiento_id: int,
):
    """Deshace una conciliación manual desde el listado."""

    session_factory = get_session_factory()

    with session_factory() as session:
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        if movimiento is None:
            return (
                "Movimiento previsto no encontrado.",
                404,
            )

        try:
            deshacer_conciliacion_manual(
                movimiento,
            )
            session.commit()

        except ConciliacionError as exc:
            session.rollback()
            return str(exc), 400

    return redirect(
        url_for(
            "conciliacion.listar_movimientos_previstos",
            estado="CONCILIADO",
        )
    )



@bp.post("/revisar/<int:movimiento_id>/aceptar")
def aceptar_propuesta_revision(movimiento_id: int):
    """Acepta una única propuesta automática de conciliación."""

    previsto_id = request.form.get(
        "previsto_id",
        type=int,
    )

    if previsto_id is None:
        return "Falta el movimiento previsto.", 400

    database_name = get_database_name()

    aliases_por_base = current_app.extensions.get(
        "contab_alias_conciliacion",
        {},
    )
    aliases_configurados = aliases_por_base.get(
        database_name,
        [],
    )

    session_factory = get_session_factory()

    try:
        with session_factory() as db_session:
            with db_session.begin():
                bancario = db_session.get(
                    MovimientoBancario,
                    movimiento_id,
                )

                if bancario is None:
                    return (
                        "Movimiento bancario no encontrado.",
                        404,
                    )

                if bancario.estado != "PENDIENTE":
                    raise ConciliacionError(
                        "El movimiento bancario ya no está pendiente."
                    )

                movimientos_previstos = db_session.scalars(
                    select(MovimientoPrevisto)
                    .options(
                        joinedload(MovimientoPrevisto.inmueble)
                    )
                    .where(
                        MovimientoPrevisto.estado == "PENDIENTE"
                    )
                    .order_by(
                        MovimientoPrevisto.fecha_prevista_desde,
                        MovimientoPrevisto.id,
                    )
                ).all()

                (
                    propuestas,
                    _,
                    _,
                ) = clasificar_movimientos_bancarios(
                    [bancario],
                    movimientos_previstos,
                    aliases_configurados=aliases_configurados,
                )

                if (
                    len(propuestas) != 1
                    or propuestas[0][1].id != previsto_id
                ):
                    raise ConciliacionError(
                        "La propuesta ya no es válida. "
                        "Vuelve a revisar la conciliación."
                    )

                _, previsto = propuestas[0]

                conciliacion = confirmar_conciliacion(
                    bancario,
                    previsto,
                )

                db_session.add(conciliacion)

    except ConciliacionError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "conciliacion.revisar_conciliacion"
        )
    )



@bp.post(
    "/previstos/<int:movimiento_id>"
    "/asociaciones/<int:conciliacion_id>/deshacer"
)
def deshacer_asociacion_bancaria_desde_interfaz(
    movimiento_id: int,
    conciliacion_id: int,
):
    """Deshace una asociación bancaria de un movimiento previsto."""

    session_factory = get_session_factory()

    with session_factory() as db_session:
        conciliacion = db_session.get(
            Conciliacion,
            conciliacion_id,
        )

        if (
            conciliacion is None
            or conciliacion.movimiento_previsto_id != movimiento_id
        ):
            return (
                "Asociación bancaria no encontrada.",
                404,
            )

        try:
            deshacer_asociacion_bancaria(
                conciliacion
            )
            db_session.commit()

        except ConciliacionError as exc:
            db_session.rollback()
            return str(exc), 400

    return redirect(
        url_for(
            "conciliacion.listar_movimientos_previstos",
            estado="TODOS",
        )
    )


@bp.post("/revisar/propuestas/aceptar")
def aceptar_propuesta_agrupada_revision():
    """Acepta una propuesta automática completa y todavía válida."""

    accion = request.form.get("accion", "exacta")

    if accion not in {
        "exacta",
        "parcial",
        "aceptar_diferencia",
    }:
        return "Acción de conciliación no válida.", 400

    try:
        bancario_ids = [
            int(valor)
            for valor in request.form.getlist("bancario_ids")
        ]
        previsto_ids = [
            int(valor)
            for valor in request.form.getlist("previsto_ids")
        ]
    except ValueError:
        return "Identificadores de movimientos no válidos.", 400

    if (
        not bancario_ids
        or not previsto_ids
        or len(set(bancario_ids)) != len(bancario_ids)
        or len(set(previsto_ids)) != len(previsto_ids)
        or any(identificador <= 0 for identificador in bancario_ids)
        or any(identificador <= 0 for identificador in previsto_ids)
    ):
        return "La propuesta indicada no es válida.", 400

    session_factory = get_session_factory()

    try:
        with session_factory() as db_session:
            with db_session.begin():
                _, _, propuestas = _obtener_revision_conciliacion(
                    db_session
                )

                ids_bancarios_solicitados = set(bancario_ids)
                ids_previstos_solicitados = set(previsto_ids)

                propuesta_elegida = next(
                    (
                        propuesta
                        for propuesta in propuestas
                        if {
                            bancario.id
                            for bancario in propuesta.bancarios
                        } == ids_bancarios_solicitados
                        and {
                            previsto.id
                            for previsto in propuesta.previstos
                        } == ids_previstos_solicitados
                    ),
                    None,
                )

                if propuesta_elegida is None:
                    raise ConciliacionError(
                        "La propuesta ya no es válida. "
                        "Vuelve a revisar la conciliación."
                    )

                if accion == "exacta":
                    asociaciones = confirmar_propuesta_conciliacion(
                        propuesta_elegida
                    )

                else:
                    bancarios = propuesta_elegida.bancarios
                    previstos = propuesta_elegida.previstos

                    total_bancario = sum(
                        saldo_movimiento_bancario(movimiento)[1]
                        for movimiento in bancarios
                    )

                    total_previsto = sum(
                        saldo_movimiento_previsto(movimiento)[1]
                        for movimiento in previstos
                    )

                    if total_bancario == total_previsto:
                        raise ConciliacionError(
                            "Los importes coinciden. "
                            "Utiliza la confirmación exacta."
                        )

                    # Prepara el reparto cronológico sin modificar
                    # todavía ninguno de los movimientos.
                    preparadas = preparar_asociaciones_cronologicas(
                        bancarios,
                        previstos,
                    )

                    asociaciones = confirmar_grupo_conciliacion(
                        preparadas,
                        cerrar_diferencia=(
                            accion == "aceptar_diferencia"
                        ),
                    )

                db_session.add_all(asociaciones)

    except ConciliacionError as exc:
        return str(exc), 400

    return redirect(
        url_for("conciliacion.revisar_conciliacion")
    )


@bp.post("/revisar/propuestas/rechazar")
def rechazar_propuesta_agrupada_revision():
    """Libera una propuesta automática para conciliación manual."""

    try:
        bancario_ids = [
            int(valor)
            for valor in request.form.getlist("bancario_ids")
        ]
        previsto_ids = [
            int(valor)
            for valor in request.form.getlist("previsto_ids")
        ]
    except ValueError:
        return "Identificadores de movimientos no válidos.", 400

    if (
        not bancario_ids
        or not previsto_ids
        or len(set(bancario_ids)) != len(bancario_ids)
        or len(set(previsto_ids)) != len(previsto_ids)
        or any(identificador <= 0 for identificador in bancario_ids)
        or any(identificador <= 0 for identificador in previsto_ids)
    ):
        return "La propuesta indicada no es válida.", 400

    session_factory = get_session_factory()

    with session_factory() as db_session:
        _, _, propuestas = _obtener_revision_conciliacion(
            db_session
        )

        ids_bancarios_solicitados = set(bancario_ids)
        ids_previstos_solicitados = set(previsto_ids)

        propuesta_elegida = next(
            (
                propuesta
                for propuesta in propuestas
                if {
                    bancario.id
                    for bancario in propuesta.bancarios
                } == ids_bancarios_solicitados
                and {
                    previsto.id
                    for previsto in propuesta.previstos
                } == ids_previstos_solicitados
            ),
            None,
        )

        if propuesta_elegida is None:
            return (
                "La propuesta ya no es válida. "
                "Vuelve a revisar la conciliación.",
                400,
            )

    (
        bancario_ids_rechazados,
        previsto_ids_rechazados,
    ) = _rechazos_revision()

    _guardar_rechazos_revision(
        bancario_ids_rechazados | ids_bancarios_solicitados,
        previsto_ids_rechazados | ids_previstos_solicitados,
    )

    return redirect(
        url_for("conciliacion.revisar_conciliacion")
    )


@bp.post("/revisar/manual/confirmar")
def confirmar_seleccion_manual_revision():
    """Confirma una selección manual exacta, parcial o con diferencia."""

    accion = request.form.get("accion", "exacta")

    if accion not in {
        "exacta",
        "parcial",
        "aceptar_diferencia",
    }:
        return "La acción de conciliación no es válida.", 400

    try:
        bancario_ids = [
            int(valor)
            for valor in request.form.getlist("bancario_ids")
        ]
        previsto_ids = [
            int(valor)
            for valor in request.form.getlist("previsto_ids")
        ]
    except ValueError:
        return "Identificadores de movimientos no válidos.", 400

    if (
        not bancario_ids
        or not previsto_ids
        or len(set(bancario_ids)) != len(bancario_ids)
        or len(set(previsto_ids)) != len(previsto_ids)
        or any(valor <= 0 for valor in bancario_ids)
        or any(valor <= 0 for valor in previsto_ids)
    ):
        return "La selección manual no es válida.", 400

    if len(bancario_ids) > 1 and len(previsto_ids) > 1:
        return "La conciliación manual m:n no está admitida.", 400

    session_factory = get_session_factory()

    try:
        with session_factory() as db_session:
            with db_session.begin():
                (
                    movimientos_bancarios,
                    movimientos_previstos,
                    propuestas,
                ) = _obtener_revision_conciliacion(
                    db_session
                )

                ids_bancarios_propuestos = {
                    movimiento.id
                    for propuesta in propuestas
                    for movimiento in propuesta.bancarios
                }

                ids_previstos_propuestos = {
                    movimiento.id
                    for propuesta in propuestas
                    for movimiento in propuesta.previstos
                }

                bancarios_manuales = {
                    movimiento.id: movimiento
                    for movimiento in movimientos_bancarios
                    if movimiento.id not in ids_bancarios_propuestos
                }

                previstos_manuales = {
                    movimiento.id: movimiento
                    for movimiento in movimientos_previstos
                    if movimiento.id not in ids_previstos_propuestos
                }

                if (
                    not set(bancario_ids).issubset(
                        bancarios_manuales
                    )
                    or not set(previsto_ids).issubset(
                        previstos_manuales
                    )
                ):
                    raise ConciliacionError(
                        "Alguno de los movimientos seleccionados "
                        "ya no está disponible en conciliación manual."
                    )

                bancarios = [
                    bancarios_manuales[identificador]
                    for identificador in bancario_ids
                ]

                previstos = [
                    previstos_manuales[identificador]
                    for identificador in previsto_ids
                ]

                if accion == "exacta":
                    propuesta = PropuestaConciliacion(
                        bancarios=bancarios,
                        previstos=previstos,
                        puntuacion=0,
                        motivos=[],
                    )

                    asociaciones = confirmar_propuesta_conciliacion(
                        propuesta
                    )

                else:
                    total_bancario = sum(
                        saldo_movimiento_bancario(movimiento)[1]
                        for movimiento in bancarios
                    )

                    total_previsto = sum(
                        saldo_movimiento_previsto(movimiento)[1]
                        for movimiento in previstos
                    )

                    if total_bancario == total_previsto:
                        raise ConciliacionError(
                            "Los importes coinciden. "
                            "Utiliza la conciliación exacta."
                        )

                    # Reparte los saldos por orden cronológico,
                    # sin modificar todavía ningún movimiento.
                    asociaciones_preparadas = (
                        preparar_asociaciones_cronologicas(
                            bancarios,
                            previstos,
                        )
                    )

                    # El servicio valida y confirma el resultado.
                    # Sólo la segunda acción cierra expresamente
                    # el saldo restante.
                    asociaciones = confirmar_grupo_conciliacion(
                        asociaciones_preparadas,
                        cerrar_diferencia=(
                            accion == "aceptar_diferencia"
                        ),
                    )

                db_session.add_all(asociaciones)

    except ConciliacionError as exc:
        return str(exc), 400

    return redirect(
        url_for("conciliacion.revisar_conciliacion")
    )


@bp.post("/revisar/debug")
def debug_revision():
    """Explica una pareja 1:1 sin modificar la conciliación."""

    if not current_app.config.get(
        "CONTAB_DEBUG_CONCILIACION",
        False,
    ):
        abort(404)

    valores_bancarios = request.form.getlist("bancario_ids")
    valores_previstos = request.form.getlist("previsto_ids")

    cardinalidad = (
        len(valores_bancarios),
        len(valores_previstos),
    )

    if cardinalidad not in {
        (1, 1),
        (1, 2),
        (2, 1),
    }:
        return (
            "Debug admite selecciones 1:1, 1:2 y 2:1.",
            400,
        )


    try:
        bancario_ids = [
            int(valor) for valor in valores_bancarios
        ]
        previsto_ids = [
            int(valor) for valor in valores_previstos
        ]
    except ValueError:
        return "Identificadores no válidos.", 400

    if (
        any(valor <= 0 for valor in bancario_ids + previsto_ids)
        or len(set(bancario_ids)) != len(bancario_ids)
        or len(set(previsto_ids)) != len(previsto_ids)
    ):
        return "Identificadores no válidos.", 400

    database_name = get_database_name()

    aliases_por_base = current_app.extensions.get(
        "contab_alias_conciliacion",
        {},
    )
    aliases = aliases_por_base.get(database_name, [])

    session_factory = get_session_factory()

    with session_factory() as db_session:
        bancarios = [
            db_session.get(MovimientoBancario, identificador)
            for identificador in bancario_ids
        ]
        previstos = [
            db_session.get(MovimientoPrevisto, identificador)
            for identificador in previsto_ids
        ]

        if any(m is None for m in bancarios + previstos):
            abort(404)

        if cardinalidad == (1, 1):
            diagnostico = diagnosticar_emparejamiento(
                bancarios[0],
                previstos[0],
                aliases,
            )
            agrupado = False
        else:
            diagnostico = diagnosticar_grupo_conciliacion(
                bancarios,
                previstos,
                aliases,
            )
            agrupado = True

        return render_template(
            "conciliacion/debug.html",
            bancarios=bancarios,
            previstos=previstos,
            diagnostico=diagnostico,
            agrupado=agrupado,
            tipo_grupo=(
                f"{len(previstos)} "
                f"{'previsto' if len(previstos) == 1 else 'previstos'}"
                " / "
                f"{len(bancarios)} "
                f"{'bancario' if len(bancarios) == 1 else 'bancarios'}"
            ),
            importe_a_texto=importe_a_texto,
            saldo_movimiento_bancario=saldo_movimiento_bancario,
            saldo_movimiento_previsto=saldo_movimiento_previsto,
            database_name=database_name,
        )


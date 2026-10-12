"""Define las rutas web para preparar reembolsos de gastos."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    url_for,
)

from contab.context import (
    get_database_name,
    get_session_factory,
)
from contab.contabilidad.services import (
    GastoRepercutiblePendiente,
    buscar_gastos_repercutibles_pendientes,
)
from contab.formato import (
    fecha_a_texto,
    importe_a_texto,
)
from contab.models import (
    Contrato,
    MovimientoPrevisto,
    SolicitudReembolso,
)
from contab.reembolsos.services import (
    ReembolsoError,
    SolicitudReembolsoPreparada,
    confirmar_solicitud_reembolso,
    preparar_eliminacion_solicitud_reembolso,
    preparar_solicitud_reembolso,
)


bp = Blueprint(
    "reembolsos",
    __name__,
    url_prefix="/reembolsos",
    template_folder="templates",
)


@dataclass(frozen=True)
class ReembolsosContratoPendientes:
    """Agrupa los gastos pendientes visibles de un contrato."""

    contrato: Contrato
    destinatario: str
    gastos: tuple[
        GastoRepercutiblePendiente,
        ...,
    ]


@dataclass(frozen=True)
class SolicitudReembolsoVisible:
    """Datos visibles de una solicitud enviada."""

    solicitud: SolicitudReembolso
    destinatario: str



def _destinatario_contrato(
    contrato: Contrato,
) -> str:
    """Obtiene los titulares del contrato como texto."""

    titulares = sorted(
        contrato.titulares,
        key=lambda titular: titular.orden,
    )

    return " / ".join(
        titular.inquilino.nombre
        for titular in titulares
    )


def _clave_origen(
    gasto: GastoRepercutiblePendiente,
) -> str:
    """Identifica el origen persistente de un gasto pendiente."""

    imputacion = gasto.imputacion

    if imputacion.apunte is not None:
        return f"A:{imputacion.apunte.id}"

    distribucion = (
        imputacion.distribucion_apunte
    )

    return f"D:{distribucion.id}"


def _seleccionar_gastos(
    pendientes: list[
        GastoRepercutiblePendiente
    ],
    origenes: list[str],
) -> list[GastoRepercutiblePendiente]:
    """Resuelve una selección contra los pendientes actuales."""

    por_origen = {
        _clave_origen(gasto): gasto
        for gasto in pendientes
    }

    seleccionados: list[
        GastoRepercutiblePendiente
    ] = []

    vistos: set[str] = set()

    for origen in origenes:
        if origen in vistos:
            raise ReembolsoError(
                "La selección contiene un gasto duplicado."
            )

        vistos.add(origen)

        gasto = por_origen.get(origen)

        if gasto is None:
            raise ReembolsoError(
                "Uno de los gastos seleccionados "
                "ya no está pendiente."
            )

        seleccionados.append(gasto)

    if not seleccionados:
        raise ReembolsoError(
            "Debe seleccionarse al menos un gasto."
        )

    return seleccionados


def _periodo_linea(
    linea,
) -> str:
    """Obtiene el período visible de una línea."""

    apunte = linea.apunte

    if (
        apunte.periodo_desde is None
        or apunte.periodo_hasta is None
    ):
        return ""

    return (
        f"del {fecha_a_texto(apunte.periodo_desde)} "
        f"al {fecha_a_texto(apunte.periodo_hasta)}"
    )


def _texto_linea(
    linea,
) -> str:
    """Explica una línea preparada de reembolso."""

    periodo = _periodo_linea(linea)

    descripcion = linea.concepto

    if periodo:
        descripcion = (
            f"{descripcion}, {periodo}"
        )

    texto = (
        f"- {descripcion}, de "
        f"{importe_a_texto(linea.importe_total)} €."
    )

    prorrateo = linea.prorrateo_temporal

    if prorrateo is not None:
        texto += (
            " Te corresponde abonar "
            f"{prorrateo.dias_contrato} de los "
            f"{prorrateo.dias_totales} días, es decir: "
            f"{importe_a_texto(prorrateo.importe_base)}"
            f" × {prorrateo.dias_contrato}"
            f" / {prorrateo.dias_totales}"
            f" = {importe_a_texto(prorrateo.importe_resultante)} €."
        )

    return texto


def _texto_solicitud(
    solicitud: SolicitudReembolsoPreparada,
) -> str:
    """Genera el texto que puede copiarse al correo."""

    lineas = [
        _texto_linea(linea)
        for linea in solicitud.lineas
    ]

    importes = [
        importe_a_texto(
            linea.importe_aplicable
        )
        for linea in solicitud.lineas
    ]

    partes = [
        *lineas,
        "",
    ]

    if len(importes) == 1:
        partes.append(
            "El total pendiente de abonar es de "
            f"{importes[0]} €."
        )
    else:
        partes.append(
            "Así que el total pendiente de abonar es de "
            f"{' + '.join(importes)}"
            f" = {importe_a_texto(solicitud.total)} €."
        )

    return "\n\n".join(partes)


def _render_revision(
    *,
    solicitud: SolicitudReembolsoPreparada,
    origenes: list[str],
):
    """Muestra la revisión de una solicitud preparada."""

    return render_template(
        "reembolsos/revision.html",
        solicitud=solicitud,
        origenes=origenes,
        destinatario=_destinatario_contrato(
            solicitud.contrato
        ),
        database_name=get_database_name(),
        fecha_a_texto=fecha_a_texto,
        importe_a_texto=importe_a_texto,
        texto_copiable=_texto_solicitud(
            solicitud
        ),
    )




@bp.get("/")
def listar_pendientes():
    """Muestra los gastos pendientes agrupados por contrato."""

    session_factory = get_session_factory()

    with session_factory() as session:
        contratos = session.scalars(
            select(Contrato)
            .order_by(Contrato.id)
        ).all()

        grupos: list[
            ReembolsosContratoPendientes
        ] = []

        for contrato in contratos:
            gastos = (
                buscar_gastos_repercutibles_pendientes(
                    session,
                    contrato=contrato,
                )
            )

            if not gastos:
                continue

            grupos.append(
                ReembolsosContratoPendientes(
                    contrato=contrato,
                    destinatario=(
                        _destinatario_contrato(
                            contrato
                        )
                    ),
                    gastos=tuple(gastos),
                )
            )

        solicitudes_activas = session.scalars(
            select(SolicitudReembolso)
            .join(
                SolicitudReembolso.movimiento_previsto
            )
            .where(
                MovimientoPrevisto.estado.in_(
                    (
                        "PENDIENTE",
                        "PARCIAL",
                        "CANCELADO",
                    )
                )
            )
            .order_by(
                SolicitudReembolso.fecha_envio.desc(),
                SolicitudReembolso.id.desc(),
            )
        ).all()

        solicitudes = [
            SolicitudReembolsoVisible(
                solicitud=solicitud,
                destinatario=_destinatario_contrato(
                    solicitud.contrato
                ),
            )
            for solicitud in solicitudes_activas
        ]

        return render_template(
            "reembolsos/pendientes.html",
            grupos=grupos,
            solicitudes=solicitudes,
            database_name=get_database_name(),
            fecha_a_texto=fecha_a_texto,
            importe_a_texto=importe_a_texto,
            clave_origen=_clave_origen,
        )


@bp.post("/<int:contrato_id>/preparar")
def revisar_solicitud(
    contrato_id: int,
):
    """Prepara una solicitud sin persistirla."""

    origenes = request.form.getlist(
        "origen"
    )

    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            contrato = session.get(
                Contrato,
                contrato_id,
            )

            if contrato is None:
                return "Contrato no encontrado.", 404

            pendientes = (
                buscar_gastos_repercutibles_pendientes(
                    session,
                    contrato=contrato,
                )
            )

            seleccionados = _seleccionar_gastos(
                pendientes,
                origenes,
            )

            solicitud = (
                preparar_solicitud_reembolso(
                    contrato=contrato,
                    gastos=seleccionados,
                )
            )

            return _render_revision(
                solicitud=solicitud,
                origenes=origenes,
            )

    except ReembolsoError as exc:
        return str(exc), 400


@bp.post("/<int:contrato_id>/enviar")
def marcar_como_enviado(
    contrato_id: int,
):
    """Confirma que una solicitud de reembolso ha sido enviada."""

    origenes = request.form.getlist(
        "origen"
    )

    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            with session.begin():
                contrato = session.get(
                    Contrato,
                    contrato_id,
                )

                if contrato is None:
                    return (
                        "Contrato no encontrado.",
                        404,
                    )

                pendientes = (
                    buscar_gastos_repercutibles_pendientes(
                        session,
                        contrato=contrato,
                    )
                )

                seleccionados = _seleccionar_gastos(
                    pendientes,
                    origenes,
                )

                preparada = (
                    preparar_solicitud_reembolso(
                        contrato=contrato,
                        gastos=seleccionados,
                    )
                )

                confirmacion = (
                    confirmar_solicitud_reembolso(
                        preparada=preparada,
                        fecha_envio=date.today(),
                    )
                )

                session.add_all([
                    confirmacion.solicitud,
                    confirmacion.movimiento,
                    *confirmacion.imputaciones,
                ])

    except ReembolsoError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "reembolsos.listar_pendientes"
        )
    )


@bp.post("/<int:solicitud_id>/eliminar")
def eliminar_solicitud_reembolso(
    solicitud_id: int,
):
    """Elimina una solicitud reversible y restaura sus gastos pendientes."""

    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            with session.begin():
                solicitud = session.get(
                    SolicitudReembolso,
                    solicitud_id,
                )

                if solicitud is None:
                    return (
                        "Solicitud de reembolso no encontrada.",
                        404,
                    )

                eliminacion = (
                    preparar_eliminacion_solicitud_reembolso(
                        solicitud
                    )
                )

                session.delete(
                    eliminacion.movimiento
                )

                for linea in eliminacion.lineas:
                    session.delete(
                        linea
                    )

                for imputacion in eliminacion.imputaciones:
                    session.delete(
                        imputacion
                    )

                session.delete(
                    eliminacion.solicitud
                )

    except ReembolsoError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "reembolsos.listar_pendientes"
        )
    )



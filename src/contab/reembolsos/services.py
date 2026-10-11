"""Implementa la lógica de negocio de los reembolsos de gastos."""

from dataclasses import dataclass

from contab.contabilidad.services import (
    GastoRepercutiblePendiente,
    calcular_reparto_contratos_detallado,
)
from contab.models import (
    ApunteContable,
    Contrato,
    ImputacionContrato,
)


class ReembolsoError(Exception):
    """Indica que no puede prepararse un reembolso válido."""


@dataclass(frozen=True)
class LineaSolicitudReembolsoPreparada:
    """Describe un gasto incluido en una solicitud preparada."""

    apunte: ApunteContable
    imputacion: ImputacionContrato
    concepto: str
    importe: int


@dataclass(frozen=True)
class SolicitudReembolsoPreparada:
    """Describe una solicitud de reembolso todavía no persistida."""

    contrato: Contrato
    lineas: tuple[
        LineaSolicitudReembolsoPreparada,
        ...,
    ]
    total: int


@dataclass(frozen=True)
class ProrrateoTemporalReembolso:
    dias_totales: int
    dias_contrato: int
    importe_base: int
    importe_resultante: int


@dataclass(frozen=True)
class RepartoEspacialReembolso:
    participacion: int
    importe_base: int
    importe_resultante: int


@dataclass(frozen=True)
class LineaSolicitudReembolsoPreparada:
    apunte: ApunteContable
    imputacion: ImputacionContrato
    concepto: str
    importe_total: int
    importe_aplicable: int
    reparto_espacial: RepartoEspacialReembolso | None
    prorrateo_temporal: ProrrateoTemporalReembolso | None



def _calculo_linea_reembolso(
    gasto: GastoRepercutiblePendiente,
) -> tuple[
    RepartoEspacialReembolso | None,
    ProrrateoTemporalReembolso | None,
]:
    """Obtiene la explicación del cálculo de una línea."""

    apunte = gasto.apunte
    imputacion = gasto.imputacion

    reparto_espacial = None

    if imputacion.distribucion_apunte is not None:
        distribucion = (
            imputacion.distribucion_apunte
        )

        importe_base_temporal = (
            distribucion.total
        )

        inmueble = distribucion.inmueble

        reparto_espacial = (
            RepartoEspacialReembolso(
                participacion=(
                    distribucion.participacion
                ),
                importe_base=apunte.total,
                importe_resultante=(
                    distribucion.total
                ),
            )
        )
    else:
        importe_base_temporal = apunte.total
        inmueble = apunte.inmueble

    reparto, _, dias_totales = (
        calcular_reparto_contratos_detallado(
            inmueble=inmueble,
            importe=importe_base_temporal,
            fecha=apunte.fecha,
            periodo_desde=apunte.periodo_desde,
            periodo_hasta=apunte.periodo_hasta,
            criterio_periodo=apunte.criterio_periodo,
        )
    )

    parte = next(
        parte
        for parte in reparto
        if parte.contrato is imputacion.contrato
    )

    prorrateo_temporal = None

    if (
        dias_totales is not None
        and parte.dias is not None
        and parte.dias < dias_totales
    ):
        prorrateo_temporal = (
            ProrrateoTemporalReembolso(
                dias_totales=dias_totales,
                dias_contrato=parte.dias,
                importe_base=(
                    importe_base_temporal
                ),
                importe_resultante=(
                    parte.importe
                ),
            )
        )

    return (
        reparto_espacial,
        prorrateo_temporal,
    )



def preparar_solicitud_reembolso(
    *,
    contrato: Contrato,
    gastos: list[GastoRepercutiblePendiente],
) -> SolicitudReembolsoPreparada:
    """Prepara una solicitud a partir de gastos pendientes seleccionados."""

    if not gastos:
        raise ReembolsoError(
            "Debe seleccionarse al menos un gasto."
        )

    lineas: list[
        LineaSolicitudReembolsoPreparada
    ] = []

    origenes: set[int] = set()
    total = 0

    for gasto in gastos:
        imputacion = gasto.imputacion

        if imputacion.contrato is not contrato:
            raise ReembolsoError(
                "Todos los gastos deben corresponder "
                "al mismo contrato."
            )

        origen = (
            imputacion.apunte
            if imputacion.apunte is not None
            else imputacion.distribucion_apunte
        )

        if origen is None:
            raise ReembolsoError(
                "El gasto no tiene un origen válido."
            )

        identificador_origen = id(origen)

        if identificador_origen in origenes:
            raise ReembolsoError(
                "No puede incluirse dos veces el mismo gasto."
            )

        origenes.add(identificador_origen)

        reparto_espacial, prorrateo_temporal = (
            _calculo_linea_reembolso(
                gasto
            )
        )

        lineas.append(
            LineaSolicitudReembolsoPreparada(
                apunte=gasto.apunte,
                imputacion=imputacion,
                concepto=gasto.apunte.concepto,
                importe_total=gasto.apunte.total,
                importe_aplicable=imputacion.importe,
                reparto_espacial=reparto_espacial,
                prorrateo_temporal=prorrateo_temporal,
            )
        )

        total += imputacion.importe

    return SolicitudReembolsoPreparada(
        contrato=contrato,
        lineas=tuple(lineas),
        total=total,
    )

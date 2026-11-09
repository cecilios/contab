
"""Calcula la situación económica de un contrato de alquiler."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from contab.models import (
    ApunteContable,
    Conciliacion,
    Factura,
    MovimientoBancario,
    MovimientoPrevisto,
    SolicitudReembolso,
)


@dataclass(frozen=True)
class MovimientoEconomico:
    """Importe exigible o cobro atribuido a un contrato."""

    fecha: date | None
    concepto: str
    importe: int


@dataclass
class SituacionContrato:
    """Resultado económico de un contrato en un período."""

    exigibles: list[MovimientoEconomico]
    cobros: list[MovimientoEconomico]
    saldo_anterior: int
    total_exigible: int
    total_cobrado: int
    saldo: int


def calcular_situacion_contrato(
    session: Session,
    contrato_id: int,
    fecha_desde: date,
    fecha_hasta: date,
) -> SituacionContrato:
    """Calcula obligaciones, cobros y saldo acumulado.

    Los importes se expresan en céntimos.

    Las facturas son exigibles desde su emisión.
    Los cobros bancarios utilizan su fecha bancaria.
    Los cobros manuales utilizan la fecha prevista.
    """

    if fecha_desde > fecha_hasta:
        raise ValueError(
            "La fecha inicial no puede ser posterior "
            "a la fecha final."
        )

    obligaciones: list[MovimientoEconomico] = []
    pagos: list[MovimientoEconomico] = []

    # 1. Facturas emitidas hasta la fecha de consulta.

    facturas = session.scalars(
        select(Factura)
        .where(
            Factura.contrato_id == contrato_id,
            Factura.estado == "EMITIDA",
            Factura.fecha_emision <= fecha_hasta,
        )
        .order_by(
            Factura.fecha_emision,
            Factura.id,
        )
    ).all()

    for factura in facturas:
        obligaciones.append(
            MovimientoEconomico(
                fecha=factura.fecha_emision,
                concepto=(
                    f"Factura {factura.numero_factura}"
                ),
                importe=factura.total,
            )
        )

    # 1 bis. Alquileres contabilizados sin factura.
    #
    # El movimiento previsto identifica el contrato.
    # Los ingresos negativos generan previstos de GASTO.
    #
    # Se excluyen los apuntes asociados a facturas
    # para evitar contabilizar dos veces el mismo ingreso.

    movimiento_del_contrato = (
        select(MovimientoPrevisto.id)
        .where(
            MovimientoPrevisto.apunte_id
            == ApunteContable.id,
            MovimientoPrevisto.contrato_id
            == contrato_id,
            or_(
                and_(
                    ApunteContable.importe_negativo.is_(False),
                    MovimientoPrevisto.naturaleza == "INGRESO",
                ),
                and_(
                    ApunteContable.importe_negativo.is_(True),
                    MovimientoPrevisto.naturaleza == "GASTO",
                ),
            ),
        )
        .exists()
    )

    apunte_con_factura = (
        select(Factura.id)
        .where(
            Factura.apunte_contable_id
            == ApunteContable.id,
        )
        .exists()
    )

    alquileres_sin_factura = session.scalars(
        select(ApunteContable)
        .where(
            ApunteContable.naturaleza == "INGRESO",
            ApunteContable.categoria == "ING_ALQUILERES",
            ApunteContable.fecha <= fecha_hasta,
            movimiento_del_contrato,
            ~apunte_con_factura,
        )
        .order_by(
            ApunteContable.fecha,
            ApunteContable.id,
        )
    ).all()

    for apunte in alquileres_sin_factura:
        signo = -1 if apunte.importe_negativo else 1

        obligaciones.append(
            MovimientoEconomico(
                fecha=apunte.fecha,
                concepto=apunte.concepto,
                importe=signo * apunte.total,
            )
        )

    # 1 ter. Solicitudes de reembolso enviadas.
    #
    # El reembolso es exigible desde su fecha de envío.
    # No se vuelve a contabilizar el gasto original.
    #
    # La propiedad total de SolicitudReembolso
    # calcula el importe firmado de sus líneas.

    solicitudes = session.scalars(
        select(SolicitudReembolso)
        .where(
            SolicitudReembolso.contrato_id == contrato_id,
            SolicitudReembolso.fecha_envio <= fecha_hasta,
        )
        .order_by(
            SolicitudReembolso.fecha_envio,
            SolicitudReembolso.id,
        )
    ).all()

    for solicitud in solicitudes:
        obligaciones.append(
            MovimientoEconomico(
                fecha=solicitud.fecha_envio,
                concepto=f"Reembolso {solicitud.fecha_envio:%d/%m/%Y}",
                importe=solicitud.total,
            )
        )

    # 2. Cobros y devoluciones bancarias del contrato.
    #
    # Los ingresos aumentan lo cobrado.
    # Las devoluciones al inquilino lo disminuyen.
    #
    # Solo incorporamos gastos bancarios vinculados
    # a solicitudes de reembolso.

    conciliaciones = session.execute(
        select(
            Conciliacion,
            MovimientoBancario,
        )
        .join(
            MovimientoPrevisto,
            Conciliacion.movimiento_previsto_id
            == MovimientoPrevisto.id,
        )
        .join(
            MovimientoBancario,
            Conciliacion.movimiento_bancario_id
            == MovimientoBancario.id,
        )
        .where(
            MovimientoPrevisto.contrato_id == contrato_id,
            MovimientoBancario.fecha <= fecha_hasta,
            or_(
                and_(
                    MovimientoPrevisto.naturaleza == "INGRESO",
                    MovimientoBancario.naturaleza == "INGRESO",
                ),

                and_(
                    MovimientoPrevisto.naturaleza == "GASTO",
                    MovimientoBancario.naturaleza == "GASTO",
                    or_(
                        # Devolución de una solicitud de reembolso.
                        MovimientoPrevisto.solicitud_reembolso_id.is_not(
                            None
                        ),
                        # Devolución de un alquiler corregido.
                        MovimientoPrevisto.apunte.has(
                            and_(
                                ApunteContable.naturaleza == "INGRESO",
                                ApunteContable.categoria == "ING_ALQUILERES",
                                ApunteContable.importe_negativo.is_(True),
                            )
                        ),
                    ),
                ),
            ),
        )
        .order_by(
            MovimientoBancario.fecha,
            Conciliacion.id,
        )
    ).all()

    for conciliacion, bancario in conciliaciones:
        signo = (
            1
            if bancario.naturaleza == "INGRESO"
            else -1
        )

        pagos.append(
            MovimientoEconomico(
                fecha=bancario.fecha,
                concepto=bancario.descripcion_original,
                importe=(
                    signo * conciliacion.importe_asociado
                ),
            )
        )


    # 3. Cobros y devoluciones conciliados manualmente.
    #
    # Utilizamos preferentemente la fecha del apunte.
    # Si no existe apunte, utilizamos la fecha prevista.
    #
    # Las devoluciones se representan con signo negativo.

    movimientos_manuales = session.scalars(
        select(MovimientoPrevisto)
        .where(
            MovimientoPrevisto.contrato_id == contrato_id,
            MovimientoPrevisto.estado == "CONCILIADO",
            MovimientoPrevisto.metodo_conciliacion == "MANUAL",
            or_(
                MovimientoPrevisto.naturaleza == "INGRESO",
                and_(
                    MovimientoPrevisto.naturaleza == "GASTO",
                    or_(
                        MovimientoPrevisto.solicitud_reembolso_id.is_not(
                            None
                        ),
                        MovimientoPrevisto.apunte.has(
                            and_(
                                ApunteContable.naturaleza == "INGRESO",
                                ApunteContable.categoria == "ING_ALQUILERES",
                                ApunteContable.importe_negativo.is_(True),
                            )
                        ),
                    ),
                ),
            ),
        )
        .order_by(MovimientoPrevisto.id)
    ).all()

    for movimiento in movimientos_manuales:
        # La fecha contable tiene prioridad sobre la prevista.
        fecha = (
            movimiento.apunte.fecha
            if movimiento.apunte is not None
            else movimiento.fecha_prevista_desde
        )

        # Los movimientos sin fecha conocida también cuentan:
        # están confirmados manualmente.
        #
        # Si conocemos la fecha, respetamos el corte.
        if fecha is not None and fecha > fecha_hasta:
            continue

        signo = (
            1
            if movimiento.naturaleza == "INGRESO"
            else -1
        )

        pagos.append(
            MovimientoEconomico(
                fecha=fecha,
                concepto=movimiento.concepto,
                importe=(
                    signo * movimiento.importe_esperado
                ),
            )
        )


    # 4. Separar el saldo anterior del período consultado.
    #
    # Los cobros manuales sin fecha conocida se incluyen
    # en el período consultado y no en el saldo anterior.

    saldo_anterior = (
        sum(
            movimiento.importe
            for movimiento in obligaciones
            if movimiento.fecha < fecha_desde
        )
        -
        sum(
            movimiento.importe
            for movimiento in pagos
            if (
                movimiento.fecha is not None
                and movimiento.fecha < fecha_desde
            )
        )
    )

    exigibles = [
        movimiento
        for movimiento in obligaciones
        if movimiento.fecha >= fecha_desde
    ]

    cobros = [
        movimiento
        for movimiento in pagos
        if (
            movimiento.fecha is None
            or movimiento.fecha >= fecha_desde
        )
    ]

    # Mostrar los movimientos por orden cronológico.
    # Los cobros sin fecha aparecen al final.
    exigibles.sort(
        key=lambda movimiento: movimiento.fecha
    )

    cobros.sort(
        key=lambda movimiento: (
            movimiento.fecha is None,
            movimiento.fecha or date.max,
        )
    )

    total_exigible = sum(
        movimiento.importe
        for movimiento in exigibles
    )

    total_cobrado = sum(
        movimiento.importe
        for movimiento in cobros
    )

    saldo = (
        saldo_anterior
        + total_exigible
        - total_cobrado
    )

    return SituacionContrato(
        exigibles=exigibles,
        cobros=cobros,
        saldo_anterior=saldo_anterior,
        total_exigible=total_exigible,
        total_cobrado=total_cobrado,
        saldo=saldo,
    )


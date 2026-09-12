"""Implementa la lógica de negocio de la conciliación bancaria."""

from datetime import date

from contab.models import (
    ApunteContable,
    Contrato,
    Inmueble,
    MovimientoBancario,
    MovimientoPrevisto,
)


class ConciliacionError(Exception):
    """Indica que no puede crearse un movimiento previsto válido."""


def crear_movimiento_previsto(
    *,
    inmueble: Inmueble,
    naturaleza: str,
    concepto: str,
    importe_esperado: int,
    fecha_prevista_desde: date | None = None,
    fecha_prevista_hasta: date | None = None,
    contraparte: str = "",
    apunte: ApunteContable | None = None,
    contrato: Contrato | None = None,
    notas: str = "",
) -> MovimientoPrevisto:
    """Prepara un movimiento previsto pendiente sin persistirlo."""

    naturaleza = naturaleza.strip().upper()
    concepto = concepto.strip()

    if naturaleza not in {"INGRESO", "GASTO"}:
        raise ConciliacionError(
            "La naturaleza debe ser INGRESO o GASTO."
        )

    if not concepto:
        raise ConciliacionError(
            "El concepto del movimiento previsto es obligatorio."
        )

    if importe_esperado <= 0:
        raise ConciliacionError(
            "El importe esperado debe ser mayor que cero."
        )

    if apunte is not None:
        if apunte.inmueble is not inmueble:
            raise ConciliacionError(
                "El apunte y el movimiento previsto deben "
                "pertenecer al mismo inmueble."
            )

        if apunte.naturaleza != naturaleza:
            raise ConciliacionError(
                "El apunte y el movimiento previsto deben "
                "tener la misma naturaleza."
            )

    if (contrato is not None
        and contrato.inmueble is not inmueble
    ):
        raise ConciliacionError(
            "El contrato y el movimiento previsto deben "
            "pertenecer al mismo inmueble."
        )

    if (fecha_prevista_hasta is not None
        and fecha_prevista_desde is None
    ):
        raise ConciliacionError(
            "No puede indicarse la fecha prevista hasta "
            "sin indicar la fecha prevista desde."
        )

    if (fecha_prevista_desde is not None
        and fecha_prevista_hasta is not None
        and fecha_prevista_hasta < fecha_prevista_desde
    ):
        raise ConciliacionError(
            "La fecha prevista hasta no puede ser anterior "
            "a la fecha prevista desde."
        )

    return MovimientoPrevisto(
        inmueble=inmueble,
        contrato=contrato,
        apunte=apunte,
        fecha_prevista_desde=fecha_prevista_desde,
        fecha_prevista_hasta=fecha_prevista_hasta,
        naturaleza=naturaleza,
        concepto=concepto,
        importe_esperado=importe_esperado,
        contraparte=contraparte.strip(),
        estado="PENDIENTE",
        notas=notas.strip() or None,
    )


def crear_movimiento_desde_apunte(
    *,
    apunte: ApunteContable,
    fecha_prevista_desde: date | None = None,
    fecha_prevista_hasta: date | None = None,
    importe_esperado: int | None = None,
    concepto: str | None = None,
    contraparte: str | None = None,
    contrato: Contrato | None = None,
    notas: str = "",
) -> MovimientoPrevisto:
    """Crea un movimiento previsto reutilizando los datos del apunte."""

    return crear_movimiento_previsto(
        inmueble=apunte.inmueble,
        apunte=apunte,
        contrato=contrato,
        fecha_prevista_desde=fecha_prevista_desde,
        fecha_prevista_hasta=fecha_prevista_hasta,
        naturaleza=apunte.naturaleza,
        concepto=(
            apunte.concepto
            if concepto is None
            else concepto
        ),
        importe_esperado=(
            apunte.total
            if importe_esperado is None
            else importe_esperado
        ),
        contraparte=(
            apunte.tercero_nombre
            if contraparte is None
            else contraparte
        ),
        notas=notas,
    )


def descartar_movimiento_bancario(
    movimiento: MovimientoBancario,
) -> MovimientoBancario:
    """Marca como ajeno a Contab un movimiento pendiente."""

    if movimiento.estado == "CONCILIADO":
        raise ConciliacionError(
            "Un movimiento conciliado no puede descartarse."
        )

    movimiento.estado = "DESCARTADO"

    return movimiento


def restaurar_movimiento_bancario(
    movimiento: MovimientoBancario,
) -> MovimientoBancario:
    """Devuelve a pendiente un movimiento descartado."""

    if movimiento.estado != "DESCARTADO":
        raise ConciliacionError(
            "Sólo puede restaurarse un movimiento descartado."
        )

    movimiento.estado = "PENDIENTE"

    return movimiento



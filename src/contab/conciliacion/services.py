"""Implementa la lógica de negocio de la conciliación bancaria."""

import unicodedata

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


def _normalizar_texto_conciliacion(
    texto: str | None,
) -> str:
    """Normaliza texto para comparaciones sencillas de conciliación."""

    if not texto:
        return ""

    texto = texto.upper()

    texto = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )

    return " ".join(
        texto.split()
    )


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


def cancelar_movimiento_previsto(
    movimiento: MovimientoPrevisto,
) -> MovimientoPrevisto:
    """Cancela un movimiento previsto todavía pendiente."""

    if movimiento.estado != "PENDIENTE":
        raise ConciliacionError(
            "Sólo puede cancelarse un movimiento previsto pendiente."
        )

    movimiento.estado = "CANCELADO"

    return movimiento


def restaurar_movimiento_previsto(
    movimiento: MovimientoPrevisto,
) -> MovimientoPrevisto:
    """Devuelve a pendiente un movimiento previsto cancelado."""

    if movimiento.estado != "CANCELADO":
        raise ConciliacionError(
            "Sólo puede restaurarse un movimiento previsto cancelado."
        )

    movimiento.estado = "PENDIENTE"

    return movimiento


def puntuar_candidato_conciliacion(
    movimiento_bancario: MovimientoBancario,
    movimiento_previsto: MovimientoPrevisto,
) -> int:
    """Puntúa la posible relación entre dos movimientos pendientes."""

    if movimiento_bancario.estado != "PENDIENTE":
        return 0

    if movimiento_previsto.estado != "PENDIENTE":
        return 0

    if (movimiento_bancario.naturaleza
        != movimiento_previsto.naturaleza
    ):
        return 0

    puntuacion = 0

    if movimiento_bancario.importe == movimiento_previsto.importe_esperado:
        puntuacion += 100

    fecha_desde = movimiento_previsto.fecha_prevista_desde
    fecha_hasta = movimiento_previsto.fecha_prevista_hasta

    if fecha_desde is not None:
        if fecha_hasta is None:
            if movimiento_bancario.fecha == fecha_desde:
                puntuacion += 20
        elif (
            fecha_desde
            <= movimiento_bancario.fecha
            <= fecha_hasta
        ):
            puntuacion += 20

    contraparte = _normalizar_texto_conciliacion(
        movimiento_previsto.contraparte
    )

    texto_bancario = _normalizar_texto_conciliacion(
        " ".join(
            [
                movimiento_bancario.tipo_original,
                movimiento_bancario.descripcion_original,
            ]
        )
    )

    if (contraparte
        and contraparte in texto_bancario
    ):
        puntuacion += 50

    return puntuacion


def buscar_candidatos_conciliacion(
    movimiento_bancario: MovimientoBancario,
    movimientos_previstos: list[MovimientoPrevisto],
) -> list[tuple[MovimientoPrevisto, int]]:
    """Devuelve las previsiones compatibles ordenadas por puntuación."""

    if movimiento_bancario.estado != "PENDIENTE":
        return []

    candidatos = []

    for movimiento_previsto in movimientos_previstos:
        if movimiento_previsto.estado != "PENDIENTE":
            continue

        if (
            movimiento_previsto.naturaleza
            != movimiento_bancario.naturaleza
        ):
            continue

        puntuacion = puntuar_candidato_conciliacion(
            movimiento_bancario,
            movimiento_previsto,
        )

        candidatos.append(
            (movimiento_previsto, puntuacion)
        )

    candidatos.sort(
        key=lambda candidato: candidato[1],
        reverse=True,
    )

    return candidatos



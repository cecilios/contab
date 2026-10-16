"""Implementa la lógica de negocio de la conciliación bancaria."""

import unicodedata

from datetime import date, timedelta
from sqlalchemy.orm import object_session

from contab.models import (
    ApunteContable,
    Conciliacion,
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


def _fecha_compatible_conciliacion(
    movimiento_bancario: MovimientoBancario,
    movimiento_previsto: MovimientoPrevisto,
) -> bool:
    """Comprueba que el movimiento no llegue excesivamente anticipado."""

    fecha_desde = movimiento_previsto.fecha_prevista_desde

    if fecha_desde is None:
        return True

    return (
        movimiento_bancario.fecha
        >= fecha_desde - timedelta(days=7)
    )


def _aliases_movimiento_previsto(
    movimiento: MovimientoPrevisto,
    aliases_configurados: list[tuple[str, str, str]],
) -> list[str]:
    """Selecciona los alias aplicables a un movimiento previsto."""

    referencia = movimiento.inmueble.referencia.upper()

    concepto = _normalizar_texto_conciliacion(
        movimiento.concepto
    )

    return [
        alias
        for tipo, inmueble_ref, alias in aliases_configurados
        if (
            inmueble_ref.upper() == referencia
            and _normalizar_texto_conciliacion(tipo) in concepto
        )
    ]




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
    aliases: list[str] | None = None,
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

    if not _fecha_compatible_conciliacion(
        movimiento_bancario,
        movimiento_previsto,
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
        elif (fecha_desde
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
                movimiento_bancario.referencia_bancaria,
            ]
        )
    )

    if (contraparte
        and contraparte in texto_bancario
    ):
        puntuacion += 50

    if aliases:
        for alias in aliases:
            alias_normalizado = _normalizar_texto_conciliacion(
                alias
            )

            if (alias_normalizado
                and alias_normalizado != contraparte
                and alias_normalizado in texto_bancario
            ):
                puntuacion += 40
                break

    return puntuacion


def buscar_candidatos_conciliacion(
    movimiento_bancario: MovimientoBancario,
    movimientos_previstos: list[MovimientoPrevisto],
    aliases_configurados: (
        list[tuple[str, str, str]] | None
    ) = None,
) -> list[tuple[MovimientoPrevisto, int]]:
    """Devuelve las previsiones compatibles ordenadas por puntuación."""

    if aliases_configurados is None:
        aliases_configurados = []

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

        aliases = _aliases_movimiento_previsto(
            movimiento_previsto,
            aliases_configurados,
        )

        if not _fecha_compatible_conciliacion(
            movimiento_bancario,
            movimiento_previsto,
        ):
            continue

        puntuacion = puntuar_candidato_conciliacion(
            movimiento_bancario,
            movimiento_previsto,
            aliases=aliases,
        )

        candidatos.append(
            (movimiento_previsto, puntuacion)
        )

    candidatos.sort(
        key=lambda candidato: candidato[1],
        reverse=True,
    )

    return candidatos


def proponer_conciliacion(
    movimiento_bancario: MovimientoBancario,
    movimientos_previstos: list[MovimientoPrevisto],
    aliases_configurados: (
        list[tuple[str, str, str]] | None
    ) = None,
) -> MovimientoPrevisto | None:
    """Propone el mejor movimiento previsto cuando hay un candidato claro."""

    candidatos = buscar_candidatos_conciliacion(
        movimiento_bancario,
        movimientos_previstos,
        aliases_configurados=aliases_configurados,
    )

    if not candidatos:
        return None

    mejor_movimiento, mejor_puntuacion = candidatos[0]

    if mejor_puntuacion <= 20:
        return None

    if (
        len(candidatos) > 1
        and candidatos[1][1] == mejor_puntuacion
    ):
        return None

    return mejor_movimiento


def proponer_descarte(
    movimiento_bancario: MovimientoBancario,
    aliases_descartar: list[str] | None = None,
) -> bool:
    """Indica si un movimiento pendiente parece ajeno a Contab."""

    if movimiento_bancario.estado != "PENDIENTE":
        return False

    if not aliases_descartar:
        return False

    texto_bancario = _normalizar_texto_conciliacion(
        " ".join(
            [
                movimiento_bancario.tipo_original,
                movimiento_bancario.descripcion_original,
                movimiento_bancario.referencia_bancaria,
            ]
        )
    )

    return any(
        alias_normalizado
        and alias_normalizado in texto_bancario
        for alias in aliases_descartar
        if (
            alias_normalizado
            := _normalizar_texto_conciliacion(alias)
        )
    )


def clasificar_movimiento_bancario(
    movimiento_bancario: MovimientoBancario,
    movimientos_previstos: list[MovimientoPrevisto],
    aliases_configurados: (
        list[tuple[str, str, str]] | None
    ) = None,
    aliases_descartar: list[str] | None = None,
) -> tuple[str, MovimientoPrevisto | None]:
    """Clasifica un movimiento pendiente para su revisión."""

    propuesta = proponer_conciliacion(
        movimiento_bancario,
        movimientos_previstos,
        aliases_configurados=aliases_configurados,
    )

    if propuesta is not None:
        return "CONCILIAR", propuesta

    if proponer_descarte(
        movimiento_bancario,
        aliases_descartar=aliases_descartar,
    ):
        return "DESCARTAR", None

    return "PENDIENTE", None


def clasificar_movimientos_bancarios(
    movimientos_bancarios: list[MovimientoBancario],
    movimientos_previstos: list[MovimientoPrevisto],
    aliases_configurados: (
        list[tuple[str, str, str]] | None
    ) = None,
    aliases_descartar: list[str] | None = None,
) -> tuple[
    list[tuple[MovimientoBancario, MovimientoPrevisto]],
    list[MovimientoBancario],
    list[MovimientoBancario],
]:
    """Agrupa los movimientos pendientes según la propuesta automática."""

    a_conciliar = []
    a_descartar = []
    pendientes = []

    for movimiento_bancario in movimientos_bancarios:
        if movimiento_bancario.estado != "PENDIENTE":
            continue

        clasificacion, propuesta = clasificar_movimiento_bancario(
            movimiento_bancario,
            movimientos_previstos,
            aliases_configurados=aliases_configurados,
            aliases_descartar=aliases_descartar,
        )

        if clasificacion == "CONCILIAR":
            assert propuesta is not None

            a_conciliar.append(
                (movimiento_bancario, propuesta)
            )

        elif clasificacion == "DESCARTAR":
            a_descartar.append(
                movimiento_bancario
            )

        else:
            pendientes.append(
                movimiento_bancario
            )

    return (
        a_conciliar,
        a_descartar,
        pendientes,
    )



def confirmar_conciliacion(
    movimiento_bancario: MovimientoBancario,
    movimiento_previsto: MovimientoPrevisto,
) -> Conciliacion:
    """Confirma una conciliación individual con importes idénticos."""

    if movimiento_bancario.estado != "PENDIENTE":
        raise ConciliacionError(
            "El movimiento bancario debe estar pendiente."
        )

    if movimiento_previsto.estado != "PENDIENTE":
        raise ConciliacionError(
            "El movimiento previsto debe estar pendiente."
        )

    if (
        movimiento_bancario.importe
        != movimiento_previsto.importe_esperado
    ):
        raise ConciliacionError(
            "La conciliación automática sólo puede confirmarse "
            "cuando los importes coinciden."
        )

    conciliaciones = confirmar_grupo_conciliacion([
        (
            movimiento_bancario,
            movimiento_previsto,
            movimiento_bancario.importe,
        ),
    ])

    return conciliaciones[0]


def conciliar_movimiento_previsto_manualmente(
    movimiento: MovimientoPrevisto,
    notas: str,
) -> None:
    """Marca un movimiento previsto como conciliado manualmente."""

    if movimiento.estado != "PENDIENTE":
        raise ConciliacionError(
            "El movimiento previsto debe estar pendiente."
        )

    notas = notas.strip()

    if not notas:
        raise ConciliacionError(
            "La conciliación manual requiere una explicación."
        )

    movimiento.estado = "CONCILIADO"
    movimiento.metodo_conciliacion = "MANUAL"
    movimiento.notas = notas


def deshacer_conciliacion_manual(
    movimiento: MovimientoPrevisto,
) -> None:
    """Devuelve a pendiente un movimiento conciliado manualmente."""

    if (
        movimiento.estado != "CONCILIADO"
        or movimiento.metodo_conciliacion != "MANUAL"
    ):
        raise ConciliacionError(
            "El movimiento debe estar conciliado manualmente."
        )

    movimiento.estado = "PENDIENTE"
    movimiento.metodo_conciliacion = None
    movimiento.notas = None


def saldo_movimiento_bancario(
    movimiento: MovimientoBancario,
) -> tuple[int, int]:
    """Devuelve los importes asociado y pendiente de un movimiento bancario."""

    asociado = sum(
        conciliacion.importe_asociado
        for conciliacion in movimiento.conciliaciones
    )

    pendiente = movimiento.importe - asociado

    return asociado, pendiente


def saldo_movimiento_previsto(
    movimiento: MovimientoPrevisto,
) -> tuple[int, int]:
    """Devuelve los importes asociado y pendiente de un movimiento previsto."""

    asociado = sum(
        conciliacion.importe_asociado
        for conciliacion in movimiento.conciliaciones
    )

    pendiente = movimiento.importe_esperado - asociado

    return asociado, pendiente



def validar_asociacion(
    movimiento_bancario: MovimientoBancario,
    movimiento_previsto: MovimientoPrevisto,
    importe: int,
) -> None:
    """Comprueba si puede asociarse un importe entre dos movimientos."""

    if movimiento_bancario.estado not in {
        "PENDIENTE",
        "PARCIAL",
    }:
        raise ConciliacionError(
            "El estado del movimiento bancario no permite asociarlo."
        )

    if movimiento_previsto.estado not in {
        "PENDIENTE",
        "PARCIAL",
    }:
        raise ConciliacionError(
            "El estado del movimiento previsto no permite asociarlo."
        )

    if (
        movimiento_bancario.naturaleza
        != movimiento_previsto.naturaleza
    ):
        raise ConciliacionError(
            "Los movimientos deben tener la misma naturaleza."
        )

    if importe <= 0:
        raise ConciliacionError(
            "El importe asociado debe ser positivo."
        )

    if any(
        conciliacion.movimiento_previsto is movimiento_previsto
        or (
            movimiento_previsto.id is not None
            and conciliacion.movimiento_previsto_id
            == movimiento_previsto.id
        )
        for conciliacion in movimiento_bancario.conciliaciones
    ):
        raise ConciliacionError(
            "Estos movimientos ya están asociados."
        )

    _, pendiente_bancario = saldo_movimiento_bancario(
        movimiento_bancario
    )

    _, pendiente_previsto = saldo_movimiento_previsto(
        movimiento_previsto
    )

    if (
        importe > pendiente_bancario
        or importe > pendiente_previsto
    ):
        raise ConciliacionError(
            "El importe supera el saldo disponible "
            "de alguno de los movimientos."
        )



def asociar_movimientos(
    movimiento_bancario: MovimientoBancario,
    movimiento_previsto: MovimientoPrevisto,
    importe: int,
) -> Conciliacion:
    """Crea una asociación validada entre dos movimientos."""

    validar_asociacion(
        movimiento_bancario,
        movimiento_previsto,
        importe,
    )

    return Conciliacion(
        movimiento_bancario=movimiento_bancario,
        movimiento_previsto=movimiento_previsto,
        importe_asociado=importe,
    )



def actualizar_estado_movimiento_bancario(
    movimiento: MovimientoBancario,
) -> None:
    """Actualiza el estado según el importe bancario asociado."""

    asociado, pendiente = saldo_movimiento_bancario(
        movimiento
    )

    if asociado == 0:
        movimiento.estado = "PENDIENTE"
    elif pendiente == 0:
        movimiento.estado = "CONCILIADO"
    else:
        movimiento.estado = "PARCIAL"


def actualizar_estado_movimiento_previsto(
    movimiento: MovimientoPrevisto,
) -> None:
    """Actualiza el estado según el importe previsto asociado."""

    # Una conciliación manual no tiene asociaciones bancarias.
    if movimiento.metodo_conciliacion == "MANUAL":
        return

    asociado, pendiente = saldo_movimiento_previsto(
        movimiento
    )

    if asociado == 0:
        movimiento.estado = "PENDIENTE"
        movimiento.metodo_conciliacion = None
    elif pendiente == 0:
        movimiento.estado = "CONCILIADO"
        movimiento.metodo_conciliacion = "INDIVIDUAL"
    else:
        movimiento.estado = "PARCIAL"
        movimiento.metodo_conciliacion = "INDIVIDUAL"



def confirmar_grupo_conciliacion(
    asociaciones: list[
        tuple[MovimientoBancario, MovimientoPrevisto, int]
    ],
) -> list[Conciliacion]:
    """Confirma un grupo de asociaciones sin guardar la transacción."""

    if not asociaciones:
        raise ConciliacionError(
            "El grupo de conciliación no puede estar vacío."
        )

    importes_bancarios = {}
    importes_previstos = {}
    parejas = set()

    # Primera fase: comprobar todas las asociaciones sin modificar nada.
    for bancario, previsto, importe in asociaciones:
        validar_asociacion(
            bancario,
            previsto,
            importe,
        )

        pareja = (bancario, previsto)

        if pareja in parejas:
            raise ConciliacionError(
                "La misma pareja aparece varias veces en el grupo."
            )

        parejas.add(pareja)

        importes_bancarios[bancario] = (
            importes_bancarios.get(bancario, 0)
            + importe
        )

        importes_previstos[previsto] = (
            importes_previstos.get(previsto, 0)
            + importe
        )

    # La suma del grupo tampoco puede superar los saldos disponibles.
    for bancario, importe in importes_bancarios.items():
        _, pendiente = saldo_movimiento_bancario(
            bancario
        )

        if importe > pendiente:
            raise ConciliacionError(
                "El grupo supera el saldo disponible "
                "de un movimiento bancario."
            )

    for previsto, importe in importes_previstos.items():
        _, pendiente = saldo_movimiento_previsto(
            previsto
        )

        if importe > pendiente:
            raise ConciliacionError(
                "El grupo supera el saldo disponible "
                "de un movimiento previsto."
            )

    # Segunda fase: crear las asociaciones, ya validadas.
    conciliaciones = [
        asociar_movimientos(bancario, previsto, importe)
        for bancario, previsto, importe in asociaciones
    ]

    # Los estados se calculan una sola vez por movimiento afectado.
    for bancario in importes_bancarios:
        actualizar_estado_movimiento_bancario(
            bancario
        )

    for previsto in importes_previstos:
        actualizar_estado_movimiento_previsto(
            previsto
        )

    return conciliaciones



def deshacer_asociacion_bancaria(
    conciliacion: Conciliacion,
) -> None:
    """Elimina una asociación bancaria y recalcula los estados."""

    session = object_session(conciliacion)

    if session is None or conciliacion.id is None:
        raise ConciliacionError(
            "La asociación debe estar guardada para poder deshacerla."
        )

    bancario = conciliacion.movimiento_bancario
    previsto = conciliacion.movimiento_previsto

    # La asociación debe dejar de contar en los saldos inmediatamente.
    bancario.conciliaciones.remove(conciliacion)
    previsto.conciliaciones.remove(conciliacion)

    # La eliminación se confirmará con la transacción del llamador.
    session.delete(conciliacion)

    actualizar_estado_movimiento_bancario(
        bancario
    )
    actualizar_estado_movimiento_previsto(
        previsto
    )



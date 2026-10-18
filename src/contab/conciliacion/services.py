"""Implementa la lógica de negocio de la conciliación bancaria."""

import unicodedata

from datetime import date, timedelta
from sqlalchemy.orm import object_session
from dataclasses import dataclass, field
from itertools import combinations

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


@dataclass
class PropuestaConciliacion:
    """Representa una posible conciliación aún no confirmada."""

    bancarios: list[MovimientoBancario]
    previstos: list[MovimientoPrevisto]
    puntuacion: int
    motivos: list[str] = field(default_factory=list)



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


MAX_PROPUESTAS_CONFLICTO = 4

def _seleccionar_propuestas_agrupadas(
    propuestas: list[PropuestaConciliacion],
) -> list[PropuestaConciliacion]:
    """Selecciona la combinación compatible con mayor puntuación."""

    def incompatibles(primera, segunda):
        return (
            any(
                bancario is otro
                for bancario in primera.bancarios
                for otro in segunda.bancarios
            )
            or any(
                previsto is otro
                for previsto in primera.previstos
                for otro in segunda.previstos
            )
        )

    pendientes = list(propuestas)
    seleccionadas = []

    while pendientes:
        # Separar componentes de propuestas conectadas por conflictos.
        componente = [pendientes.pop(0)]

        indice = 0
        while indice < len(componente):
            actual = componente[indice]

            relacionadas = [
                propuesta
                for propuesta in pendientes
                if incompatibles(actual, propuesta)
            ]

            for propuesta in relacionadas:
                pendientes.remove(propuesta)
                componente.append(propuesta)

            indice += 1

        # Un conflicto con demasiadas alternativas requiere
        # revisión manual; no elegimos arbitrariamente.
        if len(componente) > MAX_PROPUESTAS_CONFLICTO:
            continue

        # Buscar la mejor combinación de propuestas compatibles.
        mejor_grupo = []
        mejor_puntuacion = 0
        empate = False

        for cantidad in range(1, len(componente) + 1):
            for combinacion in combinations(
                componente,
                cantidad,
            ):
                if any(
                    incompatibles(primera, segunda)
                    for primera, segunda in combinations(
                        combinacion,
                        2,
                    )
                ):
                    continue

                puntuacion = sum(
                    propuesta.puntuacion
                    for propuesta in combinacion
                )

                if puntuacion > mejor_puntuacion:
                    mejor_grupo = list(combinacion)
                    mejor_puntuacion = puntuacion
                    empate = False

                elif puntuacion == mejor_puntuacion:
                    empate = True

        # Ante dos soluciones óptimas distintas, no recomendar
        # arbitrariamente una de ellas.
        if not empate:
            seleccionadas.extend(mejor_grupo)

    seleccionadas.sort(
        key=lambda propuesta: propuesta.puntuacion,
        reverse=True,
    )

    return seleccionadas


def _bancario_identifica_contraparte(
    bancario: MovimientoBancario,
    previsto: MovimientoPrevisto,
    aliases_configurados: list[tuple[str, str, str]],
) -> bool:
    """Comprueba si el texto bancario identifica la contraparte prevista."""

    texto = _normalizar_texto_conciliacion(
        " ".join([
            bancario.tipo_original or "",
            bancario.descripcion_original or "",
            bancario.referencia_bancaria or "",
        ])
    )

    contraparte = _normalizar_texto_conciliacion(
        previsto.contraparte
    )

    if contraparte and contraparte in texto:
        return True

    aliases = _aliases_movimiento_previsto(
        previsto,
        aliases_configurados,
    )

    return any(
        alias_normalizado in texto
        for alias in aliases
        if (
            alias_normalizado
            := _normalizar_texto_conciliacion(alias)
        )
    )



def _puntuar_calidad_propuesta(
    propuesta: PropuestaConciliacion,
    aliases_configurados: list[tuple[str, str, str]],
) -> int:
    """Puntúa una propuesta sin favorecer los grupos grandes."""

    puntuaciones = []

    for bancario in propuesta.bancarios:
        texto_bancario = _normalizar_texto_conciliacion(
            " ".join([
                bancario.tipo_original or "",
                bancario.descripcion_original or "",
                bancario.referencia_bancaria or "",
            ])
        )

        for previsto in propuesta.previstos:
            puntuacion = 0

            fecha_desde = previsto.fecha_prevista_desde
            fecha_hasta = previsto.fecha_prevista_hasta

            if fecha_desde is not None:
                if fecha_hasta is None:
                    if bancario.fecha == fecha_desde:
                        puntuacion += 20
                elif fecha_desde <= bancario.fecha <= fecha_hasta:
                    puntuacion += 20

            contraparte = _normalizar_texto_conciliacion(
                previsto.contraparte
            )

            if contraparte and contraparte in texto_bancario:
                puntuacion += 50

            aliases = _aliases_movimiento_previsto(
                previsto,
                aliases_configurados,
            )

            if any(
                alias_normalizado
                and alias_normalizado != contraparte
                and alias_normalizado in texto_bancario
                for alias in aliases
                if (
                    alias_normalizado
                    := _normalizar_texto_conciliacion(alias)
                )
            ):
                puntuacion += 40

            puntuaciones.append(puntuacion)

    # Todos los grupos que recibimos son exactos.
    # La media evita favorecer a los grupos con más movimientos.
    return 100 + sum(puntuaciones) // len(puntuaciones)





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
    """Actualiza el estado según asociaciones y cierres confirmados."""

    asociado, pendiente = saldo_movimiento_bancario(
        movimiento
    )

    cierre_confirmado = any(
        conciliacion.cierra_bancario
        for conciliacion in movimiento.conciliaciones
    )

    if pendiente == 0 or cierre_confirmado:
        movimiento.estado = "CONCILIADO"
    elif asociado > 0:
        movimiento.estado = "PARCIAL"
    else:
        movimiento.estado = "PENDIENTE"


def actualizar_estado_movimiento_previsto(
    movimiento: MovimientoPrevisto,
) -> None:
    """Actualiza el estado sin perder una decisión de cierre."""

    if movimiento.metodo_conciliacion == "MANUAL":
        return

    asociado, pendiente = saldo_movimiento_previsto(
        movimiento
    )

    cierre_confirmado = any(
        conciliacion.cierra_previsto
        for conciliacion in movimiento.conciliaciones
    )

    if pendiente == 0 or cierre_confirmado:
        movimiento.estado = "CONCILIADO"
        movimiento.metodo_conciliacion = "INDIVIDUAL"
    elif asociado > 0:
        movimiento.estado = "PARCIAL"
        movimiento.metodo_conciliacion = "INDIVIDUAL"
    else:
        movimiento.estado = "PENDIENTE"
        movimiento.metodo_conciliacion = None


def preparar_asociaciones_cronologicas(
    bancarios: list[MovimientoBancario],
    previstos: list[MovimientoPrevisto],
) -> list[
    tuple[MovimientoBancario, MovimientoPrevisto, int]
]:
    """Distribuye saldos disponibles por orden cronológico.

    Admite 1:1, 1:n y m:1, pero no m:n.
    No crea asociaciones ni modifica movimientos.
    """

    if not bancarios or not previstos:
        raise ConciliacionError(
            "Debe seleccionarse al menos un movimiento de cada lado."
        )

    if len(bancarios) > 1 and len(previstos) > 1:
        raise ConciliacionError(
            "La conciliación m:n no está admitida."
        )

    if (
        len(set(bancarios)) != len(bancarios)
        or len(set(previstos)) != len(previstos)
    ):
        raise ConciliacionError(
            "La selección contiene movimientos repetidos."
        )

    if any(
        bancario.estado not in {"PENDIENTE", "PARCIAL"}
        for bancario in bancarios
    ):
        raise ConciliacionError(
            "Hay movimientos bancarios no disponibles."
        )

    if any(
        previsto.estado not in {"PENDIENTE", "PARCIAL"}
        for previsto in previstos
    ):
        raise ConciliacionError(
            "Hay movimientos previstos no disponibles."
        )

    naturalezas = {
        movimiento.naturaleza
        for movimiento in [*bancarios, *previstos]
    }

    if len(naturalezas) != 1:
        raise ConciliacionError(
            "Los movimientos deben tener la misma naturaleza."
        )

    # Los movimientos sin fecha prevista se sitúan al final.
    # El ID resuelve los empates de forma reproducible.
    previstos_ordenados = sorted(
        previstos,
        key=lambda previsto: (
            previsto.fecha_prevista_desde is None,
            previsto.fecha_prevista_desde or date.max,
            previsto.id or 0,
        ),
    )

    bancarios_ordenados = sorted(
        bancarios,
        key=lambda bancario: (
            bancario.fecha,
            bancario.id or 0,
        ),
    )

    saldos_bancarios = {
        bancario: saldo_movimiento_bancario(bancario)[1]
        for bancario in bancarios_ordenados
    }

    saldos_previstos = {
        previsto: saldo_movimiento_previsto(previsto)[1]
        for previsto in previstos_ordenados
    }

    if (
        any(saldo <= 0 for saldo in saldos_bancarios.values())
        or any(saldo <= 0 for saldo in saldos_previstos.values())
    ):
        raise ConciliacionError(
            "Todos los movimientos deben tener saldo disponible."
        )

    asociaciones = []

    indice_bancario = 0
    indice_previsto = 0

    while (
        indice_bancario < len(bancarios_ordenados)
        and indice_previsto < len(previstos_ordenados)
    ):
        bancario = bancarios_ordenados[indice_bancario]
        previsto = previstos_ordenados[indice_previsto]

        importe = min(
            saldos_bancarios[bancario],
            saldos_previstos[previsto],
        )

        # Validar la pareja utilizando las reglas existentes.
        validar_asociacion(
            bancario,
            previsto,
            importe,
        )

        asociaciones.append(
            (bancario, previsto, importe)
        )

        saldos_bancarios[bancario] -= importe
        saldos_previstos[previsto] -= importe

        if saldos_bancarios[bancario] == 0:
            indice_bancario += 1

        if saldos_previstos[previsto] == 0:
            indice_previsto += 1

    # Todos los movimientos seleccionados deben participar
    # en al menos una asociación. De lo contrario,
    # el usuario estaría confirmando una selección incompleta.
    bancarios_asociados = {
        bancario
        for bancario, _, _ in asociaciones
    }

    previstos_asociados = {
        previsto
        for _, previsto, _ in asociaciones
    }

    if (
        len(bancarios_asociados) != len(bancarios)
        or len(previstos_asociados) != len(previstos)
    ):
        raise ConciliacionError(
            "La selección contiene movimientos sin asociación. "
            "Selecciona únicamente los movimientos a conciliar."
        )

    return asociaciones


def confirmar_grupo_conciliacion(
    asociaciones: list[
        tuple[MovimientoBancario, MovimientoPrevisto, int]
    ],
    *,
    cerrar_diferencia: bool = False,
) -> list[Conciliacion]:
    """Confirma asociaciones, opcionalmente cerrando una diferencia 1:1."""

    if not asociaciones:
        raise ConciliacionError(
            "El grupo de conciliación no puede estar vacío."
        )

    if cerrar_diferencia:
        bancarios_grupo = {
            bancario
            for bancario, _, _ in asociaciones
        }
        previstos_grupo = {
            previsto
            for _, previsto, _ in asociaciones
        }

        if (
            len(bancarios_grupo) > 1
            and len(previstos_grupo) > 1
        ):
            raise ConciliacionError(
                "No se admite cerrar diferencias m:n."
            )

    importes_bancarios = {}
    importes_previstos = {}
    parejas = set()

    # Validar primero, sin modificar ningún movimiento.
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

    for bancario, importe in importes_bancarios.items():
        _, pendiente = saldo_movimiento_bancario(bancario)

        if importe > pendiente:
            raise ConciliacionError(
                "El grupo supera el saldo disponible "
                "de un movimiento bancario."
            )

    for previsto, importe in importes_previstos.items():
        _, pendiente = saldo_movimiento_previsto(previsto)

        if importe > pendiente:
            raise ConciliacionError(
                "El grupo supera el saldo disponible "
                "de un movimiento previsto."
            )

    movimiento_a_cerrar = None

    if cerrar_diferencia:
        residuos_bancarios = {
            bancario: (
                saldo_movimiento_bancario(bancario)[1]
                - importe
            )
            for bancario, importe in importes_bancarios.items()
        }

        residuos_previstos = {
            previsto: (
                saldo_movimiento_previsto(previsto)[1]
                - importe
            )
            for previsto, importe in importes_previstos.items()
        }

        bancarios_con_residuo = [
            bancario
            for bancario, residuo in residuos_bancarios.items()
            if residuo > 0
        ]

        previstos_con_residuo = [
            previsto
            for previsto, residuo in residuos_previstos.items()
            if residuo > 0
        ]

        # Aceptar una diferencia sólo debe cerrar
        # un saldo restante en uno de los lados.
        if (
            len(bancarios_con_residuo)
            + len(previstos_con_residuo)
            != 1
        ):
            raise ConciliacionError(
                "Para aceptar la diferencia debe quedar "
                "un único movimiento con saldo sin asociar."
            )

        if bancarios_con_residuo:
            movimiento_a_cerrar = bancarios_con_residuo[0]
        else:
            movimiento_a_cerrar = previstos_con_residuo[0]

    # Crear asociaciones después de completar la validación.
    conciliaciones = [
        asociar_movimientos(bancario, previsto, importe)
        for bancario, previsto, importe in asociaciones
    ]

    if cerrar_diferencia:
        if isinstance(
            movimiento_a_cerrar,
            MovimientoBancario,
        ):
            candidatas = [
                conciliacion
                for conciliacion in conciliaciones
                if (
                    conciliacion.movimiento_bancario
                    is movimiento_a_cerrar
                )
            ]

            candidatas[-1].cierra_bancario = True

        else:
            candidatas = [
                conciliacion
                for conciliacion in conciliaciones
                if (
                    conciliacion.movimiento_previsto
                    is movimiento_a_cerrar
                )
            ]

            candidatas[-1].cierra_previsto = True

    for bancario in importes_bancarios:
        actualizar_estado_movimiento_bancario(bancario)

    for previsto in importes_previstos:
        actualizar_estado_movimiento_previsto(previsto)

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


def buscar_propuestas_agrupadas(
    bancarios: list[MovimientoBancario],
    previstos: list[MovimientoPrevisto],
    aliases_configurados: (
        list[tuple[str, str, str]] | None
    ) = None,
    *,
    seleccionar: bool = True,
) -> list[PropuestaConciliacion]:
    """Busca propuestas exactas 1:2 y 2:1 sin modificar movimientos."""

    aliases_configurados = aliases_configurados or []
    propuestas = []

    bancarios_disponibles = [
        bancario
        for bancario in bancarios
        if (
            bancario.estado in {"PENDIENTE", "PARCIAL"}
            and saldo_movimiento_bancario(bancario)[1] > 0
        )
    ]

    previstos_disponibles = [
        previsto
        for previsto in previstos
        if (
            previsto.estado in {"PENDIENTE", "PARCIAL"}
            and saldo_movimiento_previsto(previsto)[1] > 0
        )
    ]

    MAX_ALTERNATIVAS_GRUPO = 8

    def puntuacion_pareja(bancario, previsto):
        if bancario.naturaleza != previsto.naturaleza:
            return None

        if not _fecha_compatible_conciliacion(
            bancario,
            previsto,
        ):
            return None

        fecha_desde = previsto.fecha_prevista_desde
        fecha_hasta = previsto.fecha_prevista_hasta

        puntuacion = 0

        if fecha_desde is not None:
            if fecha_hasta is None:
                if bancario.fecha == fecha_desde:
                    puntuacion += 20
            elif fecha_desde <= bancario.fecha <= fecha_hasta:
                puntuacion += 20

        contraparte = _normalizar_texto_conciliacion(
            previsto.contraparte
        )

        texto_bancario = _normalizar_texto_conciliacion(
            " ".join([
                bancario.tipo_original or "",
                bancario.descripcion_original or "",
                bancario.referencia_bancaria or "",
            ])
        )

        if contraparte and contraparte in texto_bancario:
            puntuacion += 50

        aliases = _aliases_movimiento_previsto(
            previsto,
            aliases_configurados,
        )

        for alias in aliases:
            alias_normalizado = _normalizar_texto_conciliacion(
                alias
            )

            if (
                alias_normalizado
                and alias_normalizado != contraparte
                and alias_normalizado in texto_bancario
            ):
                puntuacion += 40
                break

        return puntuacion

    # 1:n: un previsto y dos movimientos bancarios.
    for previsto in previstos_disponibles:
        importe_previsto = saldo_movimiento_previsto(
            previsto
        )[1]

        compatibles = [
            bancario
            for bancario in bancarios_disponibles
            if (
                bancario.naturaleza == previsto.naturaleza
                and _fecha_compatible_conciliacion(
                    bancario,
                    previsto,
                )
            )
        ]

        identificados = [
            bancario
            for bancario in compatibles
            if _bancario_identifica_contraparte(
                bancario,
                previsto,
                aliases_configurados,
            )
        ]

        # Si hay al menos dos movimientos identificados,
        # priorizamos ese conjunto y evitamos combinarlo
        # con ingresos de otras contrapartes.
        candidatos = (
            identificados
            if len(identificados) >= 2
            else compatibles
        )

        # Límite preventivo: no explorar grupos demasiado grandes.
        if len(candidatos) > MAX_ALTERNATIVAS_GRUPO:
            continue

        inicio_propuestas = len(propuestas)

        for grupo_bancario in combinations(
            candidatos,
            2,
        ):
            if sum(
                saldo_movimiento_bancario(bancario)[1]
                for bancario in grupo_bancario
            ) != importe_previsto:
                continue

            puntuaciones = [
                puntuacion_pareja(bancario, previsto)
                for bancario in grupo_bancario
            ]

            if any(
                puntuacion is None
                for puntuacion in puntuaciones
            ):
                continue

            propuestas.append(
                PropuestaConciliacion(
                    bancarios=list(grupo_bancario),
                    previstos=[previsto],
                    puntuacion=100 + sum(puntuaciones),
                    motivos=[
                        "La suma de los importes pendientes coincide.",
                        "Naturaleza y fechas compatibles.",
                    ],
                )
            )

            if (
                len(propuestas) - inicio_propuestas
                > MAX_ALTERNATIVAS_GRUPO
            ):
                break

        if (
            len(propuestas) - inicio_propuestas
            > MAX_ALTERNATIVAS_GRUPO
        ):
            del propuestas[inicio_propuestas:]

    # m:1: dos previstos y un movimiento bancario.
    for bancario in bancarios_disponibles:
        importe_bancario = saldo_movimiento_bancario(
            bancario
        )[1]

        for grupo_previsto in combinations(
            previstos_disponibles,
            2,
        ):
            if sum(
                saldo_movimiento_previsto(previsto)[1]
                for previsto in grupo_previsto
            ) != importe_bancario:
                continue

            puntuaciones = [
                puntuacion_pareja(bancario, previsto)
                for previsto in grupo_previsto
            ]

            if any(
                puntuacion is None
                for puntuacion in puntuaciones
            ):
                continue

            propuestas.append(
                PropuestaConciliacion(
                    bancarios=[bancario],
                    previstos=list(grupo_previsto),
                    puntuacion=100 + sum(puntuaciones),
                    motivos=[
                        "La suma de los importes pendientes coincide.",
                        "Naturaleza y fechas compatibles.",
                    ],
                )
            )

    if seleccionar:
        return _seleccionar_propuestas_agrupadas(propuestas)

    return propuestas


def buscar_propuestas_conciliacion(
    bancarios: list[MovimientoBancario],
    previstos: list[MovimientoPrevisto],
    aliases_configurados: (
        list[tuple[str, str, str]] | None
    ) = None,
) -> list[PropuestaConciliacion]:
    """Reúne propuestas exactas 1:1 y agrupadas y resuelve conflictos."""

    aliases_configurados = aliases_configurados or []

    propuestas = []

    # Primero, las propuestas individuales exactas.
    for bancario in bancarios:
        if bancario.estado not in {"PENDIENTE", "PARCIAL"}:
            continue

        _, pendiente_bancario = saldo_movimiento_bancario(
            bancario
        )

        if pendiente_bancario <= 0:
            continue

        for previsto in previstos:
            if previsto.estado not in {"PENDIENTE", "PARCIAL"}:
                continue

            if bancario.naturaleza != previsto.naturaleza:
                continue

            if not _fecha_compatible_conciliacion(
                bancario,
                previsto,
            ):
                continue

            _, pendiente_previsto = saldo_movimiento_previsto(
                previsto
            )

            if pendiente_bancario != pendiente_previsto:
                continue

            if pendiente_previsto <= 0:
                continue

            propuestas.append(
                PropuestaConciliacion(
                    bancarios=[bancario],
                    previstos=[previsto],
                    puntuacion=0,
                    motivos=[
                        "Importes pendientes coincidentes.",
                    ],
                )
            )

    # Incorporar las propuestas 1:2 y 2:1 existentes.
    propuestas.extend(
        buscar_propuestas_agrupadas(
            bancarios,
            previstos,
            aliases_configurados=aliases_configurados,
            seleccionar=False,
        )
    )

    # Todas las propuestas compiten con la misma escala.
    for propuesta in propuestas:
        propuesta.puntuacion = _puntuar_calidad_propuesta(
            propuesta,
            aliases_configurados,
        )


    # Resolver primero las propuestas exactas.
    seleccionadas = _seleccionar_propuestas_agrupadas(
        propuestas
    )

    # Los movimientos de una propuesta exacta no pueden
    # participar en una propuesta con diferencia.
    bancarios_ocupados = {
        bancario.id
        for propuesta in seleccionadas
        for bancario in propuesta.bancarios
    }

    previstos_ocupados = {
        previsto.id
        for propuesta in seleccionadas
        for previsto in propuesta.previstos
    }

    bancarios_libres = [
        bancario
        for bancario in bancarios
        if (
            bancario.estado in {"PENDIENTE", "PARCIAL"}
            and bancario.id not in bancarios_ocupados
        )
    ]

    previstos_libres = [
        previsto
        for previsto in previstos
        if (
            previsto.estado in {"PENDIENTE", "PARCIAL"}
            and previsto.id not in previstos_ocupados
        )
    ]

    # Buscar sólo correspondencias 1:1 con diferencia
    # y contraparte claramente identificada.
    candidatos_diferentes = []

    for bancario in bancarios_libres:
        _, pendiente_bancario = saldo_movimiento_bancario(
            bancario
        )

        if pendiente_bancario <= 0:
            continue

        for previsto in previstos_libres:
            _, pendiente_previsto = saldo_movimiento_previsto(
                previsto
            )

            if pendiente_previsto <= 0:
                continue

            if pendiente_bancario == pendiente_previsto:
                continue

            # Las diferencias superiores al 5 % del saldo previsto no se sugieren
            # automáticamente. Se calculan en céntimos, sin redondeos.
            diferencia = abs(
                pendiente_bancario - pendiente_previsto
            )

            if diferencia * 100 > pendiente_previsto * 5:
                continue

            if bancario.naturaleza != previsto.naturaleza:
                continue

            if not _fecha_compatible_conciliacion(
                bancario,
                previsto,
            ):
                continue

            if not _bancario_identifica_contraparte(
                bancario,
                previsto,
                aliases_configurados,
            ):
                continue

            candidatos_diferentes.append(
                (bancario, previsto)
            )

    # No sugerir correspondencias ambiguas:
    # cada movimiento debe tener un único candidato.
    for bancario, previsto in candidatos_diferentes:
        alternativas_bancario = sum(
            candidato_bancario.id == bancario.id
            for candidato_bancario, _ in candidatos_diferentes
        )

        alternativas_previsto = sum(
            candidato_previsto.id == previsto.id
            for _, candidato_previsto in candidatos_diferentes
        )

        if (
            alternativas_bancario != 1
            or alternativas_previsto != 1
        ):
            continue

        seleccionadas.append(
            PropuestaConciliacion(
                bancarios=[bancario],
                previstos=[previsto],
                puntuacion=0,
                motivos=["Correspondencia con diferencia."],
            )
        )

    return seleccionadas


def confirmar_propuesta_conciliacion(
    propuesta: PropuestaConciliacion,
) -> list[Conciliacion]:
    """Confirma una propuesta exacta 1:1, 1:n o m:1 sin hacer commit."""

    bancarios = propuesta.bancarios
    previstos = propuesta.previstos

    if not bancarios or not previstos:
        raise ConciliacionError(
            "La propuesta debe contener movimientos "
            "bancarios y previstos."
        )

    if len(bancarios) > 1 and len(previstos) > 1:
        raise ConciliacionError(
            "La confirmación automática m:n no está implementada."
        )

    asociaciones = []

    if len(previstos) == 1:
        # 1:1 o 1:n: cada bancario aporta su saldo pendiente.
        previsto = previstos[0]

        for bancario in bancarios:
            _, importe = saldo_movimiento_bancario(
                bancario
            )

            asociaciones.append(
                (bancario, previsto, importe)
            )

    else:
        # m:1: cada previsto recibe su saldo pendiente.
        bancario = bancarios[0]

        for previsto in previstos:
            _, importe = saldo_movimiento_previsto(
                previsto
            )

            asociaciones.append(
                (bancario, previsto, importe)
            )

    total_bancario = sum(
        saldo_movimiento_bancario(bancario)[1]
        for bancario in bancarios
    )

    total_previsto = sum(
        saldo_movimiento_previsto(previsto)[1]
        for previsto in previstos
    )

    if total_bancario != total_previsto:
        raise ConciliacionError(
            "Los saldos pendientes de la propuesta "
            "ya no coinciden."
        )

    return confirmar_grupo_conciliacion(
        asociaciones
    )



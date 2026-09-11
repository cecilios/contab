"""Importación y normalización de movimientos bancarios."""

import csv

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from io import StringIO
from sqlalchemy import select
from sqlalchemy.orm import Session

from contab.models import MovimientoBancario



@dataclass(frozen=True, slots=True)
class MovimientoBancarioImportado:
    """Representa un movimiento leído de cualquier CSV bancario."""

    fecha: date
    naturaleza: str
    importe: int
    tipo_original: str
    descripcion_original: str
    referencia_bancaria: str
    huella_importacion: str


class ImportacionBancariaError(ValueError):
    """Indica que un archivo bancario no tiene el formato esperado."""



def _crear_huella(
    *,
    fecha: date,
    importe_con_signo: int,
    tipo_original: str,
    descripcion_original: str,
    referencia_bancaria: str,
    ocurrencia: int,
) -> str:
    """Crea una huella estable para detectar importaciones repetidas."""

    contenido = "|".join(
        [
            fecha.isoformat(),
            str(importe_con_signo),
            tipo_original.strip(),
            descripcion_original.strip(),
            referencia_bancaria.strip(),
            str(ocurrencia),
        ]
    )

    return sha256(
        contenido.encode("utf-8")
    ).hexdigest()


def _importe_bancario_a_centimos(texto: str) -> int:
    """Convierte un importe bancario español a céntimos."""

    normalizado = (
        texto.strip()
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        importe = Decimal(normalizado)
    except InvalidOperation as exc:
        raise ImportacionBancariaError(
            f"El importe bancario '{texto}' no es válido."
        ) from exc

    return int(
        importe * 100
    )


def leer_csv_ibercaja(
    contenido: str,
) -> list[MovimientoBancarioImportado]:
    """Lee y normaliza los movimientos de un CSV de Ibercaja."""

    lector = csv.reader(
        StringIO(contenido),
        delimiter=";",
    )

    cabecera_esperada = [
        "Nº Orden",
        "Fecha Oper",
        "Fecha Valor",
        "Concepto",
        "Descripción",
        "Referencia",
        "Importe",
        "Saldo",
    ]

    movimientos = []
    cabecera_encontrada = False
    ocurrencias: defaultdict[tuple, int] = defaultdict(int)

    for fila in lector:
        if fila == cabecera_esperada:
            cabecera_encontrada = True
            continue

        if not cabecera_encontrada:
            continue

        if not fila or not any(
            valor.strip()
            for valor in fila
        ):
            continue

        if len(fila) != len(cabecera_esperada):
            raise ImportacionBancariaError(
                "Una fila del CSV de Ibercaja no tiene "
                "el número de columnas esperado."
            )

        try:
            fecha = datetime.strptime(
                fila[1].strip(),
                "%d-%m-%Y",
            ).date()
        except ValueError as exc:
            raise ImportacionBancariaError(
                f"La fecha bancaria '{fila[1]}' no es válida."
            ) from exc

        importe_con_signo = (
            _importe_bancario_a_centimos(fila[6])
        )
        if importe_con_signo == 0:
            raise ImportacionBancariaError(
                "El importe bancario debe ser distinto de cero."
            )
        tipo_original = fila[3].strip()
        descripcion_original = fila[4].strip()
        referencia_bancaria = fila[5].strip()

        clave = (
            fecha,
            importe_con_signo,
            tipo_original,
            descripcion_original,
            referencia_bancaria,
        )
        ocurrencias[clave] += 1

        movimientos.append(
            MovimientoBancarioImportado(
                fecha=fecha,
                naturaleza=(
                    "INGRESO"
                    if importe_con_signo > 0
                    else "GASTO"
                ),
                importe=abs(importe_con_signo),
                tipo_original=tipo_original,
                descripcion_original=descripcion_original,
                referencia_bancaria=referencia_bancaria,
                huella_importacion=_crear_huella(
                    fecha=fecha,
                    importe_con_signo=importe_con_signo,
                    tipo_original=tipo_original,
                    descripcion_original=descripcion_original,
                    referencia_bancaria=referencia_bancaria,
                    ocurrencia=ocurrencias[clave],
                ),
            )
        )

    if not cabecera_encontrada:
        raise ImportacionBancariaError(
            "El archivo no tiene la cabecera esperada "
            "para un CSV de Ibercaja."
        )

    return movimientos


def leer_csv_caixabank(
    contenido: str,
) -> list[MovimientoBancarioImportado]:
    """Lee y normaliza los movimientos de un CSV de CaixaBank."""

    lector = csv.reader(
        StringIO(contenido),
        delimiter=";",
    )

    cabecera_esperada = [
        "Fecha",
        "Fecha valor",
        "Movimiento",
        "Más datos",
        "Importe",
        "Saldo",
    ]

    movimientos = []
    cabecera_encontrada = False
    ocurrencias: defaultdict[tuple, int] = defaultdict(int)

    for fila in lector:
        if fila == cabecera_esperada:
            cabecera_encontrada = True
            continue

        if not cabecera_encontrada:
            continue

        if not fila or not any(
            valor.strip()
            for valor in fila
        ):
            continue

        if len(fila) != len(cabecera_esperada):
            raise ImportacionBancariaError(
                "Una fila del CSV de CaixaBank no tiene "
                "el número de columnas esperado."
            )

        try:
            fecha = datetime.strptime(
                fila[0].strip(),
                "%d/%m/%Y",
            ).date()
        except ValueError as exc:
            raise ImportacionBancariaError(
                f"La fecha bancaria '{fila[0]}' no es válida."
            ) from exc

        importe_con_signo = (
            _importe_bancario_a_centimos(fila[4])
        )

        if importe_con_signo == 0:
            raise ImportacionBancariaError(
                "El importe bancario debe ser distinto de cero."
            )

        tipo_original = fila[2].strip()
        descripcion_original = fila[3].strip()
        referencia_bancaria = ""

        clave = (
            fecha,
            importe_con_signo,
            tipo_original,
            descripcion_original,
            referencia_bancaria,
        )
        ocurrencias[clave] += 1

        movimientos.append(
            MovimientoBancarioImportado(
                fecha=fecha,
                naturaleza=(
                    "INGRESO"
                    if importe_con_signo > 0
                    else "GASTO"
                ),
                importe=abs(importe_con_signo),
                tipo_original=tipo_original,
                descripcion_original=descripcion_original,
                referencia_bancaria="",
                huella_importacion=_crear_huella(
                    fecha=fecha,
                    importe_con_signo=importe_con_signo,
                    tipo_original=tipo_original,
                    descripcion_original=descripcion_original,
                    referencia_bancaria="",
                    ocurrencia=ocurrencias[clave],
                ),
            )
        )

    if not cabecera_encontrada:
        raise ImportacionBancariaError(
            "El archivo no tiene la cabecera esperada "
            "para un CSV de CaixaBank."
        )

    return movimientos


def preparar_movimientos_bancarios(
    *,
    session: Session,
    movimientos: Sequence[MovimientoBancarioImportado],
) -> list[MovimientoBancario]:
    """Prepara sólo los movimientos que aún no se han importado."""

    if not movimientos:
        return []

    huellas_importadas = {
        movimiento.huella_importacion
        for movimiento in movimientos
    }

    huellas_existentes = set(
        session.scalars(
            select(
                MovimientoBancario.huella_importacion
            ).where(
                MovimientoBancario.huella_importacion.in_(
                    huellas_importadas
                )
            )
        ).all()
    )

    nuevos = []

    for movimiento in movimientos:
        if (
            movimiento.huella_importacion
            in huellas_existentes
        ):
            continue

        nuevos.append(
            MovimientoBancario(
                fecha=movimiento.fecha,
                naturaleza=movimiento.naturaleza,
                importe=movimiento.importe,
                tipo_original=movimiento.tipo_original,
                descripcion_original=(
                    movimiento.descripcion_original
                ),
                referencia_bancaria=(
                    movimiento.referencia_bancaria
                ),
                huella_importacion=(
                    movimiento.huella_importacion
                ),
                estado="PENDIENTE",
            )
        )

        # Evita repetir una huella duplicada dentro
        # de la misma colección recibida.
        huellas_existentes.add(
            movimiento.huella_importacion
        )

    return nuevos


LECTORES_BANCARIOS = {
    "IBERCAJA": leer_csv_ibercaja,
    "CAIXABANK": leer_csv_caixabank,
}


def leer_csv_bancario(
    *,
    banco: str,
    contenido: str,
) -> list[MovimientoBancarioImportado]:
    """Lee un CSV utilizando el formato del banco configurado."""

    codigo_banco = banco.strip().upper()

    try:
        lector = LECTORES_BANCARIOS[codigo_banco]
    except KeyError as exc:
        raise ImportacionBancariaError(
            f"El banco '{banco}' no está soportado."
        ) from exc

    return lector(contenido)



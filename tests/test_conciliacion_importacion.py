import pytest

from datetime import date
from pathlib import Path
from dataclasses import dataclass
from sqlalchemy import select

from contab.conciliacion.importacion import (
    _crear_huella,
    ImportacionBancariaError,
    MovimientoBancarioImportado,
    leer_csv_caixabank,
    leer_csv_ibercaja,
    preparar_movimientos_bancarios,
)
from contab.models import MovimientoBancario


DATOS_TEST = Path(__file__).parent / "datos"


def test_crear_huella_importacion_es_estable() -> None:
    """La misma operación produce siempre la misma huella."""

    datos = {
        "fecha": date(2026, 9, 3),
        "importe_con_signo": 160000,
        "tipo_original": "TRANSFERENCIA OTRA ENTIDAD",
        "descripcion_original": "Alquiler septiembre",
        "referencia_bancaria": "40278053846",
        "ocurrencia": 1,
    }

    primera = _crear_huella(**datos)
    segunda = _crear_huella(**datos)

    assert primera == segunda
    assert len(primera) == 64


def test_crear_huella_distingue_operaciones_identicas() -> None:
    """Dos operaciones iguales pueden coexistir en un mismo CSV."""

    datos = {
        "fecha": date(2026, 9, 3),
        "importe_con_signo": -4350,
        "tipo_original": "RECIBO",
        "descripcion_original": "Comunidad",
        "referencia_bancaria": "",
    }

    primera = _crear_huella(
        **datos,
        ocurrencia=1,
    )
    segunda = _crear_huella(
        **datos,
        ocurrencia=2,
    )

    assert primera != segunda


def test_leer_csv_ibercaja_normaliza_movimientos() -> None:
    """Lee el preámbulo y normaliza ingresos y gastos de Ibercaja."""

    contenido = """;;;;;;;
Consulta Movimientos de la Cuenta: ;;;;;;**8271;
Fecha de generación del informe: 06/09/2026;;;;;;;
;;;;;;;
Nº Orden;Fecha Oper;Fecha Valor;Concepto;Descripción;Referencia;Importe;Saldo
1;03-09-2026;03-09-2026;TRANSFERENCIA OTRA ENTIDAD;  Alquiler septiembre  ;40278053846;1.600,00;15.201,53
2;02-09-2026;02-09-2026;RECIBO ENERGIA;  CURENERGÍA COMERCIALIZADOR  ;;-125,37;13.601,53
"""

    movimientos = leer_csv_ibercaja(contenido)

    assert len(movimientos) == 2

    ingreso = movimientos[0]

    assert ingreso.fecha == date(2026, 9, 3)
    assert ingreso.naturaleza == "INGRESO"
    assert ingreso.importe == 160000
    assert ingreso.tipo_original == (
        "TRANSFERENCIA OTRA ENTIDAD"
    )
    assert ingreso.descripcion_original == (
        "Alquiler septiembre"
    )
    assert ingreso.referencia_bancaria == "40278053846"
    assert len(ingreso.huella_importacion) == 64

    gasto = movimientos[1]

    assert gasto.fecha == date(2026, 9, 2)
    assert gasto.naturaleza == "GASTO"
    assert gasto.importe == 12537
    assert gasto.tipo_original == "RECIBO ENERGIA"
    assert gasto.descripcion_original == (
        "CURENERGÍA COMERCIALIZADOR"
    )
    assert gasto.referencia_bancaria == ""
    assert len(gasto.huella_importacion) == 64


def test_leer_csv_ibercaja_distingue_movimientos_iguales() -> None:
    """Dos movimientos bancarios iguales reciben huellas diferentes."""

    contenido = """Nº Orden;Fecha Oper;Fecha Valor;Concepto;Descripción;Referencia;Importe;Saldo
1;03-09-2026;03-09-2026;RECIBO;Comunidad;;-100,00;1.000,00
2;03-09-2026;03-09-2026;RECIBO;Comunidad;;-100,00;900,00
"""

    movimientos = leer_csv_ibercaja(contenido)

    assert len(movimientos) == 2
    assert (
        movimientos[0].huella_importacion
        != movimientos[1].huella_importacion
    )


def test_leer_csv_ibercaja_rechaza_importe_cero() -> None:
    """Un movimiento bancario debe tener un importe distinto de cero."""

    contenido = """Nº Orden;Fecha Oper;Fecha Valor;Concepto;Descripción;Referencia;Importe;Saldo
1;03-09-2026;03-09-2026;RECIBO;Comunidad;;0,00;1.000,00
"""

    with pytest.raises(
        ImportacionBancariaError,
        match="distinto de cero",
    ):
        leer_csv_ibercaja(contenido)


def test_leer_csv_caixabank_normaliza_movimientos() -> None:
    """Normaliza ingresos y gastos de un CSV de CaixaBank."""

    contenido = """Movimientos de la cuenta ES12 3456;;;;;
Importes expresados en euros;;;;;
Fecha;Fecha valor;Movimiento;Más datos;Importe;Saldo
05/09/2026;07/09/2026;TRANSF. A SU FAVOR;Alquiler septiembre;1.121,16;6.729,54
03/09/2026;03/09/2026;C.P.MONTILLA 3;Recibo de fincas, alquileres;-43,50;5.619,32
01/09/2026;01/09/2026;TRASPASO;;2.500,00;5.662,82
"""

    movimientos = leer_csv_caixabank(contenido)

    assert len(movimientos) == 3

    ingreso = movimientos[0]

    assert ingreso.fecha == date(2026, 9, 5)
    assert ingreso.naturaleza == "INGRESO"
    assert ingreso.importe == 112116
    assert ingreso.tipo_original == "TRANSF. A SU FAVOR"
    assert ingreso.descripcion_original == (
        "Alquiler septiembre"
    )
    assert ingreso.referencia_bancaria == ""

    gasto = movimientos[1]

    assert gasto.fecha == date(2026, 9, 3)
    assert gasto.naturaleza == "GASTO"
    assert gasto.importe == 4350
    assert gasto.tipo_original == "C.P.MONTILLA 3"
    assert gasto.descripcion_original == (
        "Recibo de fincas, alquileres"
    )

    ingreso_sin_descripcion = movimientos[2]

    assert ingreso_sin_descripcion.importe == 250000
    assert ingreso_sin_descripcion.descripcion_original == ""


def test_leer_csv_real_ibercaja() -> None:
    """Lee completamente el CSV anonimizado de Ibercaja."""

    contenido = (
        DATOS_TEST / "movimientos-ibercaja.csv"
    ).read_text(encoding="utf-8")

    movimientos = leer_csv_ibercaja(contenido)

    assert len(movimientos) == 51
    assert all(
        movimiento.importe > 0
        for movimiento in movimientos
    )
    assert len(
        {
            movimiento.huella_importacion
            for movimiento in movimientos
        }
    ) == len(movimientos)


def test_leer_csv_real_caixabank() -> None:
    """Lee completamente el CSV anonimizado de CaixaBank."""

    contenido = (
        DATOS_TEST / "movimientos-caixabank.csv"
    ).read_text(encoding="utf-8")

    movimientos = leer_csv_caixabank(contenido)

    assert len(movimientos) == 36
    assert all(
        movimiento.importe > 0
        for movimiento in movimientos
    )
    assert len(
        {
            movimiento.huella_importacion
            for movimiento in movimientos
        }
    ) == len(movimientos)


def test_preparar_movimientos_omite_huellas_existentes(
    session,
) -> None:
    """Sólo prepara movimientos que no estaban importados."""

    # Guardamos previamente uno de los movimientos.
    existente = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="INGRESO",
        importe=160000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Alquiler septiembre",
        referencia_bancaria="123",
        huella_importacion="a" * 64,
    )
    session.add(existente)
    session.commit()

    importados = [
        MovimientoBancarioImportado(
            fecha=date(2026, 9, 3),
            naturaleza="INGRESO",
            importe=160000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="Alquiler septiembre",
            referencia_bancaria="123",
            huella_importacion="a" * 64,
        ),
        MovimientoBancarioImportado(
            fecha=date(2026, 9, 4),
            naturaleza="GASTO",
            importe=5000,
            tipo_original="RECIBO",
            descripcion_original="Comunidad",
            referencia_bancaria="456",
            huella_importacion="b" * 64,
        ),
    ]

    # Preparamos y persistimos sólo los nuevos.
    nuevos = preparar_movimientos_bancarios(
        session=session,
        movimientos=importados,
    )

    session.add_all(nuevos)
    session.commit()

    assert len(nuevos) == 1
    assert nuevos[0].huella_importacion == "b" * 64

    guardados = session.scalars(
        select(MovimientoBancario)
    ).all()

    assert len(guardados) == 2



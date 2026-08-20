"""Pruebas de los modelos ORM Factura y FacturaLinea."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import Factura, FacturaLinea


def test_crear_factura_con_lineas(session, contrato) -> None:
    """Comprueba que una factura puede contener varias líneas económicas."""
    factura = Factura(
        contrato=contrato,
        numero_secuencia=1,
        anio=2026,
        numero_factura="01/2026A1",
        fecha_emision=date(2026, 9, 1),
        periodo=date(2026, 9, 1),
        base=108347,
        iva_porcentaje=2100,
        iva_importe=22753,
        retencion_porcentaje=1900,
        retencion_importe=20586,
        total=110514,
        ruta_pdf="facturas/01-2026A1.pdf",
    )

    factura.lineas.extend(
        [
            FacturaLinea(
                orden=1,
                tipo="RENTA",
                concepto="Alquiler del local por el mes de septiembre de 2026",
                importe=100000,
            ),
            FacturaLinea(
                orden=2,
                tipo="REPERCUSION_GASTO",
                concepto="Agua del 15/03/2026 al 18/05/2026",
                importe=8347,
            ),
        ]
    )

    session.add(factura)
    session.commit()

    assert factura.id is not None
    assert factura.estado == "EMITIDA"
    assert len(factura.lineas) == 2
    assert factura.lineas[0].importe == 100000
    assert factura.lineas[1].importe == 8347


def test_numero_factura_debe_ser_unico(session, contrato) -> None:
    """Comprueba que no pueden existir dos facturas con el mismo número."""
    factura_1 = Factura(
        contrato=contrato,
        numero_secuencia=1,
        anio=2026,
        numero_factura="01/2026A1",
        fecha_emision=date(2026, 1, 1),
        periodo=date(2026, 1, 1),
        base=100000,
        iva_porcentaje=0,
        iva_importe=0,
        retencion_porcentaje=0,
        retencion_importe=0,
        total=100000,
        ruta_pdf="factura1.pdf",
    )

    factura_2 = Factura(
        contrato=contrato,
        numero_secuencia=2,
        anio=2026,
        numero_factura="01/2026A1",
        fecha_emision=date(2026, 2, 1),
        periodo=date(2026, 2, 1),
        base=100000,
        iva_porcentaje=0,
        iva_importe=0,
        retencion_porcentaje=0,
        retencion_importe=0,
        total=100000,
        ruta_pdf="factura2.pdf",
    )

    session.add_all([factura_1, factura_2])

    with pytest.raises(IntegrityError):
        session.commit()


def test_factura_linea_rechaza_tipo_desconocido(session, contrato) -> None:
    """Comprueba que una línea sólo admite los tipos definidos."""
    factura = Factura(
        contrato=contrato,
        numero_secuencia=1,
        anio=2026,
        numero_factura="01/2026A1",
        fecha_emision=date(2026, 1, 1),
        periodo=date(2026, 1, 1),
        base=100000,
        iva_porcentaje=0,
        iva_importe=0,
        retencion_porcentaje=0,
        retencion_importe=0,
        total=100000,
        ruta_pdf="factura.pdf",
    )

    factura.lineas.append(
        FacturaLinea(
            orden=1,
            tipo="DESCONOCIDO",
            concepto="Concepto",
            importe=100000,
        )
    )

    session.add(factura)

    with pytest.raises(IntegrityError):
        session.commit()


def test_factura_linea_admite_diferencia_negativa(session, contrato) -> None:
    """Comprueba que una diferencia de revisión puede tener importe negativo."""
    factura = Factura(
        contrato=contrato,
        numero_secuencia=1,
        anio=2026,
        numero_factura="01/2026A1",
        fecha_emision=date(2026, 1, 1),
        periodo=date(2026, 1, 1),
        base=97500,
        iva_porcentaje=0,
        iva_importe=0,
        retencion_porcentaje=0,
        retencion_importe=0,
        total=97500,
        ruta_pdf="factura.pdf",
    )

    factura.lineas.extend(
        [
            FacturaLinea(
                orden=1,
                tipo="RENTA",
                concepto="Alquiler",
                importe=100000,
            ),
            FacturaLinea(
                orden=2,
                tipo="DIFERENCIA_REVISION",
                concepto="Diferencia de revisión",
                importe=-2500,
            ),
        ]
    )

    session.add(factura)
    session.commit()

    assert factura.lineas[1].importe == -2500


def test_factura_no_admite_estado_desconocido(session, contrato) -> None:
    """Comprueba que sólo pueden almacenarse estados de factura conocidos."""
    factura = Factura(
        contrato=contrato,
        numero_secuencia=1,
        anio=2026,
        numero_factura="01/2026A1",
        fecha_emision=date(2026, 1, 1),
        periodo=date(2026, 1, 1),
        base=100000,
        iva_porcentaje=0,
        iva_importe=0,
        retencion_porcentaje=0,
        retencion_importe=0,
        total=100000,
        estado="DESCONOCIDO",
        ruta_pdf="factura.pdf",
    )

    session.add(factura)

    with pytest.raises(IntegrityError):
        session.commit()

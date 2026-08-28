"""Pruebas del modelo ORM MovimientoPrevisto."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import ApunteContable, MovimientoPrevisto


@pytest.fixture
def apunte(session, inmueble) -> ApunteContable:
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 9, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler de septiembre",
        base=100000,
        iva_importe=21000,
        retencion_importe=19000,
        total=102000,
        tercero_nombre="Empresa inquilina",
        tercero_nif="B12345678",
        referencia_documento="Factura 01/2026A1",
    )

    session.add(apunte)
    session.commit()

    return apunte


def test_crear_movimiento_previsto_sin_apunte(
    session,
    inmueble,
) -> None:
    movimiento = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista=date(2026, 9, 5),
        naturaleza="GASTO",
        concepto="Recibo de agua",
        importe_esperado=5000,
    )

    session.add(movimiento)
    session.commit()

    assert movimiento.id is not None
    assert movimiento.apunte is None
    assert movimiento.contrato is None
    assert movimiento.contraparte == ""
    assert movimiento.estado == "PENDIENTE"


def test_crear_movimiento_previsto_con_apunte_y_contrato(
    session,
    inmueble,
    contrato,
    apunte,
) -> None:
    movimiento = MovimientoPrevisto(
        inmueble=inmueble,
        contrato=contrato,
        apunte=apunte,
        fecha_prevista=date(2026, 9, 1),
        naturaleza="INGRESO",
        concepto="Cobro del alquiler",
        importe_esperado=102000,
        contraparte="Empresa inquilina",
    )

    session.add(movimiento)
    session.commit()

    assert movimiento.inmueble is inmueble
    assert movimiento.contrato is contrato
    assert movimiento.apunte is apunte
    assert movimiento in apunte.movimientos_previstos


def test_un_apunte_admite_varios_movimientos_previstos(
    session,
    inmueble,
    apunte,
) -> None:
    primero = MovimientoPrevisto(
        inmueble=inmueble,
        apunte=apunte,
        fecha_prevista=date(2026, 9, 1),
        naturaleza="INGRESO",
        concepto="Primer pago",
        importe_esperado=50000,
    )

    segundo = MovimientoPrevisto(
        inmueble=inmueble,
        apunte=apunte,
        fecha_prevista=date(2026, 9, 15),
        naturaleza="INGRESO",
        concepto="Segundo pago",
        importe_esperado=52000,
    )

    session.add_all([primero, segundo])
    session.commit()

    assert len(apunte.movimientos_previstos) == 2


def test_movimiento_previsto_rechaza_naturaleza_desconocida(
    session,
    inmueble,
) -> None:
    movimiento = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista=date(2026, 9, 1),
        naturaleza="DESCONOCIDA",
        concepto="Concepto",
        importe_esperado=10000,
    )

    session.add(movimiento)

    with pytest.raises(IntegrityError):
        session.commit()


def test_movimiento_previsto_rechaza_importe_negativo(
    session,
    inmueble,
) -> None:
    movimiento = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista=date(2026, 9, 1),
        naturaleza="GASTO",
        concepto="Concepto",
        importe_esperado=-1,
    )

    session.add(movimiento)

    with pytest.raises(IntegrityError):
        session.commit()


def test_movimiento_previsto_rechaza_estado_desconocido(
    session,
    inmueble,
) -> None:
    movimiento = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista=date(2026, 9, 1),
        naturaleza="INGRESO",
        concepto="Concepto",
        importe_esperado=10000,
        estado="DESCONOCIDO",
    )

    session.add(movimiento)

    with pytest.raises(IntegrityError):
        session.commit()

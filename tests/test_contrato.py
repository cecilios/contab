"""Pruebas del modelo ORM Contrato."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import Contrato, Inmueble


def crear_inmueble(session) -> Inmueble:
    """Crea un inmueble válido para utilizarlo en las pruebas de contratos."""
    inmueble = Inmueble(
        referencia="LOCAL-1",
        codigo_facturacion="A1",
        descripcion="Local comercial",
        direccion="Dirección de prueba",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    session.add(inmueble)
    session.commit()

    return inmueble


def test_crear_contrato_asociado_a_inmueble(session) -> None:
    """Comprueba que un contrato puede asociarse correctamente a un inmueble."""
    inmueble = crear_inmueble(session)

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2026, 1, 15),
        fecha_vencimiento=date(2031, 1, 14),
        fecha_inicio_facturacion=date(2026, 2, 1),
        fianza=200000,
        iva_porcentaje=2100,
        retencion_porcentaje=1900,
        direccion_facturacion="Dirección de facturación",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler del local",
    )

    session.add(contrato)
    session.commit()

    assert contrato.id is not None
    assert contrato.inmueble_id == inmueble.id
    assert contrato.inmueble is inmueble
    assert contrato in inmueble.contratos
    assert contrato.fecha_fin is None
    assert contrato.fianza == 200000


def test_contrato_requiere_inmueble_existente(session) -> None:
    """Comprueba que no puede guardarse un contrato con un inmueble inexistente."""
    contrato = Contrato(
        inmueble_id=9999,
        fecha_inicio=date(2026, 1, 1),
        fecha_vencimiento=date(2030, 12, 31),
        fecha_inicio_facturacion=date(2026, 1, 1),
        fianza=100000,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )

    session.add(contrato)

    with pytest.raises(IntegrityError):
        session.commit()


def test_vencimiento_no_puede_ser_anterior_al_inicio(session) -> None:
    """Comprueba que el vencimiento no puede preceder al inicio del contrato."""
    inmueble = crear_inmueble(session)

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2026, 6, 1),
        fecha_vencimiento=date(2026, 5, 31),
        fecha_inicio_facturacion=date(2026, 6, 1),
        fianza=100000,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )

    session.add(contrato)

    with pytest.raises(IntegrityError):
        session.commit()


def test_inicio_facturacion_no_puede_ser_anterior_al_contrato(session) -> None:
    """Comprueba que la facturación no puede comenzar antes que el contrato."""
    inmueble = crear_inmueble(session)

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2026, 6, 15),
        fecha_vencimiento=date(2030, 6, 14),
        fecha_inicio_facturacion=date(2026, 6, 1),
        fianza=100000,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )

    session.add(contrato)

    with pytest.raises(IntegrityError):
        session.commit()

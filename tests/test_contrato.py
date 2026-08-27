"""Pruebas del modelo ORM Contrato."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import Contrato, Inmueble


def test_crear_contrato_asociado_a_inmueble(session, inmueble) -> None:
    """Comprueba que un contrato puede asociarse correctamente a un inmueble."""

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2026, 1, 15),
        fecha_vencimiento=date(2031, 1, 14),
        genera_factura=True,
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
        genera_factura=True,
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


def test_vencimiento_no_puede_ser_anterior_al_inicio(session, inmueble) -> None:
    """Comprueba que el vencimiento no puede preceder al inicio del contrato."""

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2026, 6, 1),
        fecha_vencimiento=date(2026, 5, 31),
        genera_factura=True,
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


def test_inicio_facturacion_no_puede_ser_anterior_al_contrato(session, inmueble) -> None:
    """Comprueba que la facturación no puede comenzar antes que el contrato."""
 
    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2026, 6, 15),
        fecha_vencimiento=date(2030, 6, 14),
        genera_factura=True,
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


@pytest.mark.parametrize(
    "genera_factura",
    [True, False],
)
def test_contrato_acepta_genera_factura(
    session,
    contrato,
    genera_factura,
) -> None:
    contrato.genera_factura = genera_factura

    session.add(contrato)
    session.commit()

    assert contrato.genera_factura is genera_factura



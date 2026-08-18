"""Pruebas del histórico de rentas ordinarias de los contratos."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import Contrato, Inmueble, RentaContrato


def crear_contrato(session) -> Contrato:
    """Crea un contrato válido para utilizarlo en las pruebas de rentas."""
    inmueble = Inmueble(
        referencia="LOCAL-1",
        codigo_facturacion="A1",
        descripcion="Local comercial",
        direccion="Dirección de prueba",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2026, 1, 15),
        fecha_vencimiento=date(2030, 12, 31),
        fecha_inicio_facturacion=date(2026, 2, 1),
        fianza=100000,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )

    session.add(contrato)
    session.commit()

    return contrato


def test_crear_historico_de_rentas(session) -> None:
    """Comprueba que un contrato puede almacenar sucesivas rentas ordinarias."""
    contrato = crear_contrato(session)

    renta_inicial = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 2, 1),
        importe=100000,
    )
    renta_revisada = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2027, 2, 1),
        importe=102300,
    )

    session.add_all([renta_inicial, renta_revisada])
    session.commit()

    assert renta_inicial.id is not None
    assert renta_revisada.id is not None
    assert renta_inicial.contrato is contrato
    assert len(contrato.rentas) == 2


def test_no_admite_dos_rentas_desde_misma_fecha(session) -> None:
    """Comprueba que un contrato no puede tener dos rentas desde el mismo mes."""
    contrato = crear_contrato(session)

    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=100000,
            ),
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=110000,
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_renta_no_admite_importe_negativo(session) -> None:
    """Comprueba que una renta ordinaria no puede tener importe negativo."""
    contrato = crear_contrato(session)

    session.add(
        RentaContrato(
            contrato=contrato,
            fecha_desde=date(2026, 2, 1),
            importe=-1,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()

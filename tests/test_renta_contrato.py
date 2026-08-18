"""Pruebas del histórico de rentas ordinarias de los contratos."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import Contrato, Inmueble, RentaContrato


def test_crear_historico_de_rentas(session, contrato) -> None:
    """Comprueba que un contrato puede almacenar sucesivas rentas ordinarias."""

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


def test_no_admite_dos_rentas_desde_misma_fecha(session, contrato) -> None:
    """Comprueba que un contrato no puede tener dos rentas desde el mismo mes."""

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


def test_renta_no_admite_importe_negativo(session, contrato) -> None:
    """Comprueba que una renta ordinaria no puede tener importe negativo."""

    session.add(
        RentaContrato(
            contrato=contrato,
            fecha_desde=date(2026, 2, 1),
            importe=-1,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()

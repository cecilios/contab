"""Pruebas de la lógica de negocio relacionada con contratos y rentas."""

from datetime import date

import pytest

from contab.models import RentaContrato
from contab.contratos.services import RentaNoDisponibleError, renta_vigente


def test_renta_vigente_devuelve_renta_inicial(session, contrato) -> None:
    """Comprueba que se obtiene la renta inicial antes de cualquier revisión."""
    renta = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 2, 1),
        importe=100000,
    )

    session.add(renta)
    session.commit()

    resultado = renta_vigente(contrato, date(2026, 9, 15))

    assert resultado is renta


def test_renta_vigente_devuelve_ultima_renta_aplicable(session, contrato) -> None:
    """Comprueba que se utiliza la última renta vigente en la fecha consultada."""
    renta_inicial = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 2, 1),
        importe=100000,
    )
    renta_revisada = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2027, 2, 1),
        importe=102500,
    )

    session.add_all([renta_inicial, renta_revisada])
    session.commit()

    resultado = renta_vigente(contrato, date(2027, 8, 20))

    assert resultado is renta_revisada
    assert resultado.importe == 102500


def test_renta_vigente_respeta_fecha_exacta_de_cambio(session, contrato) -> None:
    """Comprueba que una nueva renta entra en vigor exactamente en fecha_desde."""
    renta_inicial = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 2, 1),
        importe=100000,
    )
    renta_revisada = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2027, 2, 1),
        importe=102500,
    )

    session.add_all([renta_inicial, renta_revisada])
    session.commit()

    assert renta_vigente(contrato, date(2027, 1, 31)) is renta_inicial
    assert renta_vigente(contrato, date(2027, 2, 1)) is renta_revisada


def test_renta_vigente_falla_si_no_hay_renta_aplicable(session, contrato) -> None:
    """Comprueba que consultar antes de la primera renta produce un error."""
    renta = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 2, 1),
        importe=100000,
    )

    session.add(renta)
    session.commit()

    with pytest.raises(RentaNoDisponibleError):
        renta_vigente(contrato, date(2026, 1, 15))

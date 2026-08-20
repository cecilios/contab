"""Pruebas de la lógica de negocio relacionada con contratos y rentas."""

from datetime import date

import pytest

from contab.models import AjusteRenta, RentaContrato
from contab.contratos.services import (
    RentaFacturableError,
    RentaNoDisponibleError,
    renta_facturable,
    renta_vigente,
)


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


def test_renta_facturable_sin_ajuste(session, contrato) -> None:
    """Comprueba que sin ajustes se factura la renta ordinaria vigente."""
    session.add(
        RentaContrato(
            contrato=contrato,
            fecha_desde=date(2026, 2, 1),
            importe=100000,
        )
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 9, 1)) == 100000


def test_renta_facturable_con_reduccion_porcentual(session, contrato) -> None:
    """Comprueba que una reducción porcentual se aplica sobre la renta vigente."""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=100000,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 10, 1),
                tipo="REDUCCION_PORCENTUAL",
                valor=4000,
            ),
        ]
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 7, 1)) == 60000


def test_renta_facturable_con_reduccion_fija(session, contrato) -> None:
    """Comprueba que una reducción fija resta su importe a la renta vigente."""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=100000,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 10, 1),
                tipo="REDUCCION_FIJA",
                valor=20000,
            ),
        ]
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 7, 1)) == 80000


def test_renta_facturable_con_importe_fijo(session, contrato) -> None:
    """Comprueba que un importe fijo sustituye temporalmente la renta ordinaria."""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=100000,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 6, 1),
                tipo="IMPORTE_FIJO",
                valor=5000,
            ),
        ]
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 5, 1)) == 5000


def test_reduccion_porcentual_se_aplica_a_renta_revisada(session, contrato) -> None:
    """Comprueba que el ajuste porcentual se aplica a una nueva renta revisada."""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=100000,
            ),
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 7, 1),
                importe=102300,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 10, 1),
                tipo="REDUCCION_PORCENTUAL",
                valor=4000,
            ),
        ]
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 8, 1)) == 61380


def test_reduccion_fija_no_puede_producir_renta_negativa(session, contrato) -> None:
    """Comprueba que una reducción fija no puede producir renta negativa."""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=10000,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 10, 1),
                tipo="REDUCCION_FIJA",
                valor=20000,
            ),
        ]
    )
    session.commit()

    with pytest.raises(RentaFacturableError):
        renta_facturable(contrato, date(2026, 7, 1))


def test_renta_facturable_redondea_al_centimo_arriba(session, contrato) -> None:
    """Comprueba que los cálculos monetarios redondean medio céntimo hacia arriba:
       reduccion 50%, nueva renta 100,01 € × 50 % = 50,005 €  -> 50,01 €)"""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=10001,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 10, 1),
                tipo="REDUCCION_PORCENTUAL",
                valor=5000,
            ),
        ]
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 7, 1)) == 5001




def test_renta_facturable_redondea_al_centimo_abajo(session, contrato) -> None:
    """Comprueba que los cálculos monetarios redondean menos de medio céntimo
       hacia abajo: reduccion 75%, nueva renta  100,01 € × 25 % = 25,0025  -> 25,00 €)"""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=10001,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 10, 1),
                tipo="REDUCCION_PORCENTUAL",
                valor=7500,
            ),
        ]
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 7, 1)) == 2500



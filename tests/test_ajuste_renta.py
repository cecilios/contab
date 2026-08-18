"""Pruebas del modelo ORM AjusteRenta."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import AjusteRenta, Contrato, Inmueble


def test_crear_ajuste_porcentual(session, contrato) -> None:
    """Comprueba que puede almacenarse una reducción porcentual temporal."""

    ajuste = AjusteRenta(
        contrato=contrato,
        fecha_desde=date(2026, 3, 1),
        fecha_hasta=date(2026, 10, 1),
        tipo="REDUCCION_PORCENTUAL",
        valor=4000,
    )

    session.add(ajuste)
    session.commit()

    assert ajuste.id is not None
    assert ajuste.tipo == "REDUCCION_PORCENTUAL"
    assert ajuste.valor == 4000
    assert ajuste.contrato is contrato


def test_crear_ajuste_importe_fijo(session, contrato) -> None:
    """Comprueba que puede almacenarse una renta temporal de importe fijo."""

    ajuste = AjusteRenta(
        contrato=contrato,
        fecha_desde=date(2026, 3, 1),
        fecha_hasta=date(2026, 6, 1),
        tipo="IMPORTE_FIJO",
        valor=5000,
    )

    session.add(ajuste)
    session.commit()

    assert ajuste.valor == 5000


def test_ajuste_no_admite_fecha_fin_anterior(session, contrato) -> None:
    """Comprueba que un ajuste no puede finalizar antes de comenzar."""
 
    ajuste = AjusteRenta(
        contrato=contrato,
        fecha_desde=date(2026, 10, 1),
        fecha_hasta=date(2026, 3, 1),
        tipo="REDUCCION_FIJA",
        valor=10000,
    )

    session.add(ajuste)

    with pytest.raises(IntegrityError):
        session.commit()


def test_ajuste_no_admite_tipo_desconocido(session, contrato) -> None:
    """Comprueba que sólo pueden almacenarse tipos de ajuste conocidos."""

    ajuste = AjusteRenta(
        contrato=contrato,
        fecha_desde=date(2026, 3, 1),
        fecha_hasta=date(2026, 6, 1),
        tipo="DESCONOCIDO",
        valor=10000,
    )

    session.add(ajuste)

    with pytest.raises(IntegrityError):
        session.commit()

"""Pruebas del modelo ORM AjusteRenta."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import AjusteRenta, Contrato, Inmueble


def crear_contrato(session) -> Contrato:
    """Crea un contrato válido para utilizarlo en las pruebas de ajustes."""
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


def test_crear_ajuste_porcentual(session) -> None:
    """Comprueba que puede almacenarse una reducción porcentual temporal."""
    contrato = crear_contrato(session)

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


def test_crear_ajuste_importe_fijo(session) -> None:
    """Comprueba que puede almacenarse una renta temporal de importe fijo."""
    contrato = crear_contrato(session)

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


def test_ajuste_no_admite_fecha_fin_anterior(session) -> None:
    """Comprueba que un ajuste no puede finalizar antes de comenzar."""
    contrato = crear_contrato(session)

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


def test_ajuste_no_admite_tipo_desconocido(session) -> None:
    """Comprueba que sólo pueden almacenarse tipos de ajuste conocidos."""
    contrato = crear_contrato(session)

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

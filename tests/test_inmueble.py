"""Pruebas del modelo ORM Inmueble."""

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import Inmueble


def test_referencia_no_puede_repetirse(session) -> None:
    """Comprueba que dos inmuebles no pueden compartir la misma referencia."""
    session.add(
        Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local 1",
            direccion="Dirección 1",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
    )
    session.commit()

    session.add(
        Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A2",
            descripcion="Local 2",
            direccion="Dirección 2",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_participacion_no_puede_superar_100_por_ciento(session) -> None:
    """Comprueba que la participación no puede ser superior al 100 %."""
    session.add(
        Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=10001,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize("tipo", ["P", "L", "G"])
def test_inmueble_acepta_tipos_validos(session, tipo) -> None:
    inmueble = Inmueble(
        referencia=f"REF-{tipo}",
        tipo=tipo,
        codigo_facturacion=f"COD-{tipo}",
        descripcion="Inmueble",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    session.add(inmueble)
    session.commit()

    assert inmueble.tipo == tipo


def test_inmueble_rechaza_tipo_invalido(session) -> None:
    inmueble = Inmueble(
        tipo="X",
        referencia="REF-X",
        codigo_facturacion="COD-X",
        descripcion="Inmueble",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    session.add(inmueble)

    with pytest.raises(IntegrityError):
        session.commit()


def test_crear_inmueble(session) -> None:
    """Comprueba que crear_inmueble guarda el tipo"""
    inmueble = Inmueble(
        referencia="A6",
        tipo="L",
        codigo_facturacion="A6",
        descripcion="Local comercial",
        direccion="Rúa Michelena, 18",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    session.add(inmueble)
    session.commit()

    assert inmueble.id is not None
    assert inmueble.participacion == 10000
    assert inmueble.activo is True
    assert inmueble.tipo == "L"
    assert inmueble.ruta_documentos == ""



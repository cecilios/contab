"""Pruebas del modelo ORM Inquilino."""

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import Inquilino


def test_crear_inquilino(session) -> None:
    """Comprueba que puede almacenarse y recuperarse un inquilino válido."""
    inquilino = Inquilino(
        nombre="Empresa de Prueba S.L.",
        nif="B12345678",
        direccion="Rúa da Oliva, 10",
        codigo_postal="36001",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        email="prueba@example.com",
        telefono="986000000",
    )

    session.add(inquilino)
    session.commit()

    assert inquilino.id is not None
    assert inquilino.nombre == "Empresa de Prueba S.L."
    assert inquilino.nif == "B12345678"


def test_inquilino_admite_datos_opcionales_vacios(session) -> None:
    """Comprueba que sólo nombre y NIF son obligatorios al crear un inquilino."""
    inquilino = Inquilino(
        nombre="Persona de Prueba",
        nif="12345678Z",
    )

    session.add(inquilino)
    session.commit()

    assert inquilino.id is not None
    assert inquilino.direccion is None
    assert inquilino.email is None
    assert inquilino.telefono is None


def test_inquilino_requiere_nombre(session) -> None:
    """Comprueba que no puede almacenarse un inquilino sin nombre."""
    session.add(
        Inquilino(
            nombre=None,
            nif="12345678Z",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_inquilino_requiere_nif(session) -> None:
    """Comprueba que no puede almacenarse un inquilino sin NIF."""
    session.add(
        Inquilino(
            nombre="Persona de Prueba",
            nif=None,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()

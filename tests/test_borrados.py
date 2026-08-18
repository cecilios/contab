"""Pruebas de protección frente a borrados que destruirían información histórica."""

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import ContratoInquilino, Inquilino


def test_no_puede_borrarse_inmueble_con_contrato(session, inmueble, contrato) -> None:
    """Comprueba que no puede borrarse un inmueble que tenga contratos."""
    session.delete(inmueble)

    with pytest.raises(IntegrityError):
        session.commit()


def test_no_puede_borrarse_inquilino_usado_en_contrato(session, contrato) -> None:
    """Comprueba que no puede borrarse un inquilino vinculado a un contrato."""
    inquilino = Inquilino(
        nombre="Ana Pérez",
        nif="11111111A",
    )

    relacion = ContratoInquilino(
        contrato=contrato,
        inquilino=inquilino,
        orden=1,
    )

    session.add(relacion)
    session.commit()

    session.delete(inquilino)

    with pytest.raises(IntegrityError):
        session.commit()


def test_puede_borrarse_inquilino_sin_contratos(session) -> None:
    """Comprueba que puede borrarse un inquilino que nunca fue usado."""
    inquilino = Inquilino(
        nombre="Ana Pérez",
        nif="11111111A",
    )

    session.add(inquilino)
    session.commit()

    inquilino_id = inquilino.id

    session.delete(inquilino)
    session.commit()

    assert session.get(Inquilino, inquilino_id) is None

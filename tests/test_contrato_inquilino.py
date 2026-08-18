"""Pruebas de la relación entre contratos e inquilinos."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import Contrato, ContratoInquilino, Inmueble, Inquilino


def test_asociar_varios_inquilinos_a_contrato(session, contrato) -> None:
    """Comprueba que un contrato puede tener varios titulares ordenados."""

    inquilino_1 = Inquilino(
        nombre="Ana Pérez",
        nif="11111111A",
    )
    inquilino_2 = Inquilino(
        nombre="Luis García",
        nif="22222222B",
    )

    contrato.titulares.append(
        ContratoInquilino(
            inquilino=inquilino_1,
            orden=1,
        )
    )
    contrato.titulares.append(
        ContratoInquilino(
            inquilino=inquilino_2,
            orden=2,
        )
    )

    session.commit()

    assert len(contrato.titulares) == 2
    assert contrato.titulares[0].inquilino is inquilino_1
    assert contrato.titulares[0].orden == 1
    assert contrato.titulares[1].inquilino is inquilino_2
    assert contrato.titulares[1].orden == 2


def test_inquilino_no_puede_repetirse_en_contrato(session, contrato) -> None:
    """Comprueba que un titular no puede aparecer dos veces en un contrato."""

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

    contrato_id = contrato.id
    inquilino_id = inquilino.id

    # Vacía el mapa de objetos de SQLAlchemy para que sea SQLite quien
    # detecte la duplicación de la clave primaria.
    session.expunge_all()

    session.add(
        ContratoInquilino(
            contrato_id=contrato_id,
            inquilino_id=inquilino_id,
            orden=2,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_dos_titulares_no_pueden_tener_mismo_orden(session, contrato) -> None:
    """Comprueba que dos titulares del mismo contrato no comparten orden."""

    inquilino_1 = Inquilino(
        nombre="Ana Pérez",
        nif="11111111A",
    )
    inquilino_2 = Inquilino(
        nombre="Luis García",
        nif="22222222B",
    )

    session.add_all(
        [
            ContratoInquilino(
                contrato=contrato,
                inquilino=inquilino_1,
                orden=1,
            ),
            ContratoInquilino(
                contrato=contrato,
                inquilino=inquilino_2,
                orden=1,
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_orden_de_titular_debe_ser_positivo(session, contrato) -> None:
    """Comprueba que el orden de un titular debe ser mayor que cero."""

    inquilino = Inquilino(
        nombre="Ana Pérez",
        nif="11111111A",
    )

    session.add(
        ContratoInquilino(
            contrato=contrato,
            inquilino=inquilino,
            orden=0,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()

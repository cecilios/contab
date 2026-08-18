"""Pruebas de la relación entre contratos e inquilinos."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import Contrato, ContratoInquilino, Inmueble, Inquilino


def crear_contrato(session) -> Contrato:
    """Crea un contrato válido para utilizarlo en las pruebas."""
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
        fecha_inicio=date(2026, 1, 1),
        fecha_vencimiento=date(2030, 12, 31),
        fecha_inicio_facturacion=date(2026, 1, 1),
        fianza=100000,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )

    session.add(contrato)
    session.commit()

    return contrato


def test_asociar_varios_inquilinos_a_contrato(session) -> None:
    """Comprueba que un contrato puede tener varios titulares ordenados."""
    contrato = crear_contrato(session)

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


def test_inquilino_no_puede_repetirse_en_contrato(session) -> None:
    """Comprueba que un titular no puede aparecer dos veces en un contrato."""
    contrato = crear_contrato(session)

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


def test_dos_titulares_no_pueden_tener_mismo_orden(session) -> None:
    """Comprueba que dos titulares del mismo contrato no comparten orden."""
    contrato = crear_contrato(session)

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


def test_orden_de_titular_debe_ser_positivo(session) -> None:
    """Comprueba que el orden de un titular debe ser mayor que cero."""
    contrato = crear_contrato(session)

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

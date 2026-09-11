import pytest

from datetime import date
from sqlalchemy.exc import IntegrityError

from contab.models import MovimientoBancario


def test_crear_movimiento_bancario(
    session,
) -> None:
    """Guarda un movimiento bancario pendiente."""

    movimiento = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="INGRESO",
        importe=160000,
        tipo_original="TRANSFERENCIA OTRA ENTIDAD",
        descripcion_original="Alquiler septiembre",
        referencia_bancaria="40278053846",
        huella_importacion="a" * 64,
    )

    session.add(movimiento)
    session.commit()

    guardado = session.get(
        MovimientoBancario,
        movimiento.id,
    )

    assert guardado is not None
    assert guardado.fecha == date(2026, 9, 3)
    assert guardado.naturaleza == "INGRESO"
    assert guardado.importe == 160000
    assert guardado.tipo_original == (
        "TRANSFERENCIA OTRA ENTIDAD"
    )
    assert guardado.descripcion_original == (
        "Alquiler septiembre"
    )
    assert guardado.referencia_bancaria == "40278053846"
    assert guardado.huella_importacion == "a" * 64
    assert guardado.estado == "PENDIENTE"


def test_movimiento_bancario_rechaza_huella_duplicada(
    session,
) -> None:
    """Impide guardar dos veces el mismo movimiento importado."""

    datos = {
        "fecha": date(2026, 9, 3),
        "naturaleza": "INGRESO",
        "importe": 160000,
        "tipo_original": "TRANSFERENCIA",
        "descripcion_original": "Alquiler septiembre",
        "referencia_bancaria": "",
        "huella_importacion": "b" * 64,
    }

    session.add(
        MovimientoBancario(**datos)
    )
    session.commit()

    session.add(
        MovimientoBancario(**datos)
    )

    with pytest.raises(IntegrityError):
        session.commit()



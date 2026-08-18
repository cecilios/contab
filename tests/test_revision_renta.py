"""Pruebas del modelo ORM RevisionRenta."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import Contrato, Inmueble, RevisionRenta


def test_crear_revision_pendiente(session, contrato) -> None:
    """Comprueba que una revisión nueva queda pendiente por defecto."""

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 2, 1),
        metodo="IPC_NACIONAL",
    )

    session.add(revision)
    session.commit()

    assert revision.id is not None
    assert revision.estado == "PENDIENTE"
    assert revision.porcentaje_aplicado is None
    assert revision.fecha_resolucion is None
    assert revision.contrato is contrato


def test_revision_admite_porcentaje_negativo(session, contrato) -> None:
    """Comprueba que una revisión puede registrar un porcentaje negativo."""

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 2, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=-125,
        fecha_resolucion=date(2027, 3, 5),
    )

    session.add(revision)
    session.commit()

    assert revision.porcentaje_aplicado == -125


def test_no_admite_dos_revisiones_en_misma_fecha(session, contrato) -> None:
    """Comprueba que un contrato no puede tener dos revisiones el mismo mes."""

    session.add_all(
        [
            RevisionRenta(
                contrato=contrato,
                fecha_prevista=date(2027, 2, 1),
                metodo="IPC_NACIONAL",
            ),
            RevisionRenta(
                contrato=contrato,
                fecha_prevista=date(2027, 2, 1),
                metodo="IPC_REGIONAL",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_revision_no_admite_estado_desconocido(session, contrato) -> None:
    """Comprueba que sólo pueden almacenarse estados de revisión válidos."""

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 2, 1),
        metodo="IPC_NACIONAL",
        estado="DESCONOCIDO",
    )

    session.add(revision)

    with pytest.raises(IntegrityError):
        session.commit()

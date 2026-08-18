"""Pruebas del modelo ORM RevisionRenta."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import Contrato, Inmueble, RevisionRenta


def crear_contrato(session) -> Contrato:
    """Crea un contrato válido para utilizarlo en las pruebas de revisiones."""
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


def test_crear_revision_pendiente(session) -> None:
    """Comprueba que una revisión nueva queda pendiente por defecto."""
    contrato = crear_contrato(session)

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


def test_revision_admite_porcentaje_negativo(session) -> None:
    """Comprueba que una revisión puede registrar un porcentaje negativo."""
    contrato = crear_contrato(session)

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


def test_no_admite_dos_revisiones_en_misma_fecha(session) -> None:
    """Comprueba que un contrato no puede tener dos revisiones el mismo mes."""
    contrato = crear_contrato(session)

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


def test_revision_no_admite_estado_desconocido(session) -> None:
    """Comprueba que sólo pueden almacenarse estados de revisión válidos."""
    contrato = crear_contrato(session)

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 2, 1),
        metodo="IPC_NACIONAL",
        estado="DESCONOCIDO",
    )

    session.add(revision)

    with pytest.raises(IntegrityError):
        session.commit()

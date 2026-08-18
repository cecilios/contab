"""Define recursos comunes utilizados por las pruebas automatizadas."""

from datetime import date

import pytest

from contab.database import Base, create_session_factory, create_sqlite_engine
from contab.models import Contrato, Inmueble


@pytest.fixture
def session():
    """Proporciona a cada test una base SQLite nueva y vacía en memoria."""
    engine = create_sqlite_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as db_session:
        yield db_session


@pytest.fixture
def inmueble(session) -> Inmueble:
    """Crea un inmueble válido reutilizable por los tests."""
    inmueble = Inmueble(
        referencia="LOCAL-1",
        codigo_facturacion="A1",
        descripcion="Local comercial",
        direccion="Dirección de prueba",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    session.add(inmueble)
    session.commit()

    return inmueble


@pytest.fixture
def contrato(session, inmueble) -> Contrato:
    """Crea un contrato válido reutilizable por los tests."""
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


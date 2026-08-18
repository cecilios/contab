"""Define recursos comunes utilizados por las pruebas automatizadas."""

import pytest

from contab.database import Base, create_session_factory, create_sqlite_engine


@pytest.fixture
def session():
    """Proporciona a cada test una base SQLite nueva y vacía en memoria."""
    engine = create_sqlite_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as db_session:
        yield db_session

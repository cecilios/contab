"""Pruebas de la configuración y acceso básico a la base de datos."""
from sqlalchemy import text

from contab.database import create_session_factory, create_sqlite_engine


def test_sqlite_engine_works() -> None:
    """Comprueba que SQLAlchemy puede ejecutar una consulta sobre SQLite."""
    engine = create_sqlite_engine("sqlite:///:memory:")
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        result = session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1

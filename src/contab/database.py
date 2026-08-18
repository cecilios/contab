"""Configura el acceso a la base de datos SQLite mediante SQLAlchemy."""
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_sqlite_engine(database_url: str) -> Engine:
    engine = create_engine(database_url)

    event.listen(
        engine,
        "connect",
        _enable_sqlite_foreign_keys,
    )

    return engine


def create_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

"""Configura el entorno de migraciones Alembic para los modelos de Contab."""

from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from contab.database import Base
import contab.models


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASES = {
    "principal": f"sqlite:///{PROJECT_ROOT / 'contab.db'}",
    "demo": f"sqlite:///{PROJECT_ROOT / 'demo.db'}",
}


def get_database_url() -> str:
    """Devuelve la URL de la base seleccionada para la migración."""
    argumentos = context.get_x_argument(as_dictionary=True)
    nombre = argumentos.get("database")

    if nombre is None:
        return config.get_main_option("sqlalchemy.url")

    try:
        return DATABASES[nombre]
    except KeyError as exc:
        disponibles = ", ".join(DATABASES)
        raise RuntimeError(
            f"Base de datos desconocida: {nombre}. "
            f"Disponibles: {disponibles}."
        ) from exc


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    config.set_main_option(
        "sqlalchemy.url",
        get_database_url(),
    )

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

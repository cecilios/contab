"""Configura el entorno de migraciones Alembic para los modelos de Contab."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from contab.config import cargar_bases_datos
from contab.database import Base
import contab.models


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Devuelve la URL de la base seleccionada para la migración."""
    argumentos = context.get_x_argument(as_dictionary=True)
    nombre = argumentos.get("database")

    databases = cargar_bases_datos()

    if nombre is None:
        if len(databases) == 1:
            return next(iter(databases.values()))

        disponibles = ", ".join(databases)

        raise RuntimeError(
            "Hay varias bases de datos configuradas. "
            "Indica una con --database NOMBRE. "
            f"Disponibles: {disponibles}."
        )

    try:
        return databases[nombre]
    except KeyError as exc:
        disponibles = ", ".join(databases)

        raise RuntimeError(
            f"Base de datos desconocida: {nombre}. "
            f"Disponibles: {disponibles}."
        ) from exc


def run_migrations_offline() -> None:
    """Ejecuta las migraciones en modo offline."""
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Ejecuta las migraciones en modo online."""
    config.set_main_option(
        "sqlalchemy.url",
        get_database_url(),
    )

    connectable = engine_from_config(
        config.get_section(
            config.config_ini_section,
            {},
        ),
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


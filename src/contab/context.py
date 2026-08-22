"""Proporciona acceso a la base de datos seleccionada en la sesión web."""

from flask import current_app, session


class BaseDatosNoSeleccionadaError(Exception):
    """Indica que todavía no se ha seleccionado una base de datos."""


def get_session_factory():
    """Devuelve la fábrica de sesiones de la base activa."""
    nombre = session.get("database")

    if nombre is None:
        raise BaseDatosNoSeleccionadaError(
            "No se ha seleccionado ninguna base de datos."
        )

    databases = current_app.extensions["contab_databases"]

    return databases[nombre]


def get_database_name() -> str | None:
    """Devuelve el nombre de la base de datos activa en la sesión."""
    return session.get("database")

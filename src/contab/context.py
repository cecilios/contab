"""Proporciona acceso a la base de datos seleccionada en la sesión web."""

from flask import current_app, session


class BancoNoConfiguradoError(Exception):
    """Indica que la base activa no tiene banco configurado."""

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


def get_bank_name() -> str:
    """Devuelve el banco asociado a la base de datos activa."""

    nombre = get_database_name()

    if nombre is None:
        raise BaseDatosNoSeleccionadaError(
            "No se ha seleccionado ninguna base de datos."
        )

    bancos = current_app.extensions["contab_bancos"]

    try:
        return bancos[nombre]
    except KeyError as exc:
        raise BancoNoConfiguradoError(
            f"No se ha configurado el banco para "
            f"la base de datos {nombre}."
        ) from exc



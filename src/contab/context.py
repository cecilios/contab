"""Proporciona acceso a elementos depedientes de la base de datos seleccionada."""

from flask import current_app, session
from pathlib import Path
from sqlalchemy.engine import make_url


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


def get_database_path() -> Path:
    """Devuelve la ruta de la base de datos activa."""

    nombre = get_database_name()

    if nombre is None:
        raise BaseDatosNoSeleccionadaError(
            "No se ha seleccionado ninguna base de datos."
        )

    database_url = current_app.extensions[
        "contab_database_urls"
    ][nombre]

    url = make_url(database_url)

    if url.get_backend_name() != "sqlite":
        raise RuntimeError(
            "La base de datos activa no es SQLite."
        )

    if url.database in (None, "", ":memory:"):
        raise RuntimeError(
            "La base de datos activa no tiene una ruta de archivo."
        )

    return Path(url.database).resolve()


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


def get_invoice_template_path() -> Path:
    """Devuelve la plantilla de factura de la base activa."""

    database_path = get_database_path()

    return database_path.with_name(
        f"{database_path.stem}-factura.html"
    )



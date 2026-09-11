import pytest

from flask import session

from contab.app import create_app
from contab.context import (
    BancoNoConfiguradoError,
    BaseDatosNoSeleccionadaError,
    get_bank_name,
    get_database_name,
    get_session_factory,
)


def test_get_database_name() -> None:
    """Devuelve el nombre de la base activa."""

    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="clave-test",
    )

    with app.test_request_context():
        assert get_database_name() is None

        session["database"] = "test"

        assert get_database_name() == "test"


def test_get_session_factory() -> None:
    """Devuelve la fábrica de sesiones de la base activa."""

    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="clave-test",
    )

    with app.test_request_context():
        session["database"] = "test"

        assert get_session_factory() is (
            app.extensions["contab_databases"]["test"]
        )


def test_get_session_factory_exige_base_seleccionada() -> None:
    """No devuelve una sesión sin seleccionar base."""

    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="clave-test",
    )

    with app.test_request_context():
        with pytest.raises(
            BaseDatosNoSeleccionadaError,
        ):
            get_session_factory()


def test_get_bank_name_devuelve_banco_seleccionado() -> None:
    """Obtiene el banco asociado a la base activa."""

    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="clave-test",
        bancos={
            "test": "IBERCAJA",
        },
    )

    with app.test_request_context():
        session["database"] = "test"

        assert get_bank_name() == "IBERCAJA"


def test_get_bank_name_exige_base_seleccionada() -> None:
    """No permite obtener el banco sin seleccionar base."""

    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="clave-test",
        bancos={
            "test": "IBERCAJA",
        },
    )

    with app.test_request_context():
        with pytest.raises(
            BaseDatosNoSeleccionadaError,
        ):
            get_bank_name()


def test_get_bank_name_exige_banco_configurado() -> None:
    """Detecta una base creada sin banco asociado."""

    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="clave-test",
    )

    with app.test_request_context():
        session["database"] = "test"

        with pytest.raises(
            BancoNoConfiguradoError,
            match="test",
        ):
            get_bank_name()

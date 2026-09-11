"""Pruebas básicas de funcionamiento de la aplicación web."""

from contab.app import create_app


def test_index() -> None:
    """Comprueba que la página principal permite seleccionar una base de datos."""
    app = create_app(
        {
            "test": "sqlite:///:memory:",
        }
    )
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "Contab" in response.text
    assert "Base de datos" in response.text
    assert "test" in response.text


def test_create_app_carga_bancos_configurados(
    tmp_path,
    monkeypatch,
) -> None:
    """Carga los bancos asociados a las bases de datos."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[app]
secret_key = clave-test

[databases]
test = sqlite:///:memory:

[bancos]
test = IBERCAJA
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = create_app()

    assert app.extensions["contab_bancos"] == {
        "test": "IBERCAJA",
    }



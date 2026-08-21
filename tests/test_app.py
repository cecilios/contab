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

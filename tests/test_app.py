"""Pruebas básicas de funcionamiento de la aplicación web."""
from contab.app import create_app


def test_index() -> None:
    """Comprueba que la página principal responde correctamente."""
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert response.text == "Contab funciona"

from contab.app import create_app


def test_index() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert response.text == "Contab funciona"

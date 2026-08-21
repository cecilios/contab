"""Pruebas de las rutas web del módulo de inmuebles."""

from contab.app import create_app
from contab.database import Base
from contab.models import Inmueble


def crear_app_test():
    """Crea una aplicación web con una base SQLite aislada para las pruebas."""
    app = create_app("sqlite:///:memory:")

    session_factory = app.extensions["contab_session_factory"]
    engine = session_factory.kw["bind"]

    Base.metadata.create_all(engine)

    return app


def test_listado_inmuebles_vacio() -> None:
    """Comprueba que el listado informa cuando no existen inmuebles."""
    app = crear_app_test()
    client = app.test_client()

    response = client.get("/inmuebles/")

    assert response.status_code == 200
    assert "Inmuebles" in response.text
    assert "No hay inmuebles registrados." in response.text


def test_listado_muestra_inmuebles_registrados() -> None:
    """Comprueba que el listado muestra los inmuebles almacenados."""
    app = crear_app_test()
    session_factory = app.extensions["contab_session_factory"]

    with session_factory() as session:
        session.add(
            Inmueble(
                referencia="LOCAL-1",
                codigo_facturacion="A1",
                descripcion="Local comercial",
                direccion="Rúa Michelena, 18",
                poblacion="Pontevedra",
                provincia="Pontevedra",
            )
        )
        session.commit()

    client = app.test_client()
    response = client.get("/inmuebles/")

    assert response.status_code == 200
    assert "LOCAL-1" in response.text
    assert "Local comercial" in response.text
    assert "No hay inmuebles registrados." not in response.text

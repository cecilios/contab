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


def test_formulario_nuevo_inmueble_responde() -> None:
    """Comprueba que puede abrirse el formulario de alta de inmuebles."""
    app = crear_app_test()
    client = app.test_client()

    response = client.get("/inmuebles/nuevo")

    assert response.status_code == 200
    assert "Nuevo inmueble" in response.text
    assert "Referencia" in response.text
    assert "Código de facturación" in response.text


def test_crear_inmueble_desde_formulario() -> None:
    """Comprueba que un inmueble válido se guarda desde la interfaz web."""
    app = crear_app_test()
    client = app.test_client()

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "referencia": "LOCAL-2",
            "codigo_facturacion": "A2",
            "descripcion": "Segundo local",
            "direccion": "Rúa da Oliva, 20",
            "codigo_postal": "36001",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "POL-12345",
            "participacion": "100,00",
            "notas": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "LOCAL-2" in response.text
    assert "Segundo local" in response.text


def test_crear_inmueble_rechaza_referencia_vacia() -> None:
    """Comprueba que no puede crearse un inmueble sin referencia."""
    app = crear_app_test()
    client = app.test_client()

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "referencia": "",
            "codigo_facturacion": "A2",
            "descripcion": "Segundo local",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "100,00",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "La referencia es obligatoria." in response.text


def test_crear_inmueble_convierte_participacion_a_centesimas() -> None:
    """Comprueba que 32,56 % se almacena internamente como 3256."""
    app = crear_app_test()
    client = app.test_client()

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "referencia": "PARTE-A",
            "codigo_facturacion": "A3",
            "descripcion": "Parte A",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "32,56",
            "notas": "",
        },
    )

    assert response.status_code == 302

    session_factory = app.extensions["contab_session_factory"]

    with session_factory() as session:
        inmueble = session.query(Inmueble).filter_by(
            referencia="PARTE-A"
        ).one()

        assert inmueble.participacion == 3256

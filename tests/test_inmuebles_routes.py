"""Pruebas de las rutas web del módulo de inmuebles."""

import pytest
from contab.app import create_app
from contab.database import Base
from contab.models import Inmueble

@pytest.mark.parametrize(
    ("campo", "mensaje"),
    [
        ("referencia", "La referencia es obligatoria."),
        ("codigo_facturacion", "El código de facturación es obligatorio."),
        ("descripcion", "La descripción es obligatoria."),
        ("direccion", "La dirección es obligatoria."),
        ("poblacion", "La población es obligatoria."),
        ("provincia", "La provincia es obligatoria."),
    ],
)
def test_crear_inmueble_rechaza_campos_obligatorios_vacios(
    campo, mensaje
) -> None:
    """Comprueba que los campos obligatorios no pueden quedar vacíos."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    datos = {
        "referencia": "LOCAL-1",
        "codigo_facturacion": "A1",
        "descripcion": "Local comercial",
        "direccion": "Dirección",
        "codigo_postal": "",
        "poblacion": "Pontevedra",
        "provincia": "Pontevedra",
        "ref_catastral": "",
        "seguro": "",
        "participacion": "100,00",
        "notas": "",
    }

    datos[campo] = ""

    response = client.post(
        "/inmuebles/nuevo",
        data=datos,
    )

    assert response.status_code == 400
    assert mensaje in response.text

    
def crear_app_test():
    """Crea una aplicación con una base SQLite aislada para las pruebas."""
    app = create_app(
        {
            "test": "sqlite:///:memory:",
        }
    )

    session_factory = app.extensions["contab_databases"]["test"]
    engine = session_factory.kw["bind"]

    Base.metadata.create_all(engine)

    return app


def test_listado_inmuebles_vacio() -> None:
    """Comprueba que el listado informa cuando no existen inmuebles."""
    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/inmuebles/")

    assert response.status_code == 200
    assert "Inmuebles" in response.text
    assert "No hay inmuebles registrados." in response.text


def test_listado_muestra_inmuebles_registrados() -> None:
    """Comprueba que el listado muestra los inmuebles almacenados."""
    app = crear_app_test()
    session_factory = app.extensions["contab_databases"]["test"]

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

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/inmuebles/")

    assert response.status_code == 200
    assert "LOCAL-1" in response.text
    assert "Local comercial" in response.text
    assert "No hay inmuebles registrados." not in response.text


def test_formulario_nuevo_inmueble_responde() -> None:
    """Comprueba que puede abrirse el formulario de alta de inmuebles."""
    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/inmuebles/nuevo")

    assert response.status_code == 200
    assert "Nuevo inmueble" in response.text
    assert "Referencia" in response.text
    assert "Código de facturación" in response.text


def test_crear_inmueble_desde_formulario() -> None:
    """Comprueba que un inmueble válido se guarda desde la interfaz web."""
    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

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

    client.post(
        "/",
        data={"database": "test"},
    )

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

    client.post(
        "/",
        data={"database": "test"},
    )

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

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = session.query(Inmueble).filter_by(
            referencia="PARTE-A"
        ).one()

        assert inmueble.participacion == 3256


def test_listado_muestra_base_activa() -> None:
    """Comprueba que la interfaz muestra la base de datos seleccionada."""
    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/inmuebles/")

    assert response.status_code == 200
    assert "Base activa:" in response.text
    assert "test" in response.text


def test_crear_inmueble_rechaza_participacion_cero() -> None:
    """Comprueba que la participación debe ser superior al 0 %."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "referencia": "LOCAL-1",
            "codigo_facturacion": "A1",
            "descripcion": "Local comercial",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "0",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "La participación debe ser superior al 0 %." in response.text


def test_crear_inmueble_rechaza_participacion_superior_a_cien() -> None:
    """Comprueba que la participación no puede superar el 100 %."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "referencia": "LOCAL-1",
            "codigo_facturacion": "A1",
            "descripcion": "Local comercial",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "100,01",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "La participación no puede superar el 100 %." in response.text


def test_crear_inmueble_rechaza_participacion_no_numerica() -> None:
    """Comprueba que la participación debe contener un porcentaje válido."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "referencia": "LOCAL-1",
            "codigo_facturacion": "A1",
            "descripcion": "Local comercial",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "abc",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "La participación debe ser un porcentaje válido." in response.text


def test_crear_inmueble_rechaza_referencia_duplicada() -> None:
    """Comprueba que dos inmuebles no pueden compartir referencia."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    datos = {
        "referencia": "LOCAL-1",
        "codigo_facturacion": "A1",
        "descripcion": "Local comercial",
        "direccion": "Dirección",
        "codigo_postal": "",
        "poblacion": "Pontevedra",
        "provincia": "Pontevedra",
        "ref_catastral": "",
        "seguro": "",
        "participacion": "100,00",
        "notas": "",
    }

    response = client.post("/inmuebles/nuevo", data=datos)
    assert response.status_code == 302

    datos["codigo_facturacion"] = "A2"

    response = client.post("/inmuebles/nuevo", data=datos)

    assert response.status_code == 400
    assert "Ya existe un inmueble con esa referencia." in response.text


def test_crear_inmueble_rechaza_codigo_facturacion_duplicado() -> None:
    """Comprueba que dos inmuebles no pueden compartir código de facturación."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    datos = {
        "referencia": "LOCAL-1",
        "codigo_facturacion": "A1",
        "descripcion": "Local comercial",
        "direccion": "Dirección",
        "codigo_postal": "",
        "poblacion": "Pontevedra",
        "provincia": "Pontevedra",
        "ref_catastral": "",
        "seguro": "",
        "participacion": "100,00",
        "notas": "",
    }

    response = client.post("/inmuebles/nuevo", data=datos)
    assert response.status_code == 302

    datos["referencia"] = "LOCAL-2"

    response = client.post("/inmuebles/nuevo", data=datos)

    assert response.status_code == 400
    assert "Ya existe un inmueble con ese código de facturación." in response.text

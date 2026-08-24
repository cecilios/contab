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


def test_formulario_editar_inmueble_muestra_datos_actuales() -> None:
    """Comprueba que el formulario de edición muestra los datos existentes."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección inicial",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=10000,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.get(f"/inmuebles/{inmueble_id}/editar")

    assert response.status_code == 200
    assert "Editar inmueble" in response.text
    assert 'value="LOCAL-1"' in response.text
    assert 'value="Dirección inicial"' in response.text
    assert 'value="100,00"' in response.text


def test_editar_inmueble_guarda_cambios() -> None:
    """Comprueba que los cambios realizados en un inmueble se guardan."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección inicial",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=10000,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.post(
        f"/inmuebles/{inmueble_id}/editar",
        data={
            "referencia": "LOCAL-1",
            "codigo_facturacion": "A1",
            "descripcion": "Local reformado",
            "direccion": "Nueva dirección",
            "codigo_postal": "36001",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "POL-999",
            "participacion": "32,56",
            "notas": "Datos actualizados",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Local reformado" in response.text

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        assert inmueble.descripcion == "Local reformado"
        assert inmueble.direccion == "Nueva dirección"
        assert inmueble.participacion == 3256
        assert inmueble.seguro == "POL-999"


def test_editar_inmueble_inexistente_devuelve_404() -> None:
    """Comprueba que editar un inmueble inexistente devuelve 404."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    response = client.get("/inmuebles/99999/editar")

    assert response.status_code == 404


def test_editar_inmueble_rechaza_referencia_de_otro_inmueble() -> None:
    """Comprueba que la edición no puede duplicar la referencia de otro inmueble."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        primero = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Primero",
            direccion="Dirección 1",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        segundo = Inmueble(
            referencia="LOCAL-2",
            codigo_facturacion="A2",
            descripcion="Segundo",
            direccion="Dirección 2",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        session.add_all([primero, segundo])
        session.commit()

        segundo_id = segundo.id

    response = client.post(
        f"/inmuebles/{segundo_id}/editar",
        data={
            "referencia": "LOCAL-1",
            "codigo_facturacion": "A2",
            "descripcion": "Segundo",
            "direccion": "Dirección 2",
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
    assert "Ya existe un inmueble con esa referencia." in response.text


def test_confirmar_desactivacion_inmueble() -> None:
    """Comprueba que se muestra confirmación antes de desactivar un inmueble."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            activo=True,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.get(f"/inmuebles/{inmueble_id}/estado")

    assert response.status_code == 200
    assert "Este inmueble quedará inactivo" in response.text
    assert "Permanecerá a efectos históricos" in response.text
    assert "Desactivar" in response.text
    assert "Cancelar" in response.text


def test_desactivar_inmueble() -> None:
    """Comprueba que confirmar la desactivación marca el inmueble como inactivo."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            activo=True,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.post(
        f"/inmuebles/{inmueble_id}/estado",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "INACTIVO" in response.text

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        assert inmueble.activo is False


def test_confirmar_activacion_inmueble() -> None:
    """Comprueba que se muestra confirmación antes de activar un inmueble."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            activo=False,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.get(f"/inmuebles/{inmueble_id}/estado")

    assert response.status_code == 200
    assert "Este inmueble volverá a estar activo" in response.text
    assert "Activar" in response.text
    assert "Cancelar" in response.text


def test_activar_inmueble() -> None:
    """Comprueba que confirmar la activación marca el inmueble como activo."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            activo=False,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.post(
        f"/inmuebles/{inmueble_id}/estado",
        follow_redirects=True,
    )

    assert response.status_code == 200

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        assert inmueble.activo is True


def test_cambiar_estado_inmueble_inexistente_devuelve_404() -> None:
    """Comprueba que cambiar el estado de un inmueble inexistente devuelve 404."""
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    response = client.get("/inmuebles/99999/estado")

    assert response.status_code == 404



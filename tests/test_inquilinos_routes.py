"""Pruebas de las rutas web del módulo de inquilinos."""

from contab.app import create_app
from contab.database import Base
from contab.models import Inquilino


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


def seleccionar_base(client) -> None:
    """Selecciona la base de datos de pruebas para la sesión web."""
    client.post(
        "/",
        data={"database": "test"},
    )


def test_listado_inquilinos_vacio() -> None:
    """Comprueba que el listado informa cuando no existen inquilinos."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.get("/inquilinos/")

    assert response.status_code == 200
    assert "Inquilinos" in response.text
    assert "No hay inquilinos registrados." in response.text


def test_listado_muestra_inquilinos_registrados() -> None:
    """Comprueba que el listado muestra los inquilinos almacenados."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        session.add(
            Inquilino(
                nombre="Ana Pérez",
                nif="11111111A",
                email="ana@example.com",
            )
        )
        session.commit()

    response = client.get("/inquilinos/")

    assert response.status_code == 200
    assert "Ana Pérez" in response.text
    assert "11111111A" in response.text


def test_formulario_nuevo_inquilino_responde() -> None:
    """Comprueba que puede abrirse el formulario de alta de inquilinos."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.get("/inquilinos/nuevo")

    assert response.status_code == 200
    assert "Nuevo inquilino" in response.text
    assert "Nombre (*)" in response.text
    assert "NIF (*)" in response.text


def test_crear_inquilino_desde_formulario() -> None:
    """Comprueba que un inquilino válido se guarda desde la interfaz web."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.post(
        "/inquilinos/nuevo",
        data={
            "nombre": "Ana Pérez",
            "nif": "11111111A",
            "direccion": "Rúa da Oliva, 20",
            "codigo_postal": "36001",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "email": "ana@example.com",
            "telefono": "600123123",
            "notas": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Ana Pérez" in response.text
    assert "11111111A" in response.text


def test_crear_inquilino_rechaza_nombre_vacio() -> None:
    """Comprueba que no puede crearse un inquilino sin nombre."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.post(
        "/inquilinos/nuevo",
        data={
            "nombre": "",
            "nif": "11111111A",
            "direccion": "",
            "codigo_postal": "",
            "poblacion": "",
            "provincia": "",
            "email": "",
            "telefono": "",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "El nombre es obligatorio." in response.text


def test_crear_inquilino_rechaza_nif_vacio() -> None:
    """Comprueba que no puede crearse un inquilino sin NIF."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.post(
        "/inquilinos/nuevo",
        data={
            "nombre": "Ana Pérez",
            "nif": "",
            "direccion": "",
            "codigo_postal": "",
            "poblacion": "",
            "provincia": "",
            "email": "",
            "telefono": "",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "El NIF es obligatorio." in response.text


def test_crear_inquilino_rechaza_nif_duplicado() -> None:
    """Comprueba que no pueden existir dos inquilinos con el mismo NIF."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    datos = {
        "nombre": "Ana Pérez",
        "nif": "11111111A",
        "direccion": "",
        "codigo_postal": "",
        "poblacion": "",
        "provincia": "",
        "email": "",
        "telefono": "",
        "notas": "",
    }

    response = client.post("/inquilinos/nuevo", data=datos)
    assert response.status_code == 302

    datos["nombre"] = "Otra persona"

    response = client.post("/inquilinos/nuevo", data=datos)

    assert response.status_code == 400
    assert "Ya existe un inquilino con ese NIF." in response.text


def test_formulario_editar_inquilino_muestra_datos_actuales() -> None:
    """Comprueba que el formulario de edición muestra los datos existentes."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
            direccion="Dirección inicial",
            email="ana@example.com",
        )
        session.add(inquilino)
        session.commit()
        inquilino_id = inquilino.id

    response = client.get(f"/inquilinos/{inquilino_id}/editar")

    assert response.status_code == 200
    assert "Editar inquilino" in response.text
    assert 'value="Ana Pérez"' in response.text
    assert 'value="11111111A"' in response.text
    assert 'value="ana@example.com"' in response.text


def test_editar_inquilino_guarda_cambios() -> None:
    """Comprueba que los cambios realizados en un inquilino se guardan."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )
        session.add(inquilino)
        session.commit()
        inquilino_id = inquilino.id

    response = client.post(
        f"/inquilinos/{inquilino_id}/editar",
        data={
            "nombre": "Ana Pérez García",
            "nif": "11111111A",
            "direccion": "Nueva dirección",
            "codigo_postal": "36001",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "email": "nueva@example.com",
            "telefono": "600123456",
            "notas": "Actualizado",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Ana Pérez García" in response.text

    with session_factory() as session:
        inquilino = session.get(Inquilino, inquilino_id)

        assert inquilino.nombre == "Ana Pérez García"
        assert inquilino.direccion == "Nueva dirección"
        assert inquilino.email == "nueva@example.com"


def test_editar_inquilino_rechaza_nif_de_otro_inquilino() -> None:
    """Comprueba que la edición no puede duplicar el NIF de otro inquilino."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        primero = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )
        segundo = Inquilino(
            nombre="Luis García",
            nif="22222222B",
        )

        session.add_all([primero, segundo])
        session.commit()

        segundo_id = segundo.id

    response = client.post(
        f"/inquilinos/{segundo_id}/editar",
        data={
            "nombre": "Luis García",
            "nif": "11111111A",
            "direccion": "",
            "codigo_postal": "",
            "poblacion": "",
            "provincia": "",
            "email": "",
            "telefono": "",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "Ya existe un inquilino con ese NIF." in response.text


def test_editar_inquilino_inexistente_devuelve_404() -> None:
    """Comprueba que editar un inquilino inexistente devuelve 404."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.get("/inquilinos/99999/editar")

    assert response.status_code == 404



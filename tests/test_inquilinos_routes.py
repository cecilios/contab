"""Pruebas de las rutas web del módulo de inquilinos."""

from datetime import date

from contab.app import create_app
from contab.database import Base
from contab.models import (
    Contrato,
    ContratoInquilino,
    Inmueble,
    Inquilino,
)



def crear_app_test():
    """Crea una aplicación con una base SQLite aislada para las pruebas."""
    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="test-secret-key",
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


def _crear_inmueble_prueba(referencia: str) -> Inmueble:
    """Construye un inmueble válido para las pruebas del listado."""

    return Inmueble(
        referencia=referencia,
        codigo_facturacion=referencia,
        tipo="L",
        descripcion=f"Inmueble {referencia}",
        direccion="Dirección de prueba",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        porcentaje_titular=10000,
        tipo_derecho="PLENA_PROPIEDAD",
        porcentaje_derecho=10000,
        fecha_adquisicion=date(2020, 1, 1),
        tipo_adquisicion="ONEROSA",
        importe_adquisicion=0,
        gastos_adquisicion=0,
    )


def _crear_contrato_prueba(
    inmueble: Inmueble,
    *inquilinos: Inquilino,
    fecha_inicio: date = date(2024, 1, 1),
    fecha_vencimiento: date = date(2030, 12, 31),
    fecha_fin: date | None = None,
) -> Contrato:
    """Construye un contrato con sus titulares para probar el listado."""

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=fecha_vencimiento,
        fecha_fin=fecha_fin,
        genera_factura=False,
        fecha_inicio_facturacion=fecha_inicio,
        fianza=100000,
        direccion_facturacion="",
        poblacion_facturacion="",
        provincia_facturacion="",
        concepto_factura="Alquiler",
    )

    contrato.titulares = [
        ContratoInquilino(
            inquilino=inquilino,
            orden=orden,
        )
        for orden, inquilino in enumerate(inquilinos, start=1)
    ]

    return contrato


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
    assert 'name="nombre"' in response.text
    assert 'name="nif"' in response.text
    assert 'name="direccion"' in response.text


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
    assert 'name="nombre"' in response.text
    assert 'name="nif"' in response.text
    assert "Editar inquilino" in response.text


def test_editar_inquilino_inexistente_devuelve_404() -> None:
    """Comprueba que editar un inquilino inexistente devuelve 404."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.get("/inquilinos/99999/editar")

    assert response.status_code == 404


def test_listado_separa_inquilinos_vigentes_e_historicos() -> None:
    """Separa los inquilinos y ordena cada grupo por nombre."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        # Se crean deliberadamente en orden no alfabético.
        vigente_z = Inquilino(
            nombre="Vigente Z",
            nif="11111111A",
        )
        vigente_a = Inquilino(
            nombre="Vigente A",
            nif="22222222B",
        )
        historico_z = Inquilino(
            nombre="Historico Z",
            nif="33333333C",
        )
        historico_a = Inquilino(
            nombre="Historico A",
            nif="44444444D",
        )

        session.add_all([
            _crear_contrato_prueba(
                _crear_inmueble_prueba("LOCAL-Z"),
                vigente_z,
            ),
            _crear_contrato_prueba(
                _crear_inmueble_prueba("LOCAL-A"),
                vigente_a,
            ),
            _crear_contrato_prueba(
                _crear_inmueble_prueba("LOCAL-HZ"),
                historico_z,
                fecha_fin=date(2025, 6, 30),
            ),
            _crear_contrato_prueba(
                _crear_inmueble_prueba("LOCAL-HA"),
                historico_a,
                fecha_fin=date(2025, 6, 30),
            ),
        ])

        session.commit()

    response = client.get("/inquilinos/")

    assert response.status_code == 200

    html = response.text

    assert (
        html.index("<h2>Vigentes</h2>")
        < html.index("Vigente A")
        < html.index("Vigente Z")
        < html.index("<h2>Históricos</h2>")
        < html.index("Historico A")
        < html.index("Historico Z")
    )

    html = " ".join(html.split())

    assert "Vigente A - 22222222B - LOCAL-A" in html
    assert "Vigente Z - 11111111A - LOCAL-Z" in html
    assert "Historico A - 44444444D - LOCAL-HA" in html
    assert "Historico Z - 33333333C - LOCAL-HZ" in html


def test_listado_inquilino_con_varios_contratos_vigentes() -> None:
    """Muestra las referencias vigentes ordenadas y omite las históricas."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        session.add_all([
            _crear_contrato_prueba(
                _crear_inmueble_prueba("LOCAL-Z"),
                inquilino,
            ),
            _crear_contrato_prueba(
                _crear_inmueble_prueba("LOCAL-A"),
                inquilino,
            ),
            _crear_contrato_prueba(
                _crear_inmueble_prueba("LOCAL-ANTIGUO"),
                inquilino,
                fecha_fin=date(2025, 6, 30),
            ),
        ])

        session.commit()

    response = client.get("/inquilinos/")

    assert response.status_code == 200

    html = " ".join(response.text.split())

    assert (
        "Ana Pérez - 11111111A - LOCAL-A, LOCAL-Z"
        in html
    )

    assert html.count("Ana Pérez") == 1
    assert "LOCAL-ANTIGUO" not in html
    assert "No hay inquilinos históricos." in html


def test_listado_inquilino_historico_sin_referencias_duplicadas() -> None:
    """Muestra una sola vez cada inmueble de los contratos finalizados."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        inmueble_a = _crear_inmueble_prueba("LOCAL-A")
        inmueble_b = _crear_inmueble_prueba("LOCAL-B")

        # Dos contratos sucesivos sobre un mismo inmueble.
        session.add_all([
            _crear_contrato_prueba(
                inmueble_a,
                inquilino,
                fecha_inicio=date(2021, 1, 1),
                fecha_fin=date(2022, 12, 31),
            ),
            _crear_contrato_prueba(
                inmueble_a,
                inquilino,
                fecha_inicio=date(2023, 1, 1),
                fecha_fin=date(2024, 12, 31),
            ),
            _crear_contrato_prueba(
                inmueble_b,
                inquilino,
                fecha_inicio=date(2025, 1, 1),
                fecha_fin=date(2025, 6, 30),
            ),
        ])

        session.commit()

    response = client.get("/inquilinos/")

    assert response.status_code == 200

    html = " ".join(response.text.split())

    assert (
        "Ana Pérez - 11111111A - LOCAL-A, LOCAL-B"
        in html
    )

    assert html.count("LOCAL-A") == 1
    assert html.count("Ana Pérez") == 1
    assert "No hay inquilinos vigentes." in html

    assert (
        html.index("<h2>Históricos</h2>")
        < html.index("Ana Pérez")
    )


def test_listado_inquilino_sin_contratos() -> None:
    """Incluye en históricos los inquilinos sin contratos asociados."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        session.add(
            Inquilino(
                nombre="Ana Pérez",
                nif="11111111A",
            )
        )
        session.commit()

    response = client.get("/inquilinos/")

    assert response.status_code == 200

    html = " ".join(response.text.split())

    assert "No hay inquilinos vigentes." in html
    assert "Ana Pérez - 11111111A - Sin contrato" in html

    assert (
        html.index("<h2>Históricos</h2>")
        < html.index("Ana Pérez")
    )


def test_listado_inquilinos_con_contrato_vencido_no_finalizado() -> None:
    """El vencimiento no implica que los titulares sean históricos."""

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

        # Ambos son titulares de un contrato vencido,
        # pero que no se ha finalizado expresamente.
        session.add(
            _crear_contrato_prueba(
                _crear_inmueble_prueba("LOCAL-A"),
                primero,
                segundo,
                fecha_inicio=date(2021, 1, 1),
                fecha_vencimiento=date(2022, 12, 31),
            )
        )

        session.commit()

    response = client.get("/inquilinos/")

    assert response.status_code == 200

    html = " ".join(response.text.split())

    assert "Ana Pérez - 11111111A - LOCAL-A" in html
    assert "Luis García - 22222222B - LOCAL-A" in html

    assert (
        html.index("<h2>Vigentes</h2>")
        < html.index("Ana Pérez")
        < html.index("Luis García")
        < html.index("<h2>Históricos</h2>")
    )

    assert "No hay inquilinos históricos." in html


def test_listado_inquilino_con_contrato_futuro_no_finalizado() -> None:
    """Mantiene el mismo criterio de vigencia que el listado de contratos."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        session.add(
            _crear_contrato_prueba(
                _crear_inmueble_prueba("LOCAL-A"),
                inquilino,
                fecha_inicio=date(2090, 1, 1),
                fecha_vencimiento=date(2095, 12, 31),
            )
        )

        session.commit()

    response = client.get("/inquilinos/")

    assert response.status_code == 200

    html = " ".join(response.text.split())

    assert "Ana Pérez - 11111111A - LOCAL-A" in html

    assert (
        html.index("<h2>Vigentes</h2>")
        < html.index("Ana Pérez")
        < html.index("<h2>Históricos</h2>")
    )



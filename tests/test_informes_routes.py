"""Pruebas de las rutas web del módulo de informes."""

from datetime import date

from contab.app import create_app
from contab.database import Base
from contab.models import ApunteContable, Inmueble


def crear_app_test():
    """Crea una aplicación aislada para las pruebas."""
    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="test-secret-key",
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

    return app


def test_indice_de_informes() -> None:
    """Comprueba que se muestra el índice de informes."""
    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/informes/")

    assert response.status_code == 200
    assert "Informes" in response.text
    assert (
        "Exportar apuntes para declaración de IVA"
        in response.text
    )
    assert 'href="/informes/iva"' in response.text


def test_formulario_exportacion_iva_muestra_inmuebles() -> None:
    """Comprueba las opciones del formulario de exportación."""
    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    # Preparamos dos inmuebles, incluido uno inactivo.
    with session_factory() as session:
        primero = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección 1",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        segundo = Inmueble(
            referencia="PISO-2",
            tipo="P",
            codigo_facturacion="P2",
            descripcion="Piso inactivo",
            direccion="Dirección 2",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            activo=False,
        )

        session.add_all([primero, segundo])
        session.commit()

    client = app.test_client()
    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/informes/iva")

    assert response.status_code == 200
    assert (
        "Exportar apuntes para declaración de IVA"
        in response.text
    )
    assert 'name="inmueble_id"' in response.text
    assert 'name="anio"' in response.text
    assert "LOCAL-1" in response.text
    assert "Local comercial" in response.text
    assert "PISO-2" in response.text
    assert "Piso inactivo" in response.text
    assert "Exportar CSV" in response.text
    assert 'href="/informes/"' in response.text


def test_exportar_iva_descarga_csv() -> None:
    """Comprueba la descarga del CSV solicitado."""
    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    # Preparamos el inmueble y uno de sus apuntes.
    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 1, 5),
            naturaleza="INGRESO",
            categoria="ING_ALQUILER",
            concepto="Alquiler enero",
            base=100000,
            iva_importe=21000,
            retencion_importe=19000,
            total=102000,
            tratamiento="CONTABILIZAR",
            nombre_documento="Factura enero.pdf",
        )

        session.add_all([inmueble, apunte])
        session.commit()

        inmueble_id = inmueble.id

    client = app.test_client()
    client.post(
        "/",
        data={"database": "test"},
    )

    # Simulamos la selección del inmueble y del año.
    response = client.post(
        "/informes/iva",
        data={
            "inmueble_id": str(inmueble_id),
            "anio": "2026",
        },
    )

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.headers[
        "Content-Disposition"
    ] == (
        'attachment; '
        'filename="iva-LOCAL-1-2026.csv"'
    )

    assert (
        ";Alquiler enero;1.000,00;;210,00;190,00"
        in response.text
    )
    assert (
        ";Totales del año;1.000,00;0,00;210,00;190,00"
        in response.text
    )



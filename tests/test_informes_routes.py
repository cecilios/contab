"""Pruebas de las rutas web del módulo de informes."""

from datetime import date
from io import BytesIO
from zipfile import ZipFile

from contab.app import create_app
from contab.database import Base
from contab.models import (
    ApunteContable,
    Contrato,
    Inmueble,
)



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
    assert "IVA. Resumen anual" in response.text
    assert (
        'href="/informes/iva-resumen-anual"'
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
    assert 'value="todos"' in response.text
    assert "Todos los inmuebles" in response.text


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


def test_exportar_iva_todos_descarga_zip() -> None:
    """Descarga los CSV aplicables dentro de un único ZIP."""
    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    # Preparamos un activo, un inactivo con apuntes
    # y otro inactivo sin apuntes.
    with session_factory() as session:
        activo = Inmueble(
            referencia="ACTIVO",
            tipo="L",
            codigo_facturacion="ACT",
            descripcion="Inmueble activo",
            direccion="Dirección 1",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inactivo_con_apuntes = Inmueble(
            referencia="INACTIVO-CON-APUNTES",
            tipo="L",
            codigo_facturacion="ICA",
            descripcion="Inactivo con apuntes",
            direccion="Dirección 2",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            activo=False,
        )
        inactivo_sin_apuntes = Inmueble(
            referencia="INACTIVO-SIN-APUNTES",
            tipo="L",
            codigo_facturacion="ISA",
            descripcion="Inactivo sin apuntes",
            direccion="Dirección 3",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            activo=False,
        )

        apunte = ApunteContable(
            inmueble=inactivo_con_apuntes,
            fecha=date(2026, 3, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
            tratamiento="CONTABILIZAR",
            nombre_documento="Comunidad.pdf",
        )

        session.add_all(
            [
                activo,
                inactivo_con_apuntes,
                inactivo_sin_apuntes,
                apunte,
            ]
        )
        session.commit()

    client = app.test_client()
    client.post(
        "/",
        data={"database": "test"},
    )

    # Solicitamos la exportación conjunta.
    response = client.post(
        "/informes/iva",
        data={
            "inmueble_id": "todos",
            "anio": "2026",
        },
    )

    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert response.headers[
        "Content-Disposition"
    ] == (
        'attachment; filename="iva-2026.zip"'
    )

    # Comprobamos qué inmuebles contiene el ZIP.
    with ZipFile(BytesIO(response.data)) as archivo:
        assert archivo.namelist() == [
            "iva-ACTIVO-2026.csv",
            "iva-INACTIVO-CON-APUNTES-2026.csv",
        ]

        contenido = archivo.read(
            "iva-INACTIVO-CON-APUNTES-2026.csv"
        ).decode("utf-8")

    assert "Comunidad" in contenido


def test_exportar_iva_rechaza_formulario_incompleto() -> None:
    """Comprueba que inmueble y año son obligatorios."""
    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        "/informes/iva",
        data={
            "inmueble_id": "",
            "anio": "",
        },
    )

    assert response.status_code == 400
    assert (
        "Debe seleccionar un inmueble "
        "e indicar un año válido."
        in response.text
    )
    assert 'name="inmueble_id"' in response.text
    assert 'name="anio"' in response.text


def test_exportar_iva_rechaza_inmueble_inexistente() -> None:
    """Comprueba que el inmueble solicitado debe existir."""
    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        "/informes/iva",
        data={
            "inmueble_id": "999999",
            "anio": "2026",
        },
    )

    assert response.status_code == 400
    assert (
        "El inmueble seleccionado no existe."
        in response.text
    )
    assert 'value="2026"' in response.text


def test_formulario_resumen_anual_iva() -> None:
    """Muestra el formulario con sus valores iniciales."""
    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/informes/iva-resumen-anual"
    )

    assert response.status_code == 200
    assert "IVA. Resumen anual" in response.text
    assert 'name="anio"' in response.text
    assert (
        f'value="{date.today().year}"'
        in response.text
    )
    assert (
        'name="porcentaje_irpf_estimado"'
        in response.text
    )
    assert 'value="24,00"' in response.text
    assert "Porcentaje IRPF / IRNR:" in response.text
    assert "Generar CSV" in response.text
    assert 'href="/informes/"' in response.text


def test_descargar_resumen_anual_iva() -> None:
    """Genera el CSV usando el porcentaje indicado."""
    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    # Preparamos un piso sin retención y su contrato.
    with session_factory() as session:
        inmueble = Inmueble(
            referencia="PISO-1",
            tipo="P",
            codigo_facturacion="P1",
            descripcion="Piso",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        contrato = Contrato(
            inmueble=inmueble,
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=False,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=0,
            direccion_facturacion="",
            poblacion_facturacion="",
            provincia_facturacion="",
            concepto_factura="",
        )
        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 1, 5),
            naturaleza="INGRESO",
            categoria="ING_ALQUILER",
            concepto="Alquiler enero",
            base=80000,
            iva_importe=0,
            retencion_importe=0,
            total=80000,
            tratamiento="CONTABILIZAR",
            nombre_documento="Ingreso enero.pdf",
        )

        session.add_all(
            [inmueble, contrato, apunte]
        )
        session.commit()

    client = app.test_client()
    client.post(
        "/",
        data={"database": "test"},
    )

    # Solicitamos el informe con una estimación del 25 %.
    response = client.post(
        "/informes/iva-resumen-anual",
        data={
            "anio": "2026",
            "porcentaje_irpf_estimado": "25,00",
        },
    )

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.headers[
        "Content-Disposition"
    ] == (
        'attachment; filename="'
        'iva-resumen-anual-2026.csv"'
    )

    assert (
        "PISO-1;800,00;0,00;200,00;0,00;600,00"
        in response.text
    )



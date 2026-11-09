
"""Pruebas de la pantalla de situación económica del contrato."""

from datetime import date, timedelta

from contab.app import create_app
from contab.database import Base
from contab.models import Contrato, Inmueble


def crear_app_test():
    """Crea una aplicación aislada con SQLite en memoria."""

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


def test_situacion_contrato_muestra_selector():
    """El usuario puede abrir la pantalla sin elegir contrato."""

    app = crear_app_test()
    client = app.test_client()

    # El usuario selecciona la base de datos de trabajo.
    client.post(
        "/",
        data={"database": "test"},
    )

    # Abre la pantalla de situación económica.
    response = client.get("/contratos/situacion")

    assert response.status_code == 200
    assert "Situación económica del contrato" in response.text
    assert 'name="inmueble_id"' in response.text
    assert 'name="contrato_id"' in response.text
    assert 'name="fecha_desde"' in response.text


def test_situacion_contrato_sin_movimientos():
    """Un contrato sin movimientos muestra saldo cero."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    # El usuario dispone de un inmueble y un contrato.
    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección de prueba",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        contrato = Contrato(
            inmueble=inmueble,
            fecha_inicio=date(2026, 1, 15),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 2, 1),
            fianza=100000,
            direccion_facturacion="Dirección",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
        )

        session.add(contrato)
        session.commit()

        inmueble_id = inmueble.id
        contrato_id = contrato.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # El usuario selecciona el contrato para consultar
    # su situación económica desde el inicio del año.
    response = client.get(
        "/contratos/situacion",
        query_string={
            "inmueble_id": inmueble_id,
            "contrato_id": contrato_id,
            "fecha_desde": "01/01/2026",
        },
    )

    assert response.status_code == 200

    # Aparecen el inmueble y los tres conceptos
    # principales del resumen económico.
    assert "LOCAL-1" in response.text
    assert "Total a ingresar" in response.text
    assert "Total ingresado" in response.text
    assert "Saldo pendiente" in response.text

    # El período termina hoy, automáticamente.
    assert date.today().strftime(
        "%d/%m/%Y"
    ) in response.text

    # No hay facturas, cobros ni deudas.
    assert response.text.count("0,00") >= 3


def test_selector_solo_muestra_contratos_del_inmueble_y_periodo():
    """El selector no mezcla contratos ni ofrece finalizados."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        local_1 = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local uno",
            direccion="Dirección 1",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        local_2 = Inmueble(
            referencia="LOCAL-2",
            tipo="L",
            codigo_facturacion="A2",
            descripcion="Local dos",
            direccion="Dirección 2",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        def crear_contrato(inmueble, inicio, fin=None):
            return Contrato(
                inmueble=inmueble,
                fecha_inicio=inicio,
                fecha_vencimiento=date(2030, 12, 31),
                fecha_fin=fin,
                genera_factura=True,
                fecha_inicio_facturacion=inicio,
                fianza=100000,
                direccion_facturacion="Dirección",
                poblacion_facturacion="Pontevedra",
                provincia_facturacion="Pontevedra",
                concepto_factura="Alquiler",
            )

        vigente = crear_contrato(
            local_1,
            date(2026, 1, 1),
        )

        finalizado = crear_contrato(
            local_1,
            date(2025, 1, 1),
            date(2026, 6, 30),
        )

        otro_local = crear_contrato(
            local_2,
            date(2026, 2, 1),
        )

        session.add_all([
            vigente,
            finalizado,
            otro_local,
        ])
        session.commit()

        inmueble_id = local_1.id
        vigente_id = vigente.id
        finalizado_id = finalizado.id
        otro_local_id = otro_local.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # El usuario consulta el Local 1 desde julio, después de la
    # finalización del contrato anterior.
    response = client.get(
        "/contratos/situacion",
        query_string={
            "inmueble_id": inmueble_id,
            "fecha_desde": "01/07/2026",
        },
    )

    assert response.status_code == 200

    # Se comprueban únicamente las opciones del selector
    # de contratos, no el resto de la página.
    html = response.text
    selector = html.split('name="contrato_id"', 1)[1]
    selector = selector.split("</select>", 1)[0]

    assert f'value="{vigente_id}"' in selector
    assert f'value="{finalizado_id}"' not in selector
    assert f'value="{otro_local_id}"' not in selector


def test_situacion_tiene_tablas_y_totales_fuera_de_ellas():
    """La pantalla dispone del detalle y resumen definitivos."""

    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    # El usuario abre la pantalla sin seleccionar contrato.
    response = client.get("/contratos/situacion")

    assert response.status_code == 200

    # La fecha de hoy forma parte del título.
    assert (
        "a fecha "
        + date.today().strftime("%d/%m/%Y")
    ) in response.text

    # La plantilla ya contiene los estilos propios
    # de los filtros, las tablas y los totales.
    assert 'class="situacion-contrato__filtros no-imprimir"' in response.text

    # El bloque de resultados se muestra cuando
    # existe un contrato seleccionado. Comprobamos
    # que las clases están presentes en la plantilla
    # en una segunda prueba con contrato.
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

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

        contrato = Contrato(
            inmueble=inmueble,
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            direccion_facturacion="Dirección",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
        )

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id

    response = client.get(
        "/contratos/situacion",
        query_string={"contrato_id": contrato_id},
    )

    assert response.status_code == 200
    assert "situacion-contrato__tabla-exigibles" in response.text
    assert "situacion-contrato__tabla-cobros" in response.text
    assert "situacion-contrato__totales" in response.text
    assert "No hay exigibles en el período." in response.text
    assert "No hay cobros ni devoluciones" in response.text

    # El encabezado del contrato se conserva en el informe imprimible.
    assert '<h2 class="situacion-contrato__contrato">' in response.text

    # Las cifras del resumen no están dentro
    # de ninguna de las dos tablas.
    inicio_totales = response.text.index(
        'class="situacion-contrato__totales"'
    )

    cierre_ultima_tabla = response.text.rfind("</table>")

    assert inicio_totales > cierre_ultima_tabla


def test_selector_incluye_contratos_vigentes_desde_fecha():
    """Incluye contratos anteriores que seguían vigentes en el período."""

    app = crear_app_test()
    session_factory = app.extensions["contab_databases"]["test"]

    hoy = date.today()
    fecha_desde = hoy - timedelta(days=100)

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

        def crear_contrato(inicio, fin=None):
            return Contrato(
                inmueble=inmueble,
                fecha_inicio=inicio,
                fecha_vencimiento=inicio + timedelta(days=730),
                fecha_fin=fin,
                genera_factura=True,
                fecha_inicio_facturacion=inicio,
                fianza=100000,
                direccion_facturacion="Dirección",
                poblacion_facturacion="Pontevedra",
                provincia_facturacion="Pontevedra",
                concepto_factura="Alquiler",
            )

        # Este contrato terminó antes del período.
        antiguo = crear_contrato(
            hoy - timedelta(days=350),
            hoy - timedelta(days=160),
        )

        # Este terminó dentro del período consultado.
        anterior = crear_contrato(
            hoy - timedelta(days=300),
            hoy - timedelta(days=40),
        )

        # Este contrato sigue vigente.
        actual = crear_contrato(
            hoy - timedelta(days=20),
        )

        # Este todavía no ha comenzado.
        futuro = crear_contrato(
            hoy + timedelta(days=10),
        )

        session.add_all([antiguo, anterior, actual, futuro])
        session.commit()

        inmueble_id = inmueble.id
        antiguo_id = antiguo.id
        anterior_id = anterior.id
        actual_id = actual.id
        futuro_id = futuro.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # El usuario selecciona el inmueble y una fecha
    # anterior al comienzo del contrato actual.
    response = client.get(
        "/contratos/situacion",
        query_string={
            "inmueble_id": inmueble_id,
            "fecha_desde": fecha_desde.strftime("%d/%m/%Y"),
        },
    )

    assert response.status_code == 200

    # Revisar únicamente las opciones del selector.
    selector = response.text.split(
        'name="contrato_id"', 1
    )[1].split("</select>", 1)[0]

    assert f'value="{anterior_id}"' in selector
    assert f'value="{actual_id}"' in selector

    assert f'value="{antiguo_id}"' not in selector
    assert f'value="{futuro_id}"' not in selector

    # Los controles y la navegación no se imprimen.
    assert 'situacion-contrato__titulo no-imprimir' in response.text
    assert 'situacion-contrato__filtros no-imprimir' in response.text
    assert 'situacion-contrato__navegacion no-imprimir' in response.text

    # El enlace utiliza la impresión del navegador.
    assert "window.print()" in response.text


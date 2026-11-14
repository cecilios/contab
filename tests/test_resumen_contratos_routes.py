
"""Pruebas de la pantalla de resumen económico de contratos."""

import re

from datetime import date

from contab.app import create_app
from contab.database import Base
from contab.models import (
    ApunteContable,
    Conciliacion,
    Contrato,
    Inmueble,
    MovimientoBancario,
    MovimientoPrevisto,
)


DATOS_PROPIEDAD = {
    "porcentaje_titular": 10000,
    "tipo_derecho": "PLENA_PROPIEDAD",
    "porcentaje_derecho": 10000,
    "fecha_adquisicion": date(2020, 1, 1),
    "tipo_adquisicion": "ONEROSA",
    "importe_adquisicion": 0,
    "gastos_adquisicion": 0,
}



def _crear_app_test():
    """Crea una aplicación aislada para las pruebas."""

    app = create_app(
        databases={"test": "sqlite:///:memory:"},
        secret_key="test-secret-key",
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

    return app


def _crear_contrato_prueba(
    session,
    inmueble,
    *,
    inicio,
    fin=None,
):
    """Registra un contrato de alquiler válido."""

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=inicio,
        fecha_vencimiento=date(inicio.year + 5, 12, 31),
        fecha_fin=fin,
        genera_factura=False,
        fecha_inicio_facturacion=inicio,
        fianza=0,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )

    session.add(contrato)
    session.flush()

    return contrato


def _registrar_alquiler_prueba(
    session,
    contrato,
    *,
    fecha,
    importe,
    cobrado,
    referencia,
):
    """Registra una obligación y, opcionalmente, su cobro manual."""

    apunte = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=fecha,
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto=f"Alquiler {referencia}",
        base=importe,
        iva_importe=0,
        retencion_importe=0,
        total=importe,
    )

    previsto = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        apunte=apunte,
        naturaleza="INGRESO",
        concepto=apunte.concepto,
        importe_esperado=importe,
        fecha_prevista_desde=fecha,
        estado=(
            "CONCILIADO"
            if cobrado
            else "PENDIENTE"
        ),
        metodo_conciliacion=(
            "MANUAL"
            if cobrado
            else None
        ),
        notas=(
            "Cobrado fuera de la cuenta bancaria"
            if cobrado
            else None
        ),
    )

    session.add_all([apunte, previsto])
    session.flush()


def test_resumen_contratos_sin_datos():
    """El usuario abre el resumen aunque no haya contratos."""

    app = _crear_app_test()
    client = app.test_client()

    # El usuario selecciona su base de datos.
    client.post(
        "/",
        data={"database": "test"},
    )

    # Abre el resumen general de contratos.
    response = client.get("/contratos/resumen")

    assert response.status_code == 200

    assert "Resumen económico de contratos" in response.text
    assert 'name="ejercicio"' in response.text
    assert str(date.today().year) in response.text

    assert "No hay contratos para el ejercicio" in response.text


def test_resumen_separa_contratos_y_acumula_saldos():
    """Dos contratos de un inmueble conservan sus propias deudas."""

    app = _crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    ejercicio = date.today().year - 1
    anio_anterior = ejercicio - 1

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            **DATOS_PROPIEDAD,
        )

        # El inmueble tuvo dos contratos sucesivos.
        anterior = _crear_contrato_prueba(
            session,
            inmueble,
            inicio=date(anio_anterior, 1, 1),
            fin=date(ejercicio, 6, 30),
        )

        nuevo = _crear_contrato_prueba(
            session,
            inmueble,
            inicio=date(ejercicio, 7, 1),
        )

        # El contrato anterior arrastra una deuda
        # de 200 euros del ejercicio precedente.
        _registrar_alquiler_prueba(
            session,
            anterior,
            fecha=date(anio_anterior, 12, 10),
            importe=100000,
            cobrado=False,
            referencia="DICIEMBRE-ANTERIOR",
        )

        # El inquilino anterior pagó 800 euros mediante
        # un cobro manual independiente, asociado al contrato.
        cobro_anterior = MovimientoPrevisto(
            inmueble=inmueble,
            contrato=anterior,
            naturaleza="INGRESO",
            concepto="Pago parcial diciembre anterior",
            importe_esperado=80000,
            fecha_prevista_desde=date(anio_anterior, 12, 15),
            estado="CONCILIADO",
            metodo_conciliacion="MANUAL",
            notas="Cobrado en efectivo",
        )

        session.add(cobro_anterior)

        # En el ejercicio seleccionado, el contrato
        # anterior tiene otros 500 euros exigibles.
        _registrar_alquiler_prueba(
            session,
            anterior,
            fecha=date(ejercicio, 1, 10),
            importe=50000,
            cobrado=False,
            referencia="ENERO",
        )

        # El usuario confirma un cobro parcial de 300 euros.
        cobro_ejercicio = MovimientoPrevisto(
            inmueble=inmueble,
            contrato=anterior,
            naturaleza="INGRESO",
            concepto="Pago parcial enero",
            importe_esperado=30000,
            fecha_prevista_desde=date(ejercicio, 1, 15),
            estado="CONCILIADO",
            metodo_conciliacion="MANUAL",
            notas="Cobrado fuera de la cuenta bancaria",
        )

        session.add(cobro_ejercicio)

        # El nuevo contrato tiene 700 euros exigibles,
        # íntegramente cobrados.
        _registrar_alquiler_prueba(
            session,
            nuevo,
            fecha=date(ejercicio, 8, 10),
            importe=70000,
            cobrado=True,
            referencia="AGOSTO",
        )

        session.commit()

        anterior_id = anterior.id
        nuevo_id = nuevo.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # El usuario consulta el ejercicio anterior.
    response = client.get(
        "/contratos/resumen",
        query_string={"ejercicio": ejercicio},
    )

    assert response.status_code == 200

    # La pantalla identifica cada contrato
    # mediante su propio registro.
    html = response.text

    def fila_contrato(contrato_id):
        patron = (
            rf'<tr[^>]*data-contrato-id="{contrato_id}"'
            rf'[^>]*>(.*?)</tr>'
        )

        coincidencia = re.search(
            patron,
            html,
            re.DOTALL,
        )

        assert coincidencia is not None
        return coincidencia.group(1)

    fila_anterior = fila_contrato(anterior_id)
    fila_nueva = fila_contrato(nuevo_id)

    # Contrato anterior:
    # 500 exigibles, 300 cobrados este ejercicio.
    # Saldo acumulado: 200 anteriores + 200 nuevos.
    assert "500,00" in fila_anterior
    assert "300,00" in fila_anterior
    assert "400,00" in fila_anterior

    # Contrato nuevo:
    # 700 exigibles, 700 cobrados, saldo cero.
    assert "700,00" in fila_nueva
    assert "0,00" in fila_nueva
    assert "400,00" not in fila_nueva

    # Cada contrato enlaza con su situación individual.
    assert f"contrato_id={anterior_id}" in fila_anterior
    assert f"contrato_id={nuevo_id}" in fila_nueva

    # Los totales generales corresponden a:
    # 1.200 exigibles, 1.000 cobrados y
    # 400 de saldo acumulado.
    assert "1.200,00" in html
    assert "1.000,00" in html
    assert "400,00" in html


def test_resumen_calcula_pendiente_de_conciliar():
    """Suma saldos pendientes y excluye diferencias aceptadas."""

    app = _crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    hoy = date.today()

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-CONCILIACION",
            tipo="L",
            codigo_facturacion="C1",
            descripcion="Local de prueba",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            **DATOS_PROPIEDAD,
        )

        contrato = _crear_contrato_prueba(
            session,
            inmueble,
            inicio=date(hoy.year - 1, 1, 1),
        )

        # Primer movimiento: 1.000 euros previstos,
        # 600 conciliados y 400 todavía pendientes.
        parcial = MovimientoPrevisto(
            inmueble=inmueble,
            contrato=contrato,
            naturaleza="INGRESO",
            concepto="Alquiler parcialmente cobrado",
            importe_esperado=100000,
            fecha_prevista_desde=date(hoy.year, 1, 10),
            estado="PARCIAL",
        )

        bancario_parcial = MovimientoBancario(
            fecha=date(hoy.year, 1, 12),
            naturaleza="INGRESO",
            importe=60000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="Cobro parcial",
            huella_importacion="RESUMEN-PARCIAL",
            estado="CONCILIADO",
        )

        conciliacion_parcial = Conciliacion(
            movimiento_previsto=parcial,
            movimiento_bancario=bancario_parcial,
            importe_asociado=60000,
        )

        # Segundo movimiento: 500 euros previstos,
        # 450 cobrados y diferencia aceptada.
        # No debe aportar 50 euros pendientes de conciliar.
        cerrado = MovimientoPrevisto(
            inmueble=inmueble,
            contrato=contrato,
            naturaleza="INGRESO",
            concepto="Alquiler cerrado con diferencia",
            importe_esperado=50000,
            fecha_prevista_desde=date(hoy.year, 2, 10),
            estado="CONCILIADO",
            metodo_conciliacion="INDIVIDUAL",
        )

        bancario_cerrado = MovimientoBancario(
            fecha=date(hoy.year, 2, 12),
            naturaleza="INGRESO",
            importe=45000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="Cobro con diferencia aceptada",
            huella_importacion="RESUMEN-CERRADO",
            estado="CONCILIADO",
        )

        conciliacion_cerrada = Conciliacion(
            movimiento_previsto=cerrado,
            movimiento_bancario=bancario_cerrado,
            importe_asociado=45000,
            cierra_previsto=True,
        )

        session.add_all([
            parcial,
            bancario_parcial,
            conciliacion_parcial,
            cerrado,
            bancario_cerrado,
            conciliacion_cerrada,
        ])

        session.commit()
        contrato_id = contrato.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.get("/contratos/resumen")

    assert response.status_code == 200

    # El importe pendiente es 1.000 - 600 = 400 euros.
    # No incluye los 50 euros de diferencia aceptada.
    patron = (
        rf'<tr[^>]*data-contrato-id="{contrato_id}"'
        rf'[^>]*>(.*?)</tr>'
    )

    coincidencia = re.search(
        patron,
        response.text,
        re.DOTALL,
    )

    assert coincidencia is not None
    fila = coincidencia.group(1)

    assert "400,00 €" in fila

    # El total general contiene el mismo importe.
    assert (
        "total_pendiente_conciliar"
        not in response.text
    )
    assert response.text.count("400,00 €") >= 2

    # El acceso a conciliación apunta a la ruta existente.
    assert "/conciliacion/revisar" in response.text
    assert "Revisar conciliación" in response.text


def test_resumen_incluye_contrato_antiguo_con_conciliacion_pendiente():
    """Un contrato antiguo aparece si aún necesita conciliación."""

    app = _crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    ejercicio = date.today().year

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-ANTIGUO",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local antiguo",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            **DATOS_PROPIEDAD,
        )

        # Finalizó antes del ejercicio actual.
        contrato = _crear_contrato_prueba(
            session,
            inmueble,
            inicio=date(ejercicio - 3, 1, 1),
            fin=date(ejercicio - 2, 12, 31),
        )

        # No hay facturas ni apuntes exigibles.
        # Solo queda este movimiento pendiente.
        previsto = MovimientoPrevisto(
            inmueble=inmueble,
            contrato=contrato,
            naturaleza="INGRESO",
            concepto="Cobro antiguo pendiente de conciliar",
            importe_esperado=25000,
            fecha_prevista_desde=date(ejercicio - 2, 12, 10),
            estado="PENDIENTE",
        )

        session.add(previsto)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.get(
        "/contratos/resumen",
        query_string={"ejercicio": ejercicio},
    )

    assert response.status_code == 200

    patron = (
        rf'<tr[^>]*data-contrato-id="{contrato_id}"'
        rf'[^>]*>(.*?)</tr>'
    )

    coincidencia = re.search(
        patron,
        response.text,
        re.DOTALL,
    )

    assert coincidencia is not None
    fila = coincidencia.group(1)

    # El contrato aparece exclusivamente porque
    # conserva 250 euros pendientes de conciliar.
    assert "LOCAL-ANTIGUO" in fila
    assert "250,00 €" in fila

    # No existen exigibles ni cobros económicos
    # atribuidos a ese contrato.
    assert fila.count("0,00 €") >= 3


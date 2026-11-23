
"""Pruebas de la pantalla de resumen económico de contratos."""

import re

from datetime import date
from sqlalchemy import func, select

from contab.app import create_app
from contab.database import Base
from contab.models import (
    ApunteContable,
    Conciliacion,
    Contrato,
    ImputacionContrato,
    Inmueble,
    MovimientoBancario,
    MovimientoPrevisto,
    SolicitudReembolso,
    SolicitudReembolsoLinea,
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
    return apunte


def _registrar_gasto_reembolso_prueba(
    session,
    contrato,
    *,
    fecha,
    importe,
    negativo=False,
):
    """Registra un gasto repercutible aún sin gestionar."""

    apunte = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=fecha,
        naturaleza="GASTO",
        categoria="GAS_AGUA",
        concepto="Gasto repercutible de prueba",
        tratamiento="REPERCUTIR",
        importe_negativo=negativo,
        base=importe,
        iva_importe=0,
        retencion_importe=0,
        total=importe,
    )

    session.add(apunte)
    return apunte


def _fila_resumen_contrato(html, contrato_id):
    coincidencia = re.search(
        rf'<tr[^>]*data-contrato-id="{contrato_id}"'
        rf'[^>]*>(.*?)</tr>',
        html,
        re.DOTALL,
    )
    assert coincidencia is not None
    return coincidencia.group(1)





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
        apunte_diciembre = _registrar_alquiler_prueba(
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
            apunte=apunte_diciembre,
        )

        session.add(cobro_anterior)

        # En el ejercicio seleccionado, el contrato
        # anterior tiene otros 500 euros exigibles.
        apunte_enero = _registrar_alquiler_prueba(
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
            apunte=apunte_enero,
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


def test_resumen_filtra_contratos_por_vigencia_y_saldo():
    """Solo muestra vigentes y finalizados del año con saldo."""

    app = _crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    hoy = date.today()
    ejercicio = hoy.year

    with session_factory() as session:
        def crear_contrato(referencia, inicio, fin=None):
            inmueble = Inmueble(
                referencia=referencia,
                tipo="L",
                codigo_facturacion=referencia,
                descripcion=referencia,
                direccion="Dirección",
                poblacion="Pontevedra",
                provincia="Pontevedra",
                **DATOS_PROPIEDAD,
            )
            session.add(inmueble)
            return _crear_contrato_prueba(
                session,
                inmueble,
                inicio=inicio,
                fin=fin,
            )

        # El propietario tiene un contrato vigente
        # sin deuda, que debe seguir apareciendo.
        vigente = crear_contrato(
            "VIGENTE",
            date(ejercicio - 1, 1, 1),
        )

        # El propietario tiene un contrato finalizado
        # este año con 200 euros pendientes de cobro.
        finalizado_deudor = crear_contrato(
            "FINAL-DEUDOR",
            date(ejercicio - 1, 1, 1),
            date(ejercicio, 1, 1),
        )
        _registrar_alquiler_prueba(
            session,
            finalizado_deudor,
            fecha=date(ejercicio, 1, 1),
            importe=20000,
            cobrado=False,
            referencia="DEUDA",
        )

        # Otro contrato terminó este año sin deuda.
        finalizado_saldado = crear_contrato(
            "FINAL-SALDADO",
            date(ejercicio - 1, 1, 1),
            date(ejercicio, 1, 1),
        )

        # Un contrato terminó el año anterior,
        # pero conserva una deuda de 300 euros.
        antiguo = crear_contrato(
            "ANTIGUO",
            date(ejercicio - 2, 1, 1),
            date(ejercicio - 1, 12, 31),
        )
        _registrar_alquiler_prueba(
            session,
            antiguo,
            fecha=date(ejercicio - 1, 12, 1),
            importe=30000,
            cobrado=False,
            referencia="ANTIGUA",
        )

        # Hay un contrato que empezará el año próximo.
        futuro = crear_contrato(
            "FUTURO",
            date(ejercicio + 1, 1, 1),
        )

        session.commit()

        ids = {
            "vigente": vigente.id,
            "deudor": finalizado_deudor.id,
            "saldado": finalizado_saldado.id,
            "antiguo": antiguo.id,
            "futuro": futuro.id,
        }

    client = app.test_client()

    # El usuario selecciona la base de datos.
    client.post("/", data={"database": "test"})

    # Consulta el resumen del ejercicio actual.
    response = client.get("/contratos/resumen")

    assert response.status_code == 200
    html = response.text

    assert f'data-contrato-id="{ids["vigente"]}"' in html
    assert f'data-contrato-id="{ids["deudor"]}"' in html

    assert f'data-contrato-id="{ids["saldado"]}"' not in html
    assert f'data-contrato-id="{ids["antiguo"]}"' not in html
    assert f'data-contrato-id="{ids["futuro"]}"' not in html

    # Los totales solo incluyen los contratos visibles.
    assert "200,00 €" in html
    assert "300,00 €" not in html


def test_resumen_filtra_contratos_en_ejercicio_anterior():
    """Aplica las reglas respecto al ejercicio seleccionado."""

    app = _crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    ejercicio = date.today().year - 1

    with session_factory() as session:
        def crear_contrato(referencia, inicio, fin=None):
            inmueble = Inmueble(
                referencia=referencia,
                tipo="L",
                codigo_facturacion=referencia,
                descripcion=referencia,
                direccion="Dirección",
                poblacion="Pontevedra",
                provincia="Pontevedra",
                **DATOS_PROPIEDAD,
            )
            session.add(inmueble)
            return _crear_contrato_prueba(
                session,
                inmueble,
                inicio=inicio,
                fin=fin,
            )

        # Vigente al cierre del ejercicio seleccionado.
        vigente = crear_contrato(
            "HIST-VIGENTE",
            date(ejercicio, 1, 1),
        )

        # Finalizado durante ese ejercicio con deuda.
        finalizado = crear_contrato(
            "HIST-FINAL",
            date(ejercicio - 1, 1, 1),
            date(ejercicio, 6, 30),
        )
        _registrar_alquiler_prueba(
            session,
            finalizado,
            fecha=date(ejercicio, 6, 1),
            importe=15000,
            cobrado=False,
            referencia="HISTORICA",
        )

        # Finalizado antes del ejercicio consultado.
        antiguo = crear_contrato(
            "HIST-ANTIGUO",
            date(ejercicio - 2, 1, 1),
            date(ejercicio - 1, 12, 31),
        )
        _registrar_alquiler_prueba(
            session,
            antiguo,
            fecha=date(ejercicio - 1, 12, 1),
            importe=25000,
            cobrado=False,
            referencia="ANTERIOR",
        )

        # Contrato iniciado después del ejercicio.
        posterior = crear_contrato(
            "HIST-POSTERIOR",
            date(ejercicio + 1, 1, 1),
        )

        session.commit()

        ids = {
            "vigente": vigente.id,
            "finalizado": finalizado.id,
            "antiguo": antiguo.id,
            "posterior": posterior.id,
        }

    client = app.test_client()

    # El usuario selecciona la base de datos.
    client.post("/", data={"database": "test"})

    # Consulta un ejercicio anterior.
    response = client.get(
        "/contratos/resumen",
        query_string={"ejercicio": ejercicio},
    )

    assert response.status_code == 200
    html = response.text

    assert f'data-contrato-id="{ids["vigente"]}"' in html
    assert f'data-contrato-id="{ids["finalizado"]}"' in html

    assert f'data-contrato-id="{ids["antiguo"]}"' not in html
    assert f'data-contrato-id="{ids["posterior"]}"' not in html

    assert "150,00 €" in html
    assert "250,00 €" not in html


def test_resumen_muestra_saldo_negativo_sin_columna_conciliacion():
    """El crédito del inquilino conserva su signo."""

    app = _crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    hoy = date.today()

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-CREDITO",
            tipo="L",
            codigo_facturacion="CR",
            descripcion="Local con saldo a favor",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            **DATOS_PROPIEDAD,
        )

        # El contrato está vigente.
        contrato = _crear_contrato_prueba(
            session,
            inmueble,
            inicio=date(hoy.year - 1, 1, 1),
        )

        # El usuario registra un alquiler de 1.000 euros.
        apunte_enero= _registrar_alquiler_prueba(
            session,
            contrato,
            fecha=date(hoy.year, 1, 1),
            importe=100000,
            cobrado=False,
            referencia="ENERO",
        )

        # El usuario confirma un cobro de 1.050 euros.
        # El contrato queda con 50 euros a favor del inquilino.
        cobro = MovimientoPrevisto(
            inmueble=inmueble,
            contrato=contrato,
            naturaleza="INGRESO",
            concepto="Cobro adicional",
            importe_esperado=105000,
            fecha_prevista_desde=date(hoy.year, 1, 2),
            estado="CONCILIADO",
            metodo_conciliacion="MANUAL",
            notas="Cobro confirmado fuera de la cuenta importada",
            apunte=apunte_enero,
        )

        session.add(cobro)
        session.commit()
        contrato_id = contrato.id

    client = app.test_client()

    # El usuario selecciona la base de datos.
    client.post("/", data={"database": "test"})

    # Consulta el resumen económico.
    response = client.get("/contratos/resumen")

    assert response.status_code == 200

    html = response.text

    patron = (
        rf'<tr[^>]*data-contrato-id="{contrato_id}"'
        rf'[^>]*>(.*?)</tr>'
    )
    coincidencia = re.search(patron, html, re.DOTALL)

    assert coincidencia is not None
    fila = coincidencia.group(1)

    assert "1.000,00 €" in fila
    assert "1.050,00 €" in fila
    assert "-50,00 €" in fila

    # El informe ya no presenta datos de conciliación.
    assert "Pendiente de conciliar" not in html

    # Quedan cuatro columnas económicas y la de detalle.
    assert html.count(
        'class="resumen-contratos__columna-importe"'
    ) == 4


def test_resumen_muestra_reembolsos_pendientes_de_solicitar():
    """Muestra gastos repercutibles aún no solicitados."""

    app = _crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    hoy = date.today()

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-REEMBOLSOS",
            tipo="L",
            codigo_facturacion="RE",
            descripcion="Local con gastos repercutibles",
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

        gasto_pendiente = ApunteContable(
            inmueble=inmueble,
            fecha=date(hoy.year, 3, 10),
            naturaleza="GASTO",
            categoria="GAS_AGUA",
            concepto="Agua pendiente",
            tratamiento="REPERCUTIR",
            base=4107,
            iva_importe=0,
            retencion_importe=0,
            total=4107,
        )

        gasto_no_repercutible = ApunteContable(
            inmueble=inmueble,
            fecha=date(hoy.year, 3, 11),
            naturaleza="GASTO",
            categoria="GAS_AGUA",
            concepto="Agua propietario",
            tratamiento="CONTABILIZAR",
            base=2000,
            iva_importe=0,
            retencion_importe=0,
            total=2000,
        )

        session.add_all([
            gasto_pendiente,
            gasto_no_repercutible,
        ])
        session.commit()
        contrato_id = contrato.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.get(
        "/contratos/resumen",
        query_string={"ejercicio": hoy.year},
    )

    assert response.status_code == 200

    html = response.text

    assert "Reembolsos pendientes de solicitar" in html

    coincidencia = re.search(
        rf'<tr[^>]*data-contrato-id="{contrato_id}"'
        rf'[^>]*>(.*?)</tr>',
        html,
        re.DOTALL,
    )

    assert coincidencia is not None
    assert "41,07 €" in coincidencia.group(1)

    # Consultar el informe no genera imputaciones.
    with session_factory() as session:
        assert session.scalar(
            select(func.count(ImputacionContrato.id))
        ) == 0


def test_resumen_no_duplica_reembolsos_ya_solicitados():
    """Solo suma gastos todavía pendientes de solicitar."""

    app = _crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]
    ejercicio = date.today().year

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-SOLICITADO",
            tipo="L",
            codigo_facturacion="SOL",
            descripcion="Local",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            **DATOS_PROPIEDAD,
        )

        contrato = _crear_contrato_prueba(
            session,
            inmueble,
            inicio=date(ejercicio - 1, 1, 1),
        )

        pendiente = _registrar_gasto_reembolso_prueba(
            session,
            contrato,
            fecha=date(ejercicio, 3, 10),
            importe=4107,
        )

        solicitado = _registrar_gasto_reembolso_prueba(
            session,
            contrato,
            fecha=date(ejercicio, 3, 11),
            importe=2530,
        )

        imputacion = ImputacionContrato(
            apunte=solicitado,
            contrato=contrato,
            base=2530,
            iva_importe=0,
            retencion_importe=0,
            importe=2530,
        )

        solicitud = SolicitudReembolso(
            contrato=contrato,
            fecha_envio=date(ejercicio, 4, 1),
        )

        linea = SolicitudReembolsoLinea(
            solicitud=solicitud,
            apunte=solicitado,
            concepto="Agua solicitada",
            importe=2530,
        )

        movimiento = MovimientoPrevisto(
            inmueble=inmueble,
            contrato=contrato,
            solicitud_reembolso=solicitud,
            naturaleza="INGRESO",
            concepto="Reembolso solicitado",
            importe_esperado=2530,
        )

        session.add_all([
            pendiente,
            imputacion,
            solicitud,
            linea,
            movimiento,
        ])
        session.commit()
        contrato_id = contrato.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.get(
        "/contratos/resumen",
        query_string={"ejercicio": ejercicio},
    )

    assert response.status_code == 200
    fila = _fila_resumen_contrato(
        response.text,
        contrato_id,
    )

    assert "41,07 €" in fila
    assert "66,37 €" not in fila


def test_resumen_reembolsos_pendientes_compensa_abonos():
    """Un gasto negativo reduce el reembolso pendiente."""

    app = _crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]
    ejercicio = date.today().year

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-ABONOS",
            tipo="L",
            codigo_facturacion="AB",
            descripcion="Local",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            **DATOS_PROPIEDAD,
        )

        contrato = _crear_contrato_prueba(
            session,
            inmueble,
            inicio=date(ejercicio - 1, 1, 1),
        )

        _registrar_gasto_reembolso_prueba(
            session,
            contrato,
            fecha=date(ejercicio, 3, 10),
            importe=4107,
        )

        _registrar_gasto_reembolso_prueba(
            session,
            contrato,
            fecha=date(ejercicio, 3, 11),
            importe=2530,
            negativo=True,
        )

        session.commit()
        contrato_id = contrato.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.get(
        "/contratos/resumen",
        query_string={"ejercicio": ejercicio},
    )

    assert response.status_code == 200
    fila = _fila_resumen_contrato(
        response.text,
        contrato_id,
    )

    # 41,07 - 25,30 = 15,77 €
    assert "15,77 €" in fila


def test_resumen_incluye_finalizado_con_reembolso_pendiente():
    """No oculta un contrato saldado con gastos por reclamar."""

    app = _crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]
    ejercicio = date.today().year

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-FINALIZADO-RE",
            tipo="L",
            codigo_facturacion="FRE",
            descripcion="Local",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            **DATOS_PROPIEDAD,
        )

        contrato = _crear_contrato_prueba(
            session,
            inmueble,
            inicio=date(ejercicio - 1, 1, 1),
            fin=date(ejercicio, 1, 31),
        )

        _registrar_gasto_reembolso_prueba(
            session,
            contrato,
            fecha=date(ejercicio, 1, 15),
            importe=4107,
        )

        session.commit()
        contrato_id = contrato.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.get(
        "/contratos/resumen",
        query_string={"ejercicio": ejercicio},
    )

    assert response.status_code == 200
    fila = _fila_resumen_contrato(
        response.text,
        contrato_id,
    )

    assert "41,07 €" in fila
    assert "0,00 €" in fila



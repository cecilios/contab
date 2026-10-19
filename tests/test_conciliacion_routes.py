import pytest
import re

from io import BytesIO
from datetime import date
from sqlalchemy import select

import contab.conciliacion.routes as rutas_conciliacion
from contab.app import create_app
from contab.conciliacion.services import (
    PropuestaConciliacion,
    buscar_propuestas_conciliacion,
)
from contab.database import Base
from contab.models import (
    Conciliacion,
    Contrato,
    Inmueble,
    MovimientoBancario,
    MovimientoPrevisto,
)




@pytest.fixture(autouse=True)
def limpiar_motores_prueba(monkeypatch):
    """Cierra los motores SQLite de las aplicaciones creadas en cada test."""

    aplicaciones = []
    crear_app_original = create_app

    def crear_app_registrada(*args, **kwargs):
        app = crear_app_original(*args, **kwargs)
        aplicaciones.append(app)
        return app

    # Todos los tests y auxiliares de este módulo usan este nombre.
    monkeypatch.setattr(
        __name__ + ".create_app",
        crear_app_registrada,
    )

    yield

    for app in aplicaciones:
        for session_factory in app.extensions[
            "contab_databases"
        ].values():
            engine = session_factory.kw["bind"]
            engine.dispose()


def crear_app_test():
    """Crea una aplicación de conciliación aislada."""

    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="test-secret-key",
        bancos={
            "test": "IBERCAJA",
        },
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

    return app


def crear_escenario_aceptacion_individual():
    """Prepara dos propuestas exactas y una con importe distinto."""

    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="test-secret-key",
        bancos={
            "test": "IBERCAJA",
        },
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        )

        previsto_comunidad = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 9, 1),
            fecha_prevista_hasta=date(2026, 9, 5),
            naturaleza="GASTO",
            concepto="Comunidad septiembre",
            importe_esperado=10000,
            contraparte="COMUNIDAD LOCAL",
            estado="PENDIENTE",
        )

        bancario_comunidad = MovimientoBancario(
            fecha=date(2026, 9, 2),
            naturaleza="GASTO",
            importe=10000,
            tipo_original="RECIBO",
            descripcion_original="COMUNIDAD LOCAL",
            referencia_bancaria="",
            huella_importacion="a" * 64,
            estado="PENDIENTE",
        )

        previsto_alquiler = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 9, 1),
            fecha_prevista_hasta=date(2026, 9, 5),
            naturaleza="INGRESO",
            concepto="Alquiler septiembre",
            importe_esperado=85000,
            contraparte="ANA PEREZ",
            estado="PENDIENTE",
        )

        bancario_alquiler = MovimientoBancario(
            fecha=date(2026, 9, 3),
            naturaleza="INGRESO",
            importe=85000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="ANA PEREZ",
            referencia_bancaria="",
            huella_importacion="b" * 64,
            estado="PENDIENTE",
        )

        previsto_diferente = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 9, 1),
            fecha_prevista_hasta=date(2026, 9, 5),
            naturaleza="GASTO",
            concepto="Seguro septiembre",
            importe_esperado=25000,
            contraparte="ASEGURADORA XYZ",
            estado="PENDIENTE",
        )

        bancario_diferente = MovimientoBancario(
            fecha=date(2026, 9, 4),
            naturaleza="GASTO",
            importe=24000,
            tipo_original="RECIBO",
            descripcion_original="ASEGURADORA XYZ",
            referencia_bancaria="",
            huella_importacion="c" * 64,
            estado="PENDIENTE",
        )

        session.add_all([
            inmueble,
            previsto_comunidad,
            bancario_comunidad,
            previsto_alquiler,
            bancario_alquiler,
            previsto_diferente,
            bancario_diferente,
        ])
        session.commit()

        ids = {
            "b_comunidad": bancario_comunidad.id,
            "p_comunidad": previsto_comunidad.id,
            "b_alquiler": bancario_alquiler.id,
            "p_alquiler": previsto_alquiler.id,
            "b_diferente": bancario_diferente.id,
            "p_diferente": previsto_diferente.id,
        }

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    return client, session_factory, ids



def crear_escenario_rechazo_agrupado():
    """Prepara una propuesta 1:2 y otra 1:1 independientes."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-RECHAZO",
            tipo="L",
            codigo_facturacion="LR",
            descripcion="Local de prueba",
            direccion="Calle de prueba",
            poblacion="Madrid",
            provincia="Madrid",
        )

        previsto_agrupado = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 10, 1),
            fecha_prevista_hasta=date(2026, 10, 10),
            naturaleza="INGRESO",
            concepto="Alquiler para rechazo",
            importe_esperado=10000,
            contraparte="PAGADOR RECHAZO",
            estado="PENDIENTE",
        )

        bancario_1 = MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=6000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="PAGADOR RECHAZO 1",
            referencia_bancaria="",
            huella_importacion="rechazo-grupo-1",
            estado="PENDIENTE",
        )

        bancario_2 = MovimientoBancario(
            fecha=date(2026, 10, 6),
            naturaleza="INGRESO",
            importe=4000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="PAGADOR RECHAZO 2",
            referencia_bancaria="",
            huella_importacion="rechazo-grupo-2",
            estado="PENDIENTE",
        )

        # Propuesta independiente, de distinta naturaleza.
        previsto_independiente = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 10, 1),
            fecha_prevista_hasta=date(2026, 10, 10),
            naturaleza="GASTO",
            concepto="Comunidad independiente",
            importe_esperado=3000,
            contraparte="COMUNIDAD INDEPENDIENTE",
            estado="PENDIENTE",
        )

        bancario_independiente = MovimientoBancario(
            fecha=date(2026, 10, 7),
            naturaleza="GASTO",
            importe=3000,
            tipo_original="RECIBO",
            descripcion_original="COMUNIDAD INDEPENDIENTE",
            referencia_bancaria="",
            huella_importacion="rechazo-independiente",
            estado="PENDIENTE",
        )

        session.add_all([
            inmueble,
            previsto_agrupado,
            bancario_1,
            bancario_2,
            previsto_independiente,
            bancario_independiente,
        ])
        session.commit()

        ids = {
            "previsto_agrupado": previsto_agrupado.id,
            "bancario_1": bancario_1.id,
            "bancario_2": bancario_2.id,
            "previsto_independiente": previsto_independiente.id,
            "bancario_independiente": bancario_independiente.id,
        }

    client = app.test_client()
    client.post("/", data={"database": "test"})

    return client, session_factory, ids



def crear_escenario_seleccion_manual(
    previstos_datos,
    bancarios_datos,
):
    """Prepara movimientos para probar la selección manual."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-SELECCION-MANUAL",
            tipo="L",
            codigo_facturacion="LSM",
            descripcion="Local de prueba",
            direccion="Calle de prueba",
            poblacion="Madrid",
            provincia="Madrid",
        )

        previstos = [
            MovimientoPrevisto(
                inmueble=inmueble,
                fecha_prevista_desde=date(2026, 10, 1),
                fecha_prevista_hasta=date(2026, 10, 10),
                naturaleza=naturaleza,
                concepto=f"Previsto manual {indice}",
                importe_esperado=importe,
                contraparte="CONTRAPARTE PRUEBA",
                estado="PENDIENTE",
            )
            for indice, (importe, naturaleza) in enumerate(
                previstos_datos,
                start=1,
            )
        ]

        bancarios = [
            MovimientoBancario(
                fecha=date(2026, 10, 5),
                naturaleza=naturaleza,
                importe=importe,
                tipo_original="TRANSFERENCIA",
                descripcion_original=f"Bancario manual {indice}",
                referencia_bancaria="",
                huella_importacion=f"seleccion-manual-{indice}",
                estado="PENDIENTE",
            )
            for indice, (importe, naturaleza) in enumerate(
                bancarios_datos,
                start=1,
            )
        ]

        session.add_all([
            inmueble,
            *previstos,
            *bancarios,
        ])
        session.commit()

        previsto_ids = [movimiento.id for movimiento in previstos]
        bancario_ids = [movimiento.id for movimiento in bancarios]

    client = app.test_client()
    client.post("/", data={"database": "test"})

    return client, session_factory, previsto_ids, bancario_ids



def crear_escenario_movimientos_parciales():
    """Prepara dos movimientos PARCIAL con 320 € pendientes cada uno."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as db_session:
        inmueble = Inmueble(
            referencia="LOCAL-PARCIAL",
            tipo="L",
            codigo_facturacion="LP",
            descripcion="Local de prueba",
            direccion="Calle de prueba",
            poblacion="Madrid",
            provincia="Madrid",
        )

        previsto_parcial = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 10, 1),
            fecha_prevista_hasta=date(2026, 10, 10),
            naturaleza="INGRESO",
            concepto="Alquiler parcialmente cobrado",
            importe_esperado=92000,
            contraparte="PAGADOR PARCIAL",
            estado="PARCIAL",
        )

        bancario_anterior = MovimientoBancario(
            fecha=date(2026, 10, 2),
            naturaleza="INGRESO",
            importe=60000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="Ingreso anterior",
            referencia_bancaria="",
            huella_importacion="parcial-anterior-bancario",
            estado="CONCILIADO",
        )

        previsto_anterior = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 9, 1),
            fecha_prevista_hasta=date(2026, 9, 10),
            naturaleza="INGRESO",
            concepto="Previsión anterior",
            importe_esperado=18000,
            contraparte="PAGADOR PARCIAL",
            estado="CONCILIADO",
        )

        bancario_parcial = MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=50000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="Transferencia parcialmente aplicada",
            referencia_bancaria="",
            huella_importacion="parcial-actual-bancario",
            estado="PARCIAL",
        )

        # Asociación anterior del previsto: 600 €.
        asociacion_prevista = Conciliacion(
            movimiento_bancario=bancario_anterior,
            movimiento_previsto=previsto_parcial,
            importe_asociado=60000,
        )

        # Asociación anterior del bancario: 180 €.
        asociacion_bancaria = Conciliacion(
            movimiento_bancario=bancario_parcial,
            movimiento_previsto=previsto_anterior,
            importe_asociado=18000,
        )

        db_session.add_all([
            inmueble,
            previsto_parcial,
            bancario_parcial,
            previsto_anterior,
            bancario_anterior,
            asociacion_prevista,
            asociacion_bancaria,
        ])
        db_session.commit()

        ids = {
            "previsto_parcial": previsto_parcial.id,
            "bancario_parcial": bancario_parcial.id,
            "previsto_anterior": previsto_anterior.id,
            "bancario_anterior": bancario_anterior.id,
        }

    client = app.test_client()
    client.post("/", data={"database": "test"})

    return client, session_factory, ids




def test_formulario_importar_movimientos_bancarios() -> None:
    """Muestra el formulario y el banco configurado."""

    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/conciliacion/importar"
    )

    assert response.status_code == 200
    assert "Importar movimientos bancarios" in response.text
    assert "IBERCAJA" in response.text
    assert 'name="archivo"' in response.text
    assert "Conciliación" in response.text


def test_importar_movimientos_bancarios() -> None:
    """Importa el CSV y omite sus movimientos al repetirlo."""

    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    contenido = """Nº Orden;Fecha Oper;Fecha Valor;Concepto;Descripción;Referencia;Importe;Saldo
1;03-09-2026;03-09-2026;TRANSFERENCIA;Alquiler septiembre;123;1.600,00;5.000,00
2;04-09-2026;04-09-2026;RECIBO;Comunidad;;-100,00;4.900,00
"""

    # El usuario importa por primera vez el archivo.
    response = client.post(
        "/conciliacion/importar",
        data={
            "archivo": (
                BytesIO(contenido.encode("utf-8")),
                "movimientos.csv",
            ),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "Movimientos importados: 2" in response.text
    assert "Ya existentes: 0" in response.text

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        movimientos = session.scalars(
            select(MovimientoBancario)
        ).all()

        assert len(movimientos) == 2

    # El usuario vuelve a importar el mismo archivo.
    response = client.post(
        "/conciliacion/importar",
        data={
            "archivo": (
                BytesIO(contenido.encode("utf-8")),
                "movimientos.csv",
            ),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "Movimientos importados: 0" in response.text
    assert "Ya existentes: 2" in response.text

    with session_factory() as session:
        movimientos = session.scalars(
            select(MovimientoBancario)
        ).all()

        assert len(movimientos) == 2


def test_importar_movimientos_exige_archivo() -> None:
    """Vuelve al formulario si no se selecciona un CSV."""

    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        "/conciliacion/importar",
        data={},
    )

    assert response.status_code == 400
    assert "Debe seleccionar un archivo CSV." in response.text
    assert "IBERCAJA" in response.text


def test_importar_movimientos_rechaza_formato_incorrecto() -> None:
    """No guarda movimientos si el archivo no es de Ibercaja."""

    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        "/conciliacion/importar",
        data={
            "archivo": (
                BytesIO(
                    b"cabecera;desconocida\n1;2\n"
                ),
                "movimientos.csv",
            ),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "cabecera esperada" in response.text

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        movimientos = session.scalars(
            select(MovimientoBancario)
        ).all()

        assert movimientos == []


def test_listar_movimientos_bancarios() -> None:
    """Muestra los movimientos del más reciente al más antiguo."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    # Creamos dos movimientos en distinto orden cronológico.
    with session_factory() as session:
        antiguo = MovimientoBancario(
            fecha=date(2026, 8, 31),
            naturaleza="GASTO",
            importe=10000,
            tipo_original="RECIBO",
            descripcion_original="Comunidad agosto",
            referencia_bancaria="",
            huella_importacion="a" * 64,
        )
        reciente = MovimientoBancario(
            fecha=date(2026, 9, 3),
            naturaleza="INGRESO",
            importe=160000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="Alquiler septiembre",
            referencia_bancaria="123",
            huella_importacion="b" * 64,
        )

        session.add_all([
            antiguo,
            reciente,
        ])
        session.commit()

    client = app.test_client()
    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/conciliacion/")

    assert response.status_code == 200
    assert "Movimientos bancarios" in response.text
    assert "Alquiler septiembre" in response.text
    assert "Comunidad agosto" in response.text
    assert "1.600,00" in response.text
    assert "100,00" in response.text
    assert "Pendiente" in response.text

    assert response.text.index(
        "Alquiler septiembre"
    ) < response.text.index(
        "Comunidad agosto"
    )


def test_listar_movimientos_filtra_por_estado() -> None:
    """Filtra los movimientos bancarios por su estado."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        movimientos = [
            MovimientoBancario(
                fecha=date(2026, 9, 3),
                naturaleza="INGRESO",
                importe=10000,
                tipo_original="TRANSFERENCIA",
                descripcion_original="Movimiento pendiente",
                referencia_bancaria="",
                huella_importacion="a" * 64,
                estado="PENDIENTE",
            ),
            MovimientoBancario(
                fecha=date(2026, 9, 2),
                naturaleza="INGRESO",
                importe=20000,
                tipo_original="TRANSFERENCIA",
                descripcion_original="Movimiento conciliado",
                referencia_bancaria="",
                huella_importacion="b" * 64,
                estado="CONCILIADO",
            ),
            MovimientoBancario(
                fecha=date(2026, 9, 1),
                naturaleza="GASTO",
                importe=30000,
                tipo_original="TARJETA",
                descripcion_original="Movimiento descartado",
                referencia_bancaria="",
                huella_importacion="c" * 64,
                estado="DESCARTADO",
            ),
        ]

        session.add_all(movimientos)
        session.commit()

    client = app.test_client()
    client.post(
        "/",
        data={"database": "test"},
    )

    # Por defecto sólo aparecen los pendientes.
    response = client.get("/conciliacion/")

    assert response.status_code == 200
    assert "Movimiento pendiente" in response.text
    assert "Movimiento conciliado" not in response.text
    assert "Movimiento descartado" not in response.text

    # El usuario solicita todos los movimientos.
    response = client.get(
        "/conciliacion/?estado=TODOS"
    )

    assert "Movimiento pendiente" in response.text
    assert "Movimiento conciliado" in response.text
    assert "Movimiento descartado" in response.text

    # El usuario selecciona únicamente los conciliados.
    response = client.get(
        "/conciliacion/?estado=CONCILIADO"
    )

    assert "Movimiento pendiente" not in response.text
    assert "Movimiento conciliado" in response.text
    assert "Movimiento descartado" not in response.text
    assert "Descartar" not in response.text
    assert "Restaurar" not in response.text


def test_descartar_y_restaurar_movimiento_desde_listado() -> None:
    """Descarta un movimiento y permite devolverlo a pendiente."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        movimiento = MovimientoBancario(
            fecha=date(2026, 9, 3),
            naturaleza="GASTO",
            importe=10000,
            tipo_original="TARJETA VISA",
            descripcion_original="Compra particular",
            referencia_bancaria="",
            huella_importacion="a" * 64,
            estado="PENDIENTE",
        )
        session.add(movimiento)
        session.commit()

        movimiento_id = movimiento.id

    client = app.test_client()
    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario descarta el movimiento pendiente.
    response = client.post(
        (
            f"/conciliacion/movimientos/"
            f"{movimiento_id}/descartar"
        ),
        data={"estado": "PENDIENTE"},
    )

    assert response.status_code == 302

    with session_factory() as session:
        movimiento = session.get(
            MovimientoBancario,
            movimiento_id,
        )

        assert movimiento is not None
        assert movimiento.estado == "DESCARTADO"

    # El movimiento descartado ofrece la opción Restaurar.
    response = client.get(
        "/conciliacion/?estado=DESCARTADO"
    )

    assert response.status_code == 200
    assert "Compra particular" in response.text
    assert "Restaurar" in response.text

    # El usuario devuelve el movimiento a Pendiente.
    response = client.post(
        (
            f"/conciliacion/movimientos/"
            f"{movimiento_id}/restaurar"
        ),
        data={"estado": "DESCARTADO"},
    )

    assert response.status_code == 302

    with session_factory() as session:
        movimiento = session.get(
            MovimientoBancario,
            movimiento_id,
        )

        assert movimiento is not None
        assert movimiento.estado == "PENDIENTE"


def test_listar_movimientos_previstos() -> None:
    """Muestra las previsiones pendientes ordenadas por fecha."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        movimiento = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 9, 15),
            fecha_prevista_hasta=date(2026, 9, 20),
            naturaleza="GASTO",
            concepto="Recibo de gas",
            importe_esperado=12537,
            contraparte="Comercializadora",
            estado="PENDIENTE",
        )

        session.add_all([
            inmueble,
            movimiento,
        ])
        session.commit()

    client = app.test_client()
    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/conciliacion/previstos"
    )

    assert response.status_code == 200
    assert "Movimientos previstos" in response.text
    assert "LOCAL-1" in response.text
    assert "15/09/2026 a 20/09/2026" in response.text
    assert "Recibo de gas" in response.text
    assert "Comercializadora" in response.text
    assert "125,37" in response.text
    assert "Pendiente" in response.text
    assert "Previsión independiente" in response.text


def test_cancelar_movimiento_previsto_desde_interfaz() -> None:
    """Cancela desde el listado un movimiento previsto pendiente."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        movimiento = MovimientoPrevisto(
            inmueble=inmueble,
            naturaleza="GASTO",
            concepto="Recibo de comunidad",
            importe_esperado=10000,
            contraparte="Comunidad",
            estado="PENDIENTE",
        )

        session.add_all([
            inmueble,
            movimiento,
        ])
        session.commit()

        movimiento_id = movimiento.id

    client = app.test_client()
    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        (
            f"/conciliacion/previstos/"
            f"{movimiento_id}/cancelar"
        ),
        data={"estado": "PENDIENTE"},
    )

    assert response.status_code == 302

    with session_factory() as session:
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        assert movimiento is not None
        assert movimiento.estado == "CANCELADO"


def test_restaurar_movimiento_previsto_desde_interfaz() -> None:
    """Restaura desde el listado un movimiento previsto cancelado."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        movimiento = MovimientoPrevisto(
            inmueble=inmueble,
            naturaleza="GASTO",
            concepto="Recibo de comunidad",
            importe_esperado=10000,
            contraparte="Comunidad",
            estado="CANCELADO",
        )

        session.add_all([
            inmueble,
            movimiento,
        ])
        session.commit()

        movimiento_id = movimiento.id

    client = app.test_client()
    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario restaura el movimiento cancelado.
    response = client.post(
        (
            f"/conciliacion/previstos/"
            f"{movimiento_id}/restaurar"
        ),
        data={"estado": "CANCELADO"},
    )

    assert response.status_code == 302

    with session_factory() as session:
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        assert movimiento is not None
        assert movimiento.estado == "PENDIENTE"


def test_acciones_movimientos_previstos_segun_estado() -> None:
    """Muestra sólo las acciones permitidas para cada estado."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        movimientos = [
            MovimientoPrevisto(
                inmueble=inmueble,
                naturaleza="GASTO",
                concepto="Movimiento pendiente",
                importe_esperado=10000,
                estado="PENDIENTE",
            ),
            MovimientoPrevisto(
                inmueble=inmueble,
                naturaleza="GASTO",
                concepto="Movimiento cancelado",
                importe_esperado=10000,
                estado="CANCELADO",
            ),
            MovimientoPrevisto(
                inmueble=inmueble,
                naturaleza="GASTO",
                concepto="Movimiento parcial",
                importe_esperado=10000,
                estado="PARCIAL",
            ),
            MovimientoPrevisto(
                inmueble=inmueble,
                naturaleza="GASTO",
                concepto="Movimiento conciliado",
                importe_esperado=10000,
                estado="CONCILIADO",
            ),
        ]

        session.add(inmueble)
        session.add_all(movimientos)
        session.commit()

    client = app.test_client()
    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario muestra movimientos previstos de todos los estados.
    response = client.get(
        "/conciliacion/previstos?estado=TODOS"
    )

    assert response.status_code == 200

    assert response.text.count("Cancelar") == 1
    assert response.text.count("Restaurar") == 1


def test_revisar_conciliacion_clasifica_movimientos() -> None:
    """Muestra propuestas y pendientes sin modificar sus estados."""

    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="test-secret-key",
        bancos={
            "test": "IBERCAJA",
        },
        aliases_conciliacion={
            "test": [
                (
                    "COMUNIDAD",
                    "LOCAL-1",
                    "C.P. LOCAL PRUEBA",
                ),
            ],
        },
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        )

        # Propuesta exacta: comunidad.
        previsto_1 = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 9, 1),
            fecha_prevista_hasta=date(2026, 9, 5),
            naturaleza="GASTO",
            concepto="Comunidad septiembre",
            importe_esperado=10000,
            contraparte="",
            estado="PENDIENTE",
        )

        conciliable_1 = MovimientoBancario(
            fecha=date(2026, 9, 2),
            naturaleza="GASTO",
            importe=10000,
            tipo_original="RECIBO",
            descripcion_original="C.P. LOCAL PRUEBA",
            referencia_bancaria="",
            huella_importacion="a" * 64,
            estado="PENDIENTE",
        )

        # Movimiento sin propuesta.
        pendiente_1 = MovimientoBancario(
            fecha=date(2026, 9, 2),
            naturaleza="GASTO",
            importe=54321,
            tipo_original="RECIBO",
            descripcion_original="MOVIMIENTO DESCONOCIDO",
            referencia_bancaria="",
            huella_importacion="b" * 64,
            estado="PENDIENTE",
        )

        # Propuesta clara, pero con importes diferentes.
        previsto_2 = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 9, 1),
            fecha_prevista_hasta=date(2026, 9, 5),
            naturaleza="INGRESO",
            concepto="Alquiler septiembre Bárbara",
            importe_esperado=152500,
            contraparte="BARBARA BONITA BARCENAS",
            estado="PENDIENTE",
        )

        conciliable_2 = MovimientoBancario(
            fecha=date(2026, 9, 3),
            naturaleza="INGRESO",
            importe=150000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="BARBARA BONITA BARCENAS",
            referencia_bancaria="",
            huella_importacion="c" * 64,
            estado="PENDIENTE",
        )

        session.add_all(
            [
                inmueble,
                previsto_1,
                conciliable_1,
                pendiente_1,
                previsto_2,
                conciliable_2,
            ]
        )
        session.commit()

        conciliable_1_id = conciliable_1.id
        pendiente_1_id = pendiente_1.id
        previsto_1_id = previsto_1.id
        conciliable_2_id = conciliable_2.id
        previsto_2_id = previsto_2.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario abre la revisión automática de conciliación.
    response = client.get(
        "/conciliacion/revisar"
    )

    assert response.status_code == 200
    assert "Revisar conciliación" in response.text

    # La propuesta exacta aparece en la sección normal.
    assert "Propuestas automáticas" in response.text
    assert 'class="revision-propuesta"' in response.text
    assert "Comunidad septiembre" in response.text
    assert "LOCAL-1" in response.text
    assert "100,00" in response.text

    # La propuesta con importe diferente aparece separada.
    assert "Conciliación manual" in response.text
    assert "Alquiler septiembre Bárbara" in response.text
    assert "BARBARA BONITA BARCENAS" in response.text
    assert "1.500,00" in response.text
    assert "1.525,00" in response.text

    # El movimiento que no tiene propuesta sigue pendiente.
    assert "Conciliación manual" in response.text
    assert "MOVIMIENTO DESCONOCIDO" in response.text

    # El usuario puede aceptar y recharzar individualmente la propuesta
    assert "Aceptar" in response.text
    assert "Rechazar" in response.text

    # Una propuesta de importe diferente no ofrece aceptación.
    assert (
        f"/conciliacion/revisar/{conciliable_2_id}/aceptar"
        not in response.text
    )

    # Ya no hay confirmación global ni rechazo por fila.
    assert "Confirmar propuestas" not in response.text
    assert "Dejar pendiente" not in response.text

    # Abrir la revisión no confirma ni descarta nada.
    with session_factory() as session:
        conciliable_1 = session.get(
            MovimientoBancario,
            conciliable_1_id,
        )
        pendiente_1 = session.get(
            MovimientoBancario,
            pendiente_1_id,
        )
        previsto_1 = session.get(
            MovimientoPrevisto,
            previsto_1_id,
        )
        conciliable_2 = session.get(
            MovimientoBancario,
            conciliable_2_id,
        )
        previsto_2 = session.get(
            MovimientoPrevisto,
            previsto_2_id,
        )

        assert conciliable_1 is not None
        assert pendiente_1 is not None
        assert previsto_1 is not None
        assert conciliable_2 is not None
        assert previsto_2 is not None

        assert conciliable_1.estado == "PENDIENTE"
        assert pendiente_1.estado == "PENDIENTE"
        assert previsto_1.estado == "PENDIENTE"
        assert conciliable_2.estado == "PENDIENTE"
        assert previsto_2.estado == "PENDIENTE"


def test_aceptar_una_propuesta_no_confirma_las_demas() -> None:
    """Aceptar una fila sólo concilia la pareja seleccionada."""

    client, session_factory, ids = (
        crear_escenario_aceptacion_individual()
    )

    # El usuario abre la revisión y ve dos propuestas exactas.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200
    assert "Comunidad septiembre" in response.text
    assert "Alquiler septiembre" in response.text

    # El usuario acepta únicamente el recibo de comunidad.
    response = client.post(
        (
            "/conciliacion/revisar/"
            f"{ids['b_comunidad']}/aceptar"
        ),
        data={
            "previsto_id": ids["p_comunidad"],
        },
    )

    assert response.status_code == 302
    assert response.location.endswith(
        "/conciliacion/revisar"
    )

    # La base de datos sólo contiene esa conciliación.
    with session_factory() as session:
        b_comunidad = session.get(
            MovimientoBancario, ids["b_comunidad"]
        )
        p_comunidad = session.get(
            MovimientoPrevisto, ids["p_comunidad"]
        )
        b_alquiler = session.get(
            MovimientoBancario, ids["b_alquiler"]
        )
        p_alquiler = session.get(
            MovimientoPrevisto, ids["p_alquiler"]
        )
        b_diferente = session.get(
            MovimientoBancario, ids["b_diferente"]
        )
        p_diferente = session.get(
            MovimientoPrevisto, ids["p_diferente"]
        )

        conciliaciones = session.scalars(
            select(Conciliacion)
        ).all()

        assert b_comunidad.estado == "CONCILIADO"
        assert p_comunidad.estado == "CONCILIADO"
        assert p_comunidad.metodo_conciliacion == "INDIVIDUAL"

        assert b_alquiler.estado == "PENDIENTE"
        assert p_alquiler.estado == "PENDIENTE"
        assert b_diferente.estado == "PENDIENTE"
        assert p_diferente.estado == "PENDIENTE"

        assert len(conciliaciones) == 1
        assert (
            conciliaciones[0].movimiento_bancario_id
            == ids["b_comunidad"]
        )
        assert (
            conciliaciones[0].movimiento_previsto_id
            == ids["p_comunidad"]
        )
        assert conciliaciones[0].importe_asociado == 10000

    # Al volver a la pantalla, la fila aceptada ha desaparecido.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200
    assert "Comunidad septiembre" not in response.text
    assert "Alquiler septiembre" in response.text
    assert "Seguro septiembre" in response.text


def test_aceptar_segunda_propuesta_individual() -> None:
    """Permite aceptar otra fila en una operación independiente."""

    client, session_factory, ids = (
        crear_escenario_aceptacion_individual()
    )

    # El usuario acepta el recibo de comunidad.
    response = client.post(
        (
            "/conciliacion/revisar/"
            f"{ids['b_comunidad']}/aceptar"
        ),
        data={
            "previsto_id": ids["p_comunidad"],
        },
    )

    assert response.status_code == 302

    # Después acepta también el ingreso del alquiler.
    response = client.post(
        (
            "/conciliacion/revisar/"
            f"{ids['b_alquiler']}/aceptar"
        ),
        data={
            "previsto_id": ids["p_alquiler"],
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        conciliaciones = session.scalars(
            select(Conciliacion)
        ).all()

        parejas = {
            (
                c.movimiento_bancario_id,
                c.movimiento_previsto_id,
            )
            for c in conciliaciones
        }

        assert parejas == {
            (ids["b_comunidad"], ids["p_comunidad"]),
            (ids["b_alquiler"], ids["p_alquiler"]),
        }

        assert session.get(
            MovimientoBancario, ids["b_diferente"]
        ).estado == "PENDIENTE"

        assert session.get(
            MovimientoPrevisto, ids["p_diferente"]
        ).estado == "PENDIENTE"


def test_no_aceptar_propuesta_con_importes_diferentes() -> None:
    """Una discrepancia no puede confirmarse por la ruta normal."""

    client, session_factory, ids = (
        crear_escenario_aceptacion_individual()
    )

    # El usuario intenta aceptar una discrepancia de importe.
    response = client.post(
        (
            "/conciliacion/revisar/"
            f"{ids['b_diferente']}/aceptar"
        ),
        data={
            "previsto_id": ids["p_diferente"],
        },
    )

    assert response.status_code == 400

    # El intento no ha producido ningún cambio.
    with session_factory() as session:
        assert session.get(
            MovimientoBancario, ids["b_diferente"]
        ).estado == "PENDIENTE"

        assert session.get(
            MovimientoPrevisto, ids["p_diferente"]
        ).estado == "PENDIENTE"

        assert session.scalars(
            select(Conciliacion)
        ).all() == []


def test_no_aceptar_pareja_distinta_de_la_propuesta() -> None:
    """El servidor no acepta una asociación manipulada."""

    client, session_factory, ids = (
        crear_escenario_aceptacion_individual()
    )

    # El usuario envía un previsto distinto al de la fila.
    response = client.post(
        (
            "/conciliacion/revisar/"
            f"{ids['b_comunidad']}/aceptar"
        ),
        data={
            "previsto_id": ids["p_alquiler"],
        },
    )

    assert response.status_code == 400

    with session_factory() as session:
        assert session.get(
            MovimientoBancario, ids["b_comunidad"]
        ).estado == "PENDIENTE"

        assert session.get(
            MovimientoPrevisto, ids["p_comunidad"]
        ).estado == "PENDIENTE"

        assert session.scalars(
            select(Conciliacion)
        ).all() == []


def test_no_aceptar_dos_veces_la_misma_propuesta() -> None:
    """Una doble pulsación no crea conciliaciones duplicadas."""

    client, session_factory, ids = (
        crear_escenario_aceptacion_individual()
    )

    url = (
        "/conciliacion/revisar/"
        f"{ids['b_comunidad']}/aceptar"
    )

    datos = {
        "previsto_id": ids["p_comunidad"],
    }

    # Primera aceptación: la conciliación se guarda.
    response = client.post(url, data=datos)

    assert response.status_code == 302

    # Segunda aceptación: la pareja ya no está pendiente.
    response = client.post(url, data=datos)

    assert response.status_code == 400

    with session_factory() as session:
        conciliaciones = session.scalars(
            select(Conciliacion)
        ).all()

        assert len(conciliaciones) == 1

        assert session.get(
            MovimientoBancario, ids["b_comunidad"]
        ).estado == "CONCILIADO"

        assert session.get(
            MovimientoPrevisto, ids["p_comunidad"]
        ).estado == "CONCILIADO"


def test_no_aceptar_propuesta_modificada_desde_revision() -> None:
    """Revalida una propuesta aunque la pantalla sea antigua."""

    client, session_factory, ids = (
        crear_escenario_aceptacion_individual()
    )

    # El usuario abre la revisión con una propuesta válida.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200
    assert "Comunidad septiembre" in response.text

    # Antes de aceptar, cambia el importe del movimiento previsto.
    with session_factory() as session:
        with session.begin():
            previsto = session.get(
                MovimientoPrevisto,
                ids["p_comunidad"],
            )
            previsto.importe_esperado = 11000

    # El usuario intenta aceptar la propuesta antigua.
    response = client.post(
        (
            "/conciliacion/revisar/"
            f"{ids['b_comunidad']}/aceptar"
        ),
        data={
            "previsto_id": ids["p_comunidad"],
        },
    )

    assert response.status_code == 400

    # No se concilia ningún movimiento con datos desactualizados.
    with session_factory() as session:
        assert session.get(
            MovimientoBancario, ids["b_comunidad"]
        ).estado == "PENDIENTE"

        assert session.get(
            MovimientoPrevisto, ids["p_comunidad"]
        ).estado == "PENDIENTE"

        assert session.scalars(
            select(Conciliacion)
        ).all() == []


def test_aceptar_movimiento_bancario_inexistente() -> None:
    """Identificar un movimiento inexistente produce un 404."""

    client, session_factory, ids = (
        crear_escenario_aceptacion_individual()
    )

    # Se solicita la aceptación de un movimiento inexistente.
    response = client.post(
        "/conciliacion/revisar/999999/aceptar",
        data={
            "previsto_id": ids["p_comunidad"],
        },
    )

    assert response.status_code == 404

    with session_factory() as session:
        assert session.scalars(
            select(Conciliacion)
        ).all() == []


def test_conciliar_movimiento_previsto_manualmente_desde_interfaz() -> None:
    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="test-secret-key",
        bancos={
            "test": "IBERCAJA",
        },
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        )

        movimiento = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 9, 5),
            naturaleza="GASTO",
            concepto="IBI",
            importe_esperado=25000,
            estado="PENDIENTE",
        )

        session.add_all(
            [
                inmueble,
                movimiento,
            ]
        )
        session.commit()

        movimiento_id = movimiento.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario confirma manualmente cómo se resolvió el movimiento.
    response = client.post(
        (
            f"/conciliacion/previstos/{movimiento_id}"
            "/conciliar-manualmente"
        ),
        data={
            "notas": (
                "  Incluido en los cargos agrupados "
                "del Ayuntamiento.  "
            ),
        },
    )

    assert response.status_code == 302

    # La resolución manual queda persistida sin asociación bancaria.
    with session_factory() as session:
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        assert movimiento is not None
        assert movimiento.estado == "CONCILIADO"
        assert movimiento.metodo_conciliacion == "MANUAL"
        assert (
            movimiento.notas
            == "Incluido en los cargos agrupados del Ayuntamiento."
        )
        assert movimiento.conciliaciones == []

    # El usuario consulta después los movimientos ya conciliados.
    response = client.get(
        "/conciliacion/previstos?estado=CONCILIADO"
    )

    assert response.status_code == 200
    assert "Conciliado" in response.text
    assert "Manual" in response.text
    assert (
        "Incluido en los cargos agrupados del Ayuntamiento."
        in response.text
    )


def test_formulario_conciliacion_manual_muestra_movimiento() -> None:
    # comprueba que el formulario muestra los datos relevantes y, especialmente,
    # que una nota previa aparece en el textarea para que el usuario pueda
    # conservarla o modificarla.
    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="test-secret-key",
        bancos={
            "test": "IBERCAJA",
        },
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        )

        movimiento = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 9, 5),
            naturaleza="GASTO",
            concepto="IBI",
            importe_esperado=25000,
            estado="PENDIENTE",
            notas="Revisar cargos del Ayuntamiento",
        )

        session.add_all(
            [
                inmueble,
                movimiento,
            ]
        )
        session.commit()

        movimiento_id = movimiento.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario abre el formulario de conciliación manual.
    response = client.get(
        (
            f"/conciliacion/previstos/{movimiento_id}"
            "/conciliar-manualmente"
        )
    )

    assert response.status_code == 200
    assert "Conciliar movimiento manualmente" in response.text
    assert "LOCAL-1" in response.text
    assert "IBI" in response.text
    assert "250,00" in response.text

    # Las notas existentes aparecen para poder conservarlas o editarlas.
    assert "Revisar cargos del Ayuntamiento" in response.text


def test_conciliacion_manual_desde_interfaz_rechaza_notas_vacias() -> None:
    # Aquí interesa comprobar dos cosas: obtenemos un 400 (ha llegado correctamente a
    # Contab, pero los datos enviados no son válidos para realizar la operación) y,
    # sobre todo, que el movimiento sigue intacto en la base de datos.
    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="test-secret-key",
        bancos={
            "test": "IBERCAJA",
        },
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        )

        movimiento = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 9, 5),
            naturaleza="GASTO",
            concepto="IBI",
            importe_esperado=25000,
            estado="PENDIENTE",
        )

        session.add_all(
            [
                inmueble,
                movimiento,
            ]
        )
        session.commit()

        movimiento_id = movimiento.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario intenta confirmar sin explicar la conciliación.
    response = client.post(
        (
            f"/conciliacion/previstos/{movimiento_id}"
            "/conciliar-manualmente"
        ),
        data={
            "notas": "   ",
        },
    )

    assert response.status_code == 400
    assert "requiere una explicación" in response.text

    # El intento fallido no modifica el movimiento.
    with session_factory() as session:
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        assert movimiento is not None
        assert movimiento.estado == "PENDIENTE"
        assert movimiento.metodo_conciliacion is None
        assert movimiento.notas is None


def test_conciliacion_manual_movimiento_inexistente_devuelve_404() -> None:
    # cuando se intenta conciliar con un movimiento inexistente devuelve 404 (Not Found:
    # el recurso solicitado no existe)
    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="test-secret-key",
        bancos={
            "test": "IBERCAJA",
        },
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario intenta abrir un movimiento previsto inexistente.
    response = client.get(
        "/conciliacion/previstos/9999/conciliar-manualmente"
    )

    assert response.status_code == 404
    assert "Movimiento previsto no encontrado" in response.text


def test_deshacer_conciliacion_manual_desde_interfaz() -> None:
    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        )

        movimiento = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 9, 5),
            naturaleza="GASTO",
            concepto="IBI",
            importe_esperado=25000,
            estado="CONCILIADO",
            metodo_conciliacion="MANUAL",
            notas=(
                "Incluido en los cargos agrupados "
                "del Ayuntamiento."
            ),
        )

        session.add_all(
            [
                inmueble,
                movimiento,
            ]
        )
        session.commit()

        movimiento_id = movimiento.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario deshace desde el listado la conciliación manual.
    response = client.post(
        (
            f"/conciliacion/previstos/{movimiento_id}"
            "/deshacer-conciliacion-manual"
        )
    )

    assert response.status_code == 302

    # El movimiento vuelve a quedar disponible para conciliar.
    with session_factory() as session:
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        assert movimiento is not None
        assert movimiento.estado == "PENDIENTE"
        assert movimiento.metodo_conciliacion is None
        assert movimiento.notas is None
        assert movimiento.conciliaciones == []


def test_descartar_pendiente_desde_revision() -> None:
    """Descarta un movimiento y permanece en la revisión."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        bancario_descartable = MovimientoBancario(
            fecha=date(2026, 10, 2),
            naturaleza="GASTO",
            importe=4500,
            tipo_original="TARJETA",
            descripcion_original="Compra particular octubre",
            referencia_bancaria="",
            huella_importacion="a" * 64,
            estado="PENDIENTE",
        )

        bancario_pendiente = MovimientoBancario(
            fecha=date(2026, 10, 3),
            naturaleza="GASTO",
            importe=7800,
            tipo_original="RECIBO",
            descripcion_original="Recibo por investigar",
            referencia_bancaria="",
            huella_importacion="b" * 64,
            estado="PENDIENTE",
        )

        session.add_all([
            bancario_descartable,
            bancario_pendiente,
        ])
        session.commit()

        descartable_id = bancario_descartable.id
        pendiente_id = bancario_pendiente.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario abre Revisar conciliación.
    response = client.get(
        "/conciliacion/revisar"
    )

    assert response.status_code == 200
    assert "Compra particular octubre" in response.text
    assert "Recibo por investigar" in response.text

    # La fila pendiente ofrece Descartar y permite
    # regresar directamente a la revisión.
    assert (
        f"/conciliacion/movimientos/{descartable_id}/descartar"
        in response.text
    )
    assert 'name="origen"' in response.text
    assert 'value="revision"' in response.text
    assert "Descartar" in response.text

    # El usuario descarta el movimiento particular.
    response = client.post(
        (
            f"/conciliacion/movimientos/"
            f"{descartable_id}/descartar"
        ),
        data={
            "origen": "revision",
        },
    )

    assert response.status_code == 302
    assert response.location.endswith(
        "/conciliacion/revisar"
    )

    # Sólo el movimiento seleccionado cambia de estado.
    with session_factory() as session:
        descartado = session.get(
            MovimientoBancario,
            descartable_id,
        )
        pendiente = session.get(
            MovimientoBancario,
            pendiente_id,
        )

        assert descartado is not None
        assert pendiente is not None

        assert descartado.estado == "DESCARTADO"
        assert pendiente.estado == "PENDIENTE"

    # Al volver a la revisión, el descartado desaparece.
    response = client.get(
        "/conciliacion/revisar"
    )

    assert response.status_code == 200
    assert "Compra particular octubre" not in response.text
    assert "Recibo por investigar" in response.text

    # El movimiento sigue conservado y puede restaurarse.
    response = client.get(
        "/conciliacion/?estado=DESCARTADO"
    )

    assert response.status_code == 200
    assert "Compra particular octubre" in response.text
    assert "Restaurar" in response.text


def test_no_descartar_conciliado_desde_revision() -> None:
    """No permite descartar un movimiento ya conciliado."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        movimiento = MovimientoBancario(
            fecha=date(2026, 10, 2),
            naturaleza="INGRESO",
            importe=85000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="Alquiler ya conciliado",
            referencia_bancaria="",
            huella_importacion="c" * 64,
            estado="CONCILIADO",
        )

        session.add(movimiento)
        session.commit()

        movimiento_id = movimiento.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # Se intenta descartar un movimiento ya conciliado.
    response = client.post(
        (
            f"/conciliacion/movimientos/"
            f"{movimiento_id}/descartar"
        ),
        data={
            "origen": "revision",
        },
    )

    assert response.status_code == 400

    # La petición incorrecta no modifica la conciliación.
    with session_factory() as session:
        movimiento = session.get(
            MovimientoBancario,
            movimiento_id,
        )

        assert movimiento is not None
        assert movimiento.estado == "CONCILIADO"


def test_descartar_inexistente_desde_revision() -> None:
    """Un movimiento bancario inexistente produce un 404."""

    app = crear_app_test()

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario solicita descartar un movimiento inexistente.
    response = client.post(
        "/conciliacion/movimientos/999999/descartar",
        data={
            "origen": "revision",
        },
    )

    assert response.status_code == 404


def test_deshacer_asociacion_bancaria_desde_interfaz() -> None:
    """El usuario deshace una conciliación bancaria individual."""

    app = crear_app_test()
    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        )

        previsto = MovimientoPrevisto(
            inmueble=inmueble,
            naturaleza="INGRESO",
            concepto="Alquiler octubre",
            importe_esperado=100000,
            estado="CONCILIADO",
            metodo_conciliacion="INDIVIDUAL",
        )

        bancario = MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=100000,
            tipo_original="TRANSFERENCIA",
            huella_importacion="ruta-deshacer-individual",
            estado="CONCILIADO",
        )

        conciliacion = Conciliacion(
            movimiento_bancario=bancario,
            movimiento_previsto=previsto,
            importe_asociado=100000,
        )

        session.add(conciliacion)
        session.commit()

        previsto_id = previsto.id
        bancario_id = bancario.id
        conciliacion_id = conciliacion.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    url = (
        f"/conciliacion/previstos/{previsto_id}"
        f"/asociaciones/{conciliacion_id}/deshacer"
    )

    # El usuario encuentra la acción en el listado de conciliados.
    listado = client.get(
        "/conciliacion/previstos?estado=CONCILIADO"
    )

    assert listado.status_code == 200
    assert f'action="{url}"' in listado.text

    # El usuario deshace la asociación bancaria.
    response = client.post(url)

    assert response.status_code == 302

    with session_factory() as session:
        assert session.get(Conciliacion, conciliacion_id) is None

        previsto = session.get(MovimientoPrevisto, previsto_id)
        bancario = session.get(MovimientoBancario, bancario_id)

        assert previsto.estado == "PENDIENTE"
        assert previsto.metodo_conciliacion is None
        assert bancario.estado == "PENDIENTE"


def test_deshacer_asociacion_bancaria_conserva_las_otras() -> None:
    """Deshace una transferencia sin perder las demás asociaciones."""

    app = crear_app_test()
    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        )

        previsto = MovimientoPrevisto(
            inmueble=inmueble,
            naturaleza="INGRESO",
            concepto="Alquiler octubre",
            importe_esperado=100000,
            estado="CONCILIADO",
            metodo_conciliacion="INDIVIDUAL",
        )

        primero = MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=60000,
            tipo_original="TRANSFERENCIA",
            huella_importacion="ruta-deshacer-grupo-1",
            estado="CONCILIADO",
        )

        segundo = MovimientoBancario(
            fecha=date(2026, 10, 7),
            naturaleza="INGRESO",
            importe=40000,
            tipo_original="TRANSFERENCIA",
            huella_importacion="ruta-deshacer-grupo-2",
            estado="CONCILIADO",
        )

        primera_asociacion = Conciliacion(
            movimiento_bancario=primero,
            movimiento_previsto=previsto,
            importe_asociado=60000,
        )

        segunda_asociacion = Conciliacion(
            movimiento_bancario=segundo,
            movimiento_previsto=previsto,
            importe_asociado=40000,
        )

        session.add_all([
            primera_asociacion,
            segunda_asociacion,
        ])
        session.commit()

        previsto_id = previsto.id
        primero_id = primero.id
        segundo_id = segundo.id
        primera_id = primera_asociacion.id
        segunda_id = segunda_asociacion.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    url_primera = (
        f"/conciliacion/previstos/{previsto_id}"
        f"/asociaciones/{primera_id}/deshacer"
    )
    url_segunda = (
        f"/conciliacion/previstos/{previsto_id}"
        f"/asociaciones/{segunda_id}/deshacer"
    )

    # Cada transferencia debe tener su propia acción.
    listado = client.get(
        "/conciliacion/previstos?estado=CONCILIADO"
    )

    assert listado.status_code == 200
    assert f'action="{url_primera}"' in listado.text
    assert f'action="{url_segunda}"' in listado.text

    # El usuario retira únicamente la segunda transferencia.
    response = client.post(url_segunda)

    assert response.status_code == 302

    with session_factory() as session:
        assert session.get(Conciliacion, primera_id) is not None
        assert session.get(Conciliacion, segunda_id) is None

        previsto = session.get(MovimientoPrevisto, previsto_id)
        primero = session.get(MovimientoBancario, primero_id)
        segundo = session.get(MovimientoBancario, segundo_id)

        assert previsto.estado == "PARCIAL"
        assert previsto.metodo_conciliacion == "INDIVIDUAL"
        assert primero.estado == "CONCILIADO"
        assert segundo.estado == "PENDIENTE"


def test_deshacer_asociacion_bancaria_inexistente_devuelve_404() -> None:
    """No permite deshacer una asociación inexistente."""

    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    response = client.post(
        "/conciliacion/previstos/999999"
        "/asociaciones/999999/deshacer"
    )

    assert response.status_code == 404


def test_deshacer_asociacion_bancaria_rechaza_previsto_ajeno() -> None:
    """La asociación debe pertenecer al previsto indicado en la URL."""

    app = crear_app_test()
    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        )

        previsto = MovimientoPrevisto(
            inmueble=inmueble,
            naturaleza="INGRESO",
            concepto="Alquiler octubre",
            importe_esperado=100000,
            estado="CONCILIADO",
            metodo_conciliacion="INDIVIDUAL",
        )

        otro_previsto = MovimientoPrevisto(
            inmueble=inmueble,
            naturaleza="INGRESO",
            concepto="Alquiler noviembre",
            importe_esperado=100000,
            estado="PENDIENTE",
        )

        bancario = MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=100000,
            tipo_original="TRANSFERENCIA",
            huella_importacion="ruta-deshacer-ajeno",
            estado="CONCILIADO",
        )

        conciliacion = Conciliacion(
            movimiento_bancario=bancario,
            movimiento_previsto=previsto,
            importe_asociado=100000,
        )

        session.add_all([conciliacion, otro_previsto])
        session.commit()

        conciliacion_id = conciliacion.id
        otro_previsto_id = otro_previsto.id
        previsto_id = previsto.id
        bancario_id = bancario.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # Se intenta deshacer la asociación usando otro previsto.
    response = client.post(
        f"/conciliacion/previstos/{otro_previsto_id}"
        f"/asociaciones/{conciliacion_id}/deshacer"
    )

    assert response.status_code == 404

    with session_factory() as session:
        assert session.get(Conciliacion, conciliacion_id) is not None

        previsto = session.get(MovimientoPrevisto, previsto_id)
        bancario = session.get(MovimientoBancario, bancario_id)

        assert previsto.estado == "CONCILIADO"
        assert bancario.estado == "CONCILIADO"


@pytest.mark.parametrize(
    ("numero_previstos", "numero_bancarios"),
    [
        (1, 1),
        (1, 2),
        (1, 3),
        (2, 1),
        (3, 1),
    ],
)
def test_revisar_conciliacion_presenta_propuestas_agrupadas(
    monkeypatch,
    numero_previstos,
    numero_bancarios,
) -> None:
    """Representa cada propuesta en las filas necesarias."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-GRUPOS",
            tipo="L",
            codigo_facturacion="LG",
            descripcion="Local de prueba",
            direccion="Calle de prueba",
            poblacion="Madrid",
            provincia="Madrid",
        )

        previstos = [
            MovimientoPrevisto(
                inmueble=inmueble,
                naturaleza="INGRESO",
                concepto=f"Previsto grupo {indice}",
                importe_esperado=10000,
                estado="PENDIENTE",
            )
            for indice in range(1, numero_previstos + 1)
        ]

        importe_bancario = (
            10000 * numero_previstos
            // numero_bancarios
        )

        bancarios = [
            MovimientoBancario(
                fecha=date(2026, 10, 5),
                naturaleza="INGRESO",
                importe=importe_bancario,
                tipo_original="TRANSFERENCIA",
                descripcion_original=f"Banco grupo {indice}",
                referencia_bancaria="",
                huella_importacion=f"pantalla-grupo-{indice}",
                estado="PENDIENTE",
            )
            for indice in range(1, numero_bancarios + 1)
        ]

        session.add_all([
            inmueble,
            *previstos,
            *bancarios,
        ])
        session.commit()

    def propuestas_simuladas(
        movimientos_bancarios,
        movimientos_previstos,
        aliases_configurados=None,
    ):
        return [
            PropuestaConciliacion(
                bancarios=movimientos_bancarios,
                previstos=movimientos_previstos,
                puntuacion=150,
                motivos=["Grupo de prueba"],
            )
        ]

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        propuestas_simuladas,
    )

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    assert "Previsto grupo 1" in response.text
    assert "Banco grupo 1" in response.text
    assert 'class="revision-propuesta"' in response.text

    # Cada propuesta debe tener su propio tbody.
    grupos = re.findall(
        r'<tbody\b[^>]*class="[^"]*\brevision-propuesta\b[^"]*"'
        r'[^>]*>(.*?)</tbody>',
        response.text,
        flags=re.DOTALL,
    )

    assert len(grupos) == 1

    grupo = grupos[0]

    filas = re.findall(
        r"<tr\b[^>]*>.*?</tr>",
        grupo,
        flags=re.DOTALL,
    )

    assert len(filas) == max(
        numero_previstos,
        numero_bancarios,
    )

    # Todos los movimientos aparecen una sola vez.
    for indice in range(1, numero_previstos + 1):
        assert response.text.count(
            f"Previsto grupo {indice}"
        ) == 1

    for indice in range(1, numero_bancarios + 1):
        assert response.text.count(
            f"Banco grupo {indice}"
        ) == 1

    # Las acciones pertenecen al grupo, no a cada fila.
    assert len(re.findall(
        r'<button\b[^>]*\brevision-propuesta__boton--aceptar\b[^>]*>',
        grupo,
    )) == 1

    assert len(re.findall(
        r'<button\b[^>]*\brevision-propuesta__boton--rechazar\b[^>]*>',
        grupo,
    )) == 1

    # Debe existir separación entre ambos bloques.
    assert "revision-celda--bancario-inicio" in grupo


@pytest.mark.parametrize(
    ("importes_previstos", "importes_bancarios"),
    [
        ([10000], [10000]),
        ([10000], [6000, 4000]),
        ([6000, 4000], [10000]),
    ],
    ids=["1-a-1", "1-a-2", "2-a-1"],
)
def test_aceptar_propuesta_agrupada_desde_revision(
    importes_previstos,
    importes_bancarios,
) -> None:
    """Acepta una propuesta completa y conserva las demás."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-AGRUPADO",
            tipo="L",
            codigo_facturacion="LA",
            descripcion="Local de prueba",
            direccion="Calle de prueba",
            poblacion="Madrid",
            provincia="Madrid",
        )

        previstos = [
            MovimientoPrevisto(
                inmueble=inmueble,
                fecha_prevista_desde=date(2026, 10, 1),
                fecha_prevista_hasta=date(2026, 10, 10),
                naturaleza="INGRESO",
                concepto=f"Concepto agrupado {indice}",
                importe_esperado=importe,
                contraparte="PAGADOR AGRUPADO",
                estado="PENDIENTE",
            )
            for indice, importe in enumerate(
                importes_previstos,
                start=1,
            )
        ]

        bancarios = [
            MovimientoBancario(
                fecha=date(2026, 10, 5),
                naturaleza="INGRESO",
                importe=importe,
                tipo_original="TRANSFERENCIA",
                descripcion_original="PAGADOR AGRUPADO",
                referencia_bancaria="",
                huella_importacion=f"grupo-aceptar-{indice}",
                estado="PENDIENTE",
            )
            for indice, importe in enumerate(
                importes_bancarios,
                start=1,
            )
        ]

        # Otra propuesta independiente que no debe modificarse.
        previsto_independiente = MovimientoPrevisto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 10, 1),
            fecha_prevista_hasta=date(2026, 10, 10),
            naturaleza="GASTO",
            concepto="Gasto independiente",
            importe_esperado=3000,
            contraparte="PROVEEDOR INDEPENDIENTE",
            estado="PENDIENTE",
        )

        bancario_independiente = MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="GASTO",
            importe=3000,
            tipo_original="RECIBO",
            descripcion_original="PROVEEDOR INDEPENDIENTE",
            referencia_bancaria="",
            huella_importacion="grupo-aceptar-independiente",
            estado="PENDIENTE",
        )

        session.add_all([
            inmueble,
            *previstos,
            *bancarios,
            previsto_independiente,
            bancario_independiente,
        ])
        session.commit()

        previstos_ids = [p.id for p in previstos]
        bancarios_ids = [b.id for b in bancarios]
        previsto_independiente_id = previsto_independiente.id
        bancario_independiente_id = bancario_independiente.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # El formulario debe identificar todos los movimientos.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    # Confirmamos únicamente el grupo seleccionado.
    response = client.post(
        "/conciliacion/revisar/propuestas/aceptar",
        data={
            "bancario_ids": [
                str(id_) for id_ in bancarios_ids
            ],
            "previsto_ids": [
                str(id_) for id_ in previstos_ids
            ],
        },
    )

    assert response.status_code == 302
    assert response.location.endswith(
        "/conciliacion/revisar"
    )

    with session_factory() as session:
        asociaciones = session.scalars(
            select(Conciliacion)
        ).all()

        assert len(asociaciones) == max(
            len(previstos_ids),
            len(bancarios_ids),
        )

        assert {
            asociacion.movimiento_bancario_id
            for asociacion in asociaciones
        } == set(bancarios_ids)

        assert {
            asociacion.movimiento_previsto_id
            for asociacion in asociaciones
        } == set(previstos_ids)

        assert sum(
            asociacion.importe_asociado
            for asociacion in asociaciones
        ) == 10000

        for previsto_id in previstos_ids:
            previsto = session.get(
                MovimientoPrevisto,
                previsto_id,
            )
            assert previsto.estado == "CONCILIADO"

        for bancario_id in bancarios_ids:
            bancario = session.get(
                MovimientoBancario,
                bancario_id,
            )
            assert bancario.estado == "CONCILIADO"

        previsto_independiente = session.get(
            MovimientoPrevisto,
            previsto_independiente_id,
        )
        bancario_independiente = session.get(
            MovimientoBancario,
            bancario_independiente_id,
        )

        assert previsto_independiente.estado == "PENDIENTE"
        assert bancario_independiente.estado == "PENDIENTE"

    # La propuesta aceptada desaparece de la revisión.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200
    assert "Concepto agrupado 1" not in response.text
    assert "PAGADOR AGRUPADO" not in response.text
    assert "Gasto independiente" in response.text


def test_rechazar_propuesta_agrupada_libera_movimientos() -> None:
    """Traslada una propuesta 1:2 a manual sin conciliarla."""

    client, session_factory, ids = (
        crear_escenario_rechazo_agrupado()
    )

    response = client.post(
        "/conciliacion/revisar/propuestas/rechazar",
        data={
            "bancario_ids": [
                str(ids["bancario_1"]),
                str(ids["bancario_2"]),
            ],
            "previsto_ids": [
                str(ids["previsto_agrupado"]),
            ],
        },
    )

    assert response.status_code == 302
    assert response.location.endswith(
        "/conciliacion/revisar"
    )

    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    # Ningún movimiento rechazado permanece entre propuestas.
    grupos = re.findall(
        r'<tbody\b[^>]*class="[^"]*\brevision-propuesta\b[^"]*"'
        r'[^>]*>(.*?)</tbody>',
        response.text,
        flags=re.DOTALL,
    )

    assert all(
        "Alquiler para rechazo" not in grupo
        and "PAGADOR RECHAZO 1" not in grupo
        and "PAGADOR RECHAZO 2" not in grupo
        for grupo in grupos
    )

    # Los tres movimientos aparecen una sola vez, en manual.
    for texto in (
        "Alquiler para rechazo",
        "PAGADOR RECHAZO 1",
        "PAGADOR RECHAZO 2",
    ):
        assert response.text.count(texto) == 1

    manual = response.text.split(
        'class="revision__seccion revision__seccion--manual"',
        1,
    )[1]

    assert "Alquiler para rechazo" in manual
    assert "PAGADOR RECHAZO 1" in manual
    assert "PAGADOR RECHAZO 2" in manual

    # El rechazo no crea asociaciones ni cambia estados.
    with session_factory() as session:
        assert session.scalars(
            select(Conciliacion)
        ).all() == []

        for modelo, identificador in (
            (MovimientoPrevisto, ids["previsto_agrupado"]),
            (MovimientoBancario, ids["bancario_1"]),
            (MovimientoBancario, ids["bancario_2"]),
        ):
            movimiento = session.get(modelo, identificador)
            assert movimiento.estado == "PENDIENTE"


def test_rechazo_propuesta_persiste_en_sesion() -> None:
    """Conserva los movimientos liberados al recargar."""

    client, _, ids = crear_escenario_rechazo_agrupado()

    response = client.post(
        "/conciliacion/revisar/propuestas/rechazar",
        data={
            "bancario_ids": [
                str(ids["bancario_1"]),
                str(ids["bancario_2"]),
            ],
            "previsto_ids": [
                str(ids["previsto_agrupado"]),
            ],
        },
    )

    assert response.status_code == 302

    for _ in range(2):
        response = client.get("/conciliacion/revisar")

        assert response.status_code == 200

        manual = response.text.split(
            'class="revision__seccion revision__seccion--manual"',
            1,
        )[1]

        assert "Alquiler para rechazo" in manual
        assert "PAGADOR RECHAZO 1" in manual
        assert "PAGADOR RECHAZO 2" in manual

        propuestas_html = response.text.split(
            'class="revision__seccion revision__seccion--manual"',
            1,
        )[0]

        assert "Alquiler para rechazo" not in propuestas_html
        assert "PAGADOR RECHAZO 1" not in propuestas_html
        assert "PAGADOR RECHAZO 2" not in propuestas_html


def test_rechazar_propuesta_no_impide_aceptar_otra() -> None:
    """Mantiene operativa una propuesta independiente."""

    client, session_factory, ids = (
        crear_escenario_rechazo_agrupado()
    )

    response = client.post(
        "/conciliacion/revisar/propuestas/rechazar",
        data={
            "bancario_ids": [
                str(ids["bancario_1"]),
                str(ids["bancario_2"]),
            ],
            "previsto_ids": [
                str(ids["previsto_agrupado"]),
            ],
        },
    )

    assert response.status_code == 302

    response = client.post(
        "/conciliacion/revisar/propuestas/aceptar",
        data={
            "bancario_ids": [
                str(ids["bancario_independiente"]),
            ],
            "previsto_ids": [
                str(ids["previsto_independiente"]),
            ],
        },
    )

    assert response.status_code == 302
    assert response.location.endswith(
        "/conciliacion/revisar"
    )

    with session_factory() as session:
        asociaciones = session.scalars(
            select(Conciliacion)
        ).all()

        assert len(asociaciones) == 1

        assert (
            asociaciones[0].movimiento_bancario_id
            == ids["bancario_independiente"]
        )
        assert (
            asociaciones[0].movimiento_previsto_id
            == ids["previsto_independiente"]
        )

        assert session.get(
            MovimientoPrevisto,
            ids["previsto_independiente"],
        ).estado == "CONCILIADO"

        assert session.get(
            MovimientoBancario,
            ids["bancario_independiente"],
        ).estado == "CONCILIADO"

        # Los movimientos rechazados continúan pendientes.
        assert session.get(
            MovimientoPrevisto,
            ids["previsto_agrupado"],
        ).estado == "PENDIENTE"

        assert session.get(
            MovimientoBancario,
            ids["bancario_1"],
        ).estado == "PENDIENTE"

        assert session.get(
            MovimientoBancario,
            ids["bancario_2"],
        ).estado == "PENDIENTE"

    # Los rechazados siguen en manual tras la aceptación.
    response = client.get("/conciliacion/revisar")

    manual = response.text.split(
        'class="revision__seccion revision__seccion--manual"',
        1,
    )[1]

    assert "Alquiler para rechazo" in manual
    assert "PAGADOR RECHAZO 1" in manual
    assert "PAGADOR RECHAZO 2" in manual

    # La propuesta independiente ya no está pendiente.
    assert "Comunidad independiente" not in response.text


def test_revision_manual_muestra_casillas_y_totales() -> None:
    """Permite seleccionar movimientos de ambos lados."""

    client, _, ids = crear_escenario_rechazo_agrupado()

    # Liberamos la propuesta 1:2 para poder seleccionarla
    # en la zona de conciliación manual.
    response = client.post(
        "/conciliacion/revisar/propuestas/rechazar",
        data={
            "bancario_ids": [
                str(ids["bancario_1"]),
                str(ids["bancario_2"]),
            ],
            "previsto_ids": [
                str(ids["previsto_agrupado"]),
            ],
        },
    )

    assert response.status_code == 302

    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    manual = response.text.split(
        'class="revision__seccion revision__seccion--manual"',
        1,
    )[1]

    # Los movimientos previstos y bancarios se seleccionan
    # mediante casillas independientes.
    assert 'name="previsto_ids"' in manual
    assert 'name="bancario_ids"' in manual

    assert (
        f'value="{ids["previsto_agrupado"]}"'
        in manual
    )
    assert (
        f'value="{ids["bancario_1"]}"'
        in manual
    )
    assert (
        f'value="{ids["bancario_2"]}"'
        in manual
    )

    assert 'id="revision-manual-formulario-ingresos"' in manual
    assert 'id="revision-manual-formulario-gastos"' in manual

    assert manual.count(
        'class="revision-manual__formulario"'
    ) == 2

    assert manual.count(
        "revision-manual__total-previstos"
    ) == 2

    assert manual.count(
        "revision-manual__total-bancarios"
    ) == 2

    assert manual.count(
        "revision-manual__diferencia"
    ) == 2


def test_revision_manual_no_preselecciona_movimientos_rechazados() -> None:
    """Rechazar una propuesta no selecciona sus movimientos."""

    client, _, ids = crear_escenario_rechazo_agrupado()

    response = client.post(
        "/conciliacion/revisar/propuestas/rechazar",
        data={
            "bancario_ids": [
                str(ids["bancario_1"]),
                str(ids["bancario_2"]),
            ],
            "previsto_ids": [
                str(ids["previsto_agrupado"]),
            ],
        },
    )

    assert response.status_code == 302

    response = client.get("/conciliacion/revisar")

    manual = response.text.split(
        'class="revision__seccion revision__seccion--manual"',
        1,
    )[1]

    casillas = re.findall(
        r'<input\b[^>]*type="checkbox"[^>]*>',
        manual,
        flags=re.DOTALL,
    )

    assert len(casillas) == 3

    assert all(
        "checked" not in casilla
        for casilla in casillas
    )


def test_confirmar_seleccion_manual_uno_a_dos() -> None:
    """Concilia manualmente un previsto con dos bancarios."""

    client, session_factory, ids = (
        crear_escenario_rechazo_agrupado()
    )

    # El usuario rechaza la sugerencia automática.
    response = client.post(
        "/conciliacion/revisar/propuestas/rechazar",
        data={
            "bancario_ids": [
                str(ids["bancario_1"]),
                str(ids["bancario_2"]),
            ],
            "previsto_ids": [
                str(ids["previsto_agrupado"]),
            ],
        },
    )

    assert response.status_code == 302

    # Selecciona expresamente los mismos movimientos
    # para confirmar una conciliación manual.
    response = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data={
            "bancario_ids": [
                str(ids["bancario_1"]),
                str(ids["bancario_2"]),
            ],
            "previsto_ids": [
                str(ids["previsto_agrupado"]),
            ],
        },
    )

    assert response.status_code == 302
    assert response.location.endswith(
        "/conciliacion/revisar"
    )

    with session_factory() as session:
        asociaciones = session.scalars(
            select(Conciliacion)
        ).all()

        assert len(asociaciones) == 2

        assert {
            asociacion.movimiento_bancario_id
            for asociacion in asociaciones
        } == {
            ids["bancario_1"],
            ids["bancario_2"],
        }

        assert {
            asociacion.movimiento_previsto_id
            for asociacion in asociaciones
        } == {
            ids["previsto_agrupado"],
        }

        assert sum(
            asociacion.importe_asociado
            for asociacion in asociaciones
        ) == 10000

        assert session.get(
            MovimientoPrevisto,
            ids["previsto_agrupado"],
        ).estado == "CONCILIADO"

        assert session.get(
            MovimientoBancario,
            ids["bancario_1"],
        ).estado == "CONCILIADO"

        assert session.get(
            MovimientoBancario,
            ids["bancario_2"],
        ).estado == "CONCILIADO"

        # La propuesta independiente sigue pendiente.
        assert session.get(
            MovimientoPrevisto,
            ids["previsto_independiente"],
        ).estado == "PENDIENTE"

        assert session.get(
            MovimientoBancario,
            ids["bancario_independiente"],
        ).estado == "PENDIENTE"

    # Los movimientos ya conciliados desaparecen
    # de ambas secciones de la revisión.
    response = client.get("/conciliacion/revisar")

    assert "Alquiler para rechazo" not in response.text
    assert "PAGADOR RECHAZO 1" not in response.text
    assert "PAGADOR RECHAZO 2" not in response.text

    assert "Comunidad independiente" in response.text


@pytest.mark.parametrize(
    ("importes_previstos", "importes_bancarios"),
    [
        ([10000], [10000]),
        ([6000, 4000], [10000]),
        ([10000], [5000, 3000, 2000]),
        ([5000, 3000, 2000], [10000]),
    ],
    ids=["1-a-1", "2-a-1", "1-a-3", "3-a-1"],
)
def test_confirmar_seleccion_manual_cardinalidades(
    monkeypatch,
    importes_previstos,
    importes_bancarios,
) -> None:
    """Confirma agrupaciones manuales sin propuesta automática."""

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-MANUAL",
            tipo="L",
            codigo_facturacion="LM",
            descripcion="Local de prueba",
            direccion="Calle de prueba",
            poblacion="Madrid",
            provincia="Madrid",
        )

        previstos = [
            MovimientoPrevisto(
                inmueble=inmueble,
                fecha_prevista_desde=date(2026, 1, 1),
                fecha_prevista_hasta=date(2026, 1, 5),
                naturaleza="INGRESO",
                concepto=f"Previsto manual {indice}",
                importe_esperado=importe,
                contraparte="PAGADOR MANUAL",
                estado="PENDIENTE",
            )
            for indice, importe in enumerate(
                importes_previstos,
                start=1,
            )
        ]

        bancarios = [
            MovimientoBancario(
                fecha=date(2026, 10, 5),
                naturaleza="INGRESO",
                importe=importe,
                tipo_original="TRANSFERENCIA",
                descripcion_original=f"Banco manual {indice}",
                referencia_bancaria="",
                huella_importacion=f"manual-cardinalidad-{indice}",
                estado="PENDIENTE",
            )
            for indice, importe in enumerate(
                importes_bancarios,
                start=1,
            )
        ]

        session.add_all([
            inmueble,
            *previstos,
            *bancarios,
        ])
        session.commit()

        previsto_ids = [p.id for p in previstos]
        bancario_ids = [b.id for b in bancarios]

    client = app.test_client()
    client.post("/", data={"database": "test"})

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    # No debe haber propuestas automáticas: las fechas
    # son deliberadamente incompatibles.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200
    assert "No hay propuestas automáticas" in response.text

    # Todos los movimientos están disponibles en manual.
    for indice in range(1, len(previsto_ids) + 1):
        assert f"Previsto manual {indice}" in response.text

    for indice in range(1, len(bancario_ids) + 1):
        assert f"Banco manual {indice}" in response.text

    response = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data={
            "previsto_ids": [
                str(identificador)
                for identificador in previsto_ids
            ],
            "bancario_ids": [
                str(identificador)
                for identificador in bancario_ids
            ],
        },
    )

    assert response.status_code == 302
    assert response.location.endswith(
        "/conciliacion/revisar"
    )

    with session_factory() as session:
        asociaciones = session.scalars(
            select(Conciliacion)
        ).all()

        assert len(asociaciones) == max(
            len(previsto_ids),
            len(bancario_ids),
        )

        assert {
            asociacion.movimiento_previsto_id
            for asociacion in asociaciones
        } == set(previsto_ids)

        assert {
            asociacion.movimiento_bancario_id
            for asociacion in asociaciones
        } == set(bancario_ids)

        assert sum(
            asociacion.importe_asociado
            for asociacion in asociaciones
        ) == 10000

        for identificador in previsto_ids:
            assert session.get(
                MovimientoPrevisto,
                identificador,
            ).estado == "CONCILIADO"

        for identificador in bancario_ids:
            assert session.get(
                MovimientoBancario,
                identificador,
            ).estado == "CONCILIADO"

    # Los movimientos conciliados desaparecen de la revisión.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    for indice in range(1, len(previsto_ids) + 1):
        assert f"Previsto manual {indice}" not in response.text

    for indice in range(1, len(bancario_ids) + 1):
        assert f"Banco manual {indice}" not in response.text


@pytest.mark.parametrize(
    ("previstos_datos", "bancarios_datos", "mensaje_esperado"),
    [
        (
            [(6000, "INGRESO"), (4000, "INGRESO")],
            [(7000, "INGRESO"), (3000, "INGRESO")],
            "m:n",
        ),
        (
            [(10000, "INGRESO")],
            [(9900, "INGRESO")],
            "saldos pendientes",
        ),
        (
            [(10000, "INGRESO")],
            [(10000, "GASTO")],
            "naturaleza",
        ),
    ],
    ids=[
        "muchos-a-muchos",
        "importes-diferentes",
        "naturalezas-distintas",
    ],
)
def test_confirmar_seleccion_manual_rechaza_incompatibles(
    monkeypatch,
    previstos_datos,
    bancarios_datos,
    mensaje_esperado,
) -> None:
    """Rechaza selecciones incompatibles sin modificar los movimientos."""

    (
        client,
        session_factory,
        previsto_ids,
        bancario_ids,
    ) = crear_escenario_seleccion_manual(
        previstos_datos,
        bancarios_datos,
    )

    # En este test todos los movimientos están disponibles
    # para selección manual.
    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    response = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data={
            "previsto_ids": [
                str(identificador)
                for identificador in previsto_ids
            ],
            "bancario_ids": [
                str(identificador)
                for identificador in bancario_ids
            ],
        },
    )

    assert response.status_code == 400
    assert mensaje_esperado.lower() in response.text.lower()

    with session_factory() as session:
        # Ninguna conciliación debe haberse guardado.
        asociaciones = session.scalars(
            select(Conciliacion)
        ).all()

        assert asociaciones == []

        # Todos los movimientos conservan sus estados.
        for identificador in previsto_ids:
            movimiento = session.get(
                MovimientoPrevisto,
                identificador,
            )

            assert movimiento is not None
            assert movimiento.estado == "PENDIENTE"

        for identificador in bancario_ids:
            movimiento = session.get(
                MovimientoBancario,
                identificador,
            )

            assert movimiento is not None
            assert movimiento.estado == "PENDIENTE"


def test_manual_rechaza_movimiento_reservado_en_propuesta() -> None:
    """No permite conciliar manualmente una propuesta no rechazada."""

    client, session_factory, ids = (
        crear_escenario_rechazo_agrupado()
    )

    # La propuesta independiente 1:1 sigue en la sección automática.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    propuestas_html = response.text.split(
        'class="revision__seccion revision__seccion--manual"',
        1,
    )[0]

    assert "Comunidad independiente" in propuestas_html

    response = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data={
            "previsto_ids": [
                str(ids["previsto_independiente"]),
            ],
            "bancario_ids": [
                str(ids["bancario_independiente"]),
            ],
        },
    )

    assert response.status_code == 400
    assert "no está disponible" in response.text

    with session_factory() as session:
        assert session.scalars(select(Conciliacion)).all() == []

        assert session.get(
            MovimientoPrevisto,
            ids["previsto_independiente"],
        ).estado == "PENDIENTE"

        assert session.get(
            MovimientoBancario,
            ids["bancario_independiente"],
        ).estado == "PENDIENTE"


def test_manual_rechaza_movimientos_ya_conciliados(
    monkeypatch,
) -> None:
    """Impide confirmar dos veces una selección manual."""

    (
        client,
        session_factory,
        previsto_ids,
        bancario_ids,
    ) = crear_escenario_seleccion_manual(
        [(10000, "INGRESO")],
        [(10000, "INGRESO")],
    )

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    datos = {
        "previsto_ids": [str(previsto_ids[0])],
        "bancario_ids": [str(bancario_ids[0])],
    }

    primera = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data=datos,
    )

    assert primera.status_code == 302

    segunda = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data=datos,
    )

    assert segunda.status_code == 400

    with session_factory() as session:
        asociaciones = session.scalars(
            select(Conciliacion)
        ).all()

        assert len(asociaciones) == 1
        assert asociaciones[0].importe_asociado == 10000

        assert session.get(
            MovimientoPrevisto,
            previsto_ids[0],
        ).estado == "CONCILIADO"

        assert session.get(
            MovimientoBancario,
            bancario_ids[0],
        ).estado == "CONCILIADO"


@pytest.mark.parametrize(
    "construir_datos",
    [
        pytest.param(
            lambda p, b: {
                "previsto_ids": ["999999"],
                "bancario_ids": [str(b[0])],
            },
            id="previsto-inexistente",
        ),
        pytest.param(
            lambda p, b: {
                "previsto_ids": [str(p[0])],
                "bancario_ids": ["999999"],
            },
            id="bancario-inexistente",
        ),
        pytest.param(
            lambda p, b: {
                "previsto_ids": [str(p[0]), str(p[0])],
                "bancario_ids": [str(b[0])],
            },
            id="previsto-duplicado",
        ),
        pytest.param(
            lambda p, b: {
                "previsto_ids": [str(p[0])],
                "bancario_ids": [str(b[0]), str(b[0])],
            },
            id="bancario-duplicado",
        ),
        pytest.param(
            lambda p, b: {
                "previsto_ids": ["abc"],
                "bancario_ids": [str(b[0])],
            },
            id="identificador-no-numerico",
        ),
        pytest.param(
            lambda p, b: {
                "previsto_ids": ["-1"],
                "bancario_ids": [str(b[0])],
            },
            id="identificador-negativo",
        ),
        pytest.param(
            lambda p, b: {
                "previsto_ids": [],
                "bancario_ids": [str(b[0])],
            },
            id="sin-previstos",
        ),
        pytest.param(
            lambda p, b: {
                "previsto_ids": [str(p[0])],
                "bancario_ids": [],
            },
            id="sin-bancarios",
        ),
    ],
)
def test_manual_rechaza_identificadores_invalidos(
    monkeypatch,
    construir_datos,
) -> None:
    """Rechaza solicitudes manipuladas sin alterar la base de datos."""

    (
        client,
        session_factory,
        previsto_ids,
        bancario_ids,
    ) = crear_escenario_seleccion_manual(
        [(10000, "INGRESO")],
        [(10000, "INGRESO")],
    )

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    datos = construir_datos(
        previsto_ids,
        bancario_ids,
    )

    response = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data=datos,
    )

    assert response.status_code == 400

    with session_factory() as session:
        assert session.scalars(
            select(Conciliacion)
        ).all() == []

        assert session.get(
            MovimientoPrevisto,
            previsto_ids[0],
        ).estado == "PENDIENTE"

        assert session.get(
            MovimientoBancario,
            bancario_ids[0],
        ).estado == "PENDIENTE"


def test_revision_propone_movimientos_parciales_por_saldo() -> None:
    """Incluye movimientos PARCIAL en las propuestas automáticas."""

    client, _, _ = crear_escenario_movimientos_parciales()

    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    grupos = re.findall(
        r'<tbody\b[^>]*class="[^"]*\brevision-propuesta\b[^"]*"'
        r'[^>]*>(.*?)</tbody>',
        response.text,
        flags=re.DOTALL,
    )

    assert len(grupos) == 1

    grupo = grupos[0]

    assert "Alquiler parcialmente cobrado" in grupo
    assert "Transferencia parcialmente aplicada" in grupo

    # Debe mostrarse el importe disponible para conciliar.
    assert grupo.count("320,00") == 2

    # La pantalla debe identificar que los movimientos
    # tienen un importe original distinto del pendiente.
    assert "920,00" in grupo
    assert "500,00" in grupo


def test_revision_manual_muestra_saldos_parciales(
    monkeypatch,
) -> None:
    """Las casillas manuales utilizan saldos pendientes."""

    client, _, ids = crear_escenario_movimientos_parciales()

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    manual = response.text.split(
        'class="revision__seccion revision__seccion--manual"',
        1,
    )[1]

    assert "Alquiler parcialmente cobrado" in manual
    assert "Transferencia parcialmente aplicada" in manual

    # Las casillas deben usar 32000 céntimos, no
    # 92000 ni 50000, para calcular los totales.
    casillas = re.findall(
        r'<input\b[^>]*type="checkbox"[^>]*>',
        manual,
        flags=re.DOTALL,
    )

    casilla_previsto = next(
        casilla
        for casilla in casillas
        if (
            'name="previsto_ids"' in casilla
            and f'value="{ids["previsto_parcial"]}"' in casilla
        )
    )

    casilla_bancario = next(
        casilla
        for casilla in casillas
        if (
            'name="bancario_ids"' in casilla
            and f'value="{ids["bancario_parcial"]}"' in casilla
        )
    )

    assert 'data-importe="32000"' in casilla_previsto
    assert 'data-importe="32000"' in casilla_bancario

    assert "320,00" in manual
    assert "920,00" in manual
    assert "500,00" in manual


def test_confirmar_manual_movimientos_parciales(
    monkeypatch,
) -> None:
    """Concilia los 320 € restantes sin alterar asociaciones anteriores."""

    client, session_factory, ids = (
        crear_escenario_movimientos_parciales()
    )

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    response = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data={
            "previsto_ids": [
                str(ids["previsto_parcial"]),
            ],
            "bancario_ids": [
                str(ids["bancario_parcial"]),
            ],
        },
    )

    assert response.status_code == 302
    assert response.location.endswith(
        "/conciliacion/revisar"
    )

    with session_factory() as db_session:
        asociaciones = db_session.scalars(
            select(Conciliacion)
        ).all()

        assert len(asociaciones) == 3

        importes_por_pareja = {
            (
                asociacion.movimiento_bancario_id,
                asociacion.movimiento_previsto_id,
            ): asociacion.importe_asociado
            for asociacion in asociaciones
        }

        assert importes_por_pareja == {
            (
                ids["bancario_anterior"],
                ids["previsto_parcial"],
            ): 60000,
            (
                ids["bancario_parcial"],
                ids["previsto_anterior"],
            ): 18000,
            (
                ids["bancario_parcial"],
                ids["previsto_parcial"],
            ): 32000,
        }

        assert db_session.get(
            MovimientoPrevisto,
            ids["previsto_parcial"],
        ).estado == "CONCILIADO"

        assert db_session.get(
            MovimientoBancario,
            ids["bancario_parcial"],
        ).estado == "CONCILIADO"

    # Los movimientos totalmente conciliados dejan
    # de aparecer en la revisión.
    response = client.get("/conciliacion/revisar")

    assert "Alquiler parcialmente cobrado" not in response.text
    assert "Transferencia parcialmente aplicada" not in response.text


def test_no_aceptar_propuesta_rechazada_en_sesion() -> None:
    """No permite aceptar una propuesta rechazada previamente."""

    client, session_factory, ids = (
        crear_escenario_rechazo_agrupado()
    )

    datos = {
        "bancario_ids": [
            str(ids["bancario_1"]),
            str(ids["bancario_2"]),
        ],
        "previsto_ids": [
            str(ids["previsto_agrupado"]),
        ],
    }

    # Primero se rechaza la propuesta 1:2.
    response = client.post(
        "/conciliacion/revisar/propuestas/rechazar",
        data=datos,
    )

    assert response.status_code == 302

    # La propuesta ya no debe aparecer entre las automáticas.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    propuestas_html = response.text.split(
        'class="revision__seccion revision__seccion--manual"',
        1,
    )[0]

    assert "Alquiler para rechazo" not in propuestas_html

    # Se intenta aceptar la propuesta utilizando sus
    # identificadores originales, como si el formulario
    # anterior siguiera abierto.
    response = client.post(
        "/conciliacion/revisar/propuestas/aceptar",
        data=datos,
    )

    assert response.status_code == 400

    # El intento no debe modificar la base de datos.
    with session_factory() as db_session:
        asociaciones = db_session.scalars(
            select(Conciliacion)
        ).all()

        assert asociaciones == []

        assert db_session.get(
            MovimientoPrevisto,
            ids["previsto_agrupado"],
        ).estado == "PENDIENTE"

        assert db_session.get(
            MovimientoBancario,
            ids["bancario_1"],
        ).estado == "PENDIENTE"

        assert db_session.get(
            MovimientoBancario,
            ids["bancario_2"],
        ).estado == "PENDIENTE"

    # El intento fallido tampoco debe anular el rechazo.
    response = client.get("/conciliacion/revisar")

    manual = response.text.split(
        'class="revision__seccion revision__seccion--manual"',
        1,
    )[1]

    assert "Alquiler para rechazo" in manual
    assert "PAGADOR RECHAZO 1" in manual
    assert "PAGADOR RECHAZO 2" in manual


def test_proponer_conciliacion_uno_a_uno_con_diferencia(
    inmueble,
) -> None:
    """Sugiere una pareja fiable aunque sus importes difieran."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=92000,
        contraparte="ANA PEREZ",
        estado="PENDIENTE",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=90000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="INGRESO ANA PEREZ",
        referencia_bancaria="",
        huella_importacion="diferencia-alquiler-1",
        estado="PENDIENTE",
    )

    propuestas = buscar_propuestas_conciliacion(
        [bancario],
        [previsto],
    )

    assert len(propuestas) == 1

    propuesta = propuestas[0]

    assert propuesta.bancarios == [bancario]
    assert propuesta.previstos == [previsto]

    # Se conservan los importes reales.
    assert bancario.importe == 90000
    assert previsto.importe_esperado == 92000

    # Generar la propuesta no concilia los movimientos.
    assert bancario.estado == "PENDIENTE"
    assert previsto.estado == "PENDIENTE"
    assert bancario.conciliaciones == []
    assert previsto.conciliaciones == []


def test_revision_muestra_propuesta_uno_a_uno_con_diferencia() -> None:
    """Muestra una correspondencia con diferencia sin permitir aceptarla."""

    client, session_factory, ids = (
        crear_escenario_aceptacion_individual()
    )

    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    grupos = re.findall(
        r'<tbody\b[^>]*class="[^"]*\brevision-propuesta\b[^"]*"'
        r'[^>]*>(.*?)</tbody>',
        response.text,
        flags=re.DOTALL,
    )

    grupo_diferente = next(
        (
            grupo
            for grupo in grupos
            if "Seguro septiembre" in grupo
        ),
        None,
    )

    assert grupo_diferente is not None

    assert "ASEGURADORA XYZ" in grupo_diferente
    assert "250,00" in grupo_diferente
    assert "240,00" in grupo_diferente

    # Se identifica expresamente la diferencia.
    assert "10,00" in grupo_diferente
    assert "revision-propuesta--diferencia" in response.text

    # Aparecen los botones para confirmar
    assert "Conciliar parcialmente" in response.text
    assert "Aceptar diferencia" in response.text
    assert "Rechazar" in response.text

    assert re.search(
        r'<button\b[^>]*name="accion"[^>]*value="parcial"',
        response.text,
        re.S,
    )

    assert re.search(
        r'<button\b[^>]*name="accion"[^>]*value="aceptar_diferencia"',
        response.text,
        re.S,
    )

    # Sí puede rechazarse para trasladarla a manual.
    assert (
        "revision-propuesta__boton--rechazar"
        in grupo_diferente
    )

    # Ninguno de los dos movimientos aparece duplicado
    # en las listas manuales.
    manual = response.text.split(
        'class="revision__seccion revision__seccion--manual"',
        1,
    )[1]

    assert "Seguro septiembre" not in manual
    assert "ASEGURADORA XYZ" not in manual

    # La consulta no modifica los movimientos.
    with session_factory() as db_session:
        assert db_session.get(
            MovimientoPrevisto,
            ids["p_diferente"],
        ).estado == "PENDIENTE"

        assert db_session.get(
            MovimientoBancario,
            ids["b_diferente"],
        ).estado == "PENDIENTE"


def test_aceptar_propuesta_exacta_rechaza_diferencia() -> None:
    """No confirma por la ruta exacta una propuesta con diferencia."""

    client, session_factory, ids = (
        crear_escenario_aceptacion_individual()
    )

    # La correspondencia con diferencia debe ser visible
    # entre las propuestas automáticas.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200
    assert "revision-propuesta--diferencia" in response.text
    assert "Seguro septiembre" in response.text

    # Intentamos utilizar directamente la ruta de aceptación
    # exacta, aunque la pantalla no ofrezca ese botón.
    response = client.post(
        "/conciliacion/revisar/propuestas/aceptar",
        data={
            "bancario_ids": [
                str(ids["b_diferente"]),
            ],
            "previsto_ids": [
                str(ids["p_diferente"]),
            ],
        },
    )

    assert response.status_code == 400

    with session_factory() as db_session:
        asociaciones = db_session.scalars(
            select(Conciliacion)
        ).all()

        assert asociaciones == []

        previsto = db_session.get(
            MovimientoPrevisto,
            ids["p_diferente"],
        )

        bancario = db_session.get(
            MovimientoBancario,
            ids["b_diferente"],
        )

        assert previsto.estado == "PENDIENTE"
        assert bancario.estado == "PENDIENTE"

        # Los importes originales deben permanecer intactos.
        assert previsto.importe_esperado == 25000
        assert bancario.importe == 24000

    # La propuesta continúa disponible para revisión.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200
    assert "Seguro septiembre" in response.text
    assert "ASEGURADORA XYZ" in response.text


def test_revision_permite_conciliar_previsto_sin_banco() -> None:
    """La revisión ofrece conciliar sin banco y conserva el motivo."""

    (
        client,
        session_factory,
        previsto_ids,
        _,
    ) = crear_escenario_seleccion_manual(
        previstos_datos=[(25000, "GASTO")],
        bancarios_datos=[],
    )

    previsto_id = previsto_ids[0]
    ruta_manual = (
        f"/conciliacion/previstos/{previsto_id}"
        "/conciliar-manualmente"
    )

    # La nueva pantalla debe ofrecer la operación
    # sin exigir seleccionar un bancario.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200
    assert "Previsto manual 1" in response.text
    assert ruta_manual in response.text

    # Se utiliza la ruta de conciliación manual
    # sin banco que ya existe en Contab.
    response = client.post(
        ruta_manual,
        data={"notas": "Pago efectuado en metálico"},
    )

    assert response.status_code == 302

    with session_factory() as db_session:
        previsto = db_session.get(
            MovimientoPrevisto,
            previsto_id,
        )

        assert previsto.estado == "CONCILIADO"
        assert previsto.metodo_conciliacion == "MANUAL"
        assert previsto.notas == "Pago efectuado en metálico"

        asociaciones = db_session.scalars(
            select(Conciliacion)
        ).all()

        # No se crea un movimiento bancario ficticio
        # ni una asociación inexistente.
        assert asociaciones == []

    # El previsto conciliado deja de aparecer
    # entre los pendientes de revisión.
    response = client.get("/conciliacion/revisar")

    assert "Previsto manual 1" not in response.text


@pytest.mark.parametrize(
    (
        "importe_previsto",
        "importe_bancario",
        "accion",
        "estado_previsto",
        "estado_bancario",
        "cierra_previsto",
        "cierra_bancario",
    ),
    [
        (
            100000, 60000, "parcial",
            "PARCIAL", "CONCILIADO",
            False, False,
        ),
        (
            100000, 99500, "aceptar_diferencia",
            "CONCILIADO", "CONCILIADO",
            True, False,
        ),
        (
            100000, 100500, "aceptar_diferencia",
            "CONCILIADO", "CONCILIADO",
            False, True,
        ),
    ],
)
def test_revision_manual_con_diferencias(
    monkeypatch,
    importe_previsto,
    importe_bancario,
    accion,
    estado_previsto,
    estado_bancario,
    cierra_previsto,
    cierra_bancario,
) -> None:
    """La acción elegida determina si se conserva el saldo disponible."""

    client, session_factory, previstos, bancarios = (
        crear_escenario_seleccion_manual(
            previstos_datos=[(importe_previsto, "INGRESO")],
            bancarios_datos=[(importe_bancario, "INGRESO")],
        )
    )

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    response = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data={
            "previsto_ids": [str(previstos[0])],
            "bancario_ids": [str(bancarios[0])],
            "accion": accion,
        },
    )

    assert response.status_code == 302
    assert response.location.endswith("/conciliacion/revisar")

    with session_factory() as db_session:
        previsto = db_session.get(
            MovimientoPrevisto, previstos[0]
        )
        bancario = db_session.get(
            MovimientoBancario, bancarios[0]
        )

        asociaciones = db_session.scalars(
            select(Conciliacion)
        ).all()

        assert len(asociaciones) == 1

        conciliacion = asociaciones[0]

        assert conciliacion.importe_asociado == min(
            importe_previsto,
            importe_bancario,
        )

        assert conciliacion.cierra_previsto is cierra_previsto
        assert conciliacion.cierra_bancario is cierra_bancario

        assert previsto.estado == estado_previsto
        assert bancario.estado == estado_bancario
        assert previsto.metodo_conciliacion == "INDIVIDUAL"

        # Ningún importe original se altera.
        assert previsto.importe_esperado == importe_previsto
        assert bancario.importe == importe_bancario

    # La revisión sólo debe mostrar los movimientos
    # cuyos saldos sigan disponibles para conciliar.
    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    if estado_previsto == "PARCIAL":
        assert "Previsto manual 1" in response.text
    else:
        assert "Previsto manual 1" not in response.text

    assert "Bancario manual 1" not in response.text


def test_revision_rechaza_accion_desconocida(
    monkeypatch,
) -> None:
    """No se interpreta una acción inválida como una confirmación."""

    client, session_factory, previstos, bancarios = (
        crear_escenario_seleccion_manual(
            previstos_datos=[(100000, "INGRESO")],
            bancarios_datos=[(100000, "INGRESO")],
        )
    )

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    response = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data={
            "previsto_ids": [str(previstos[0])],
            "bancario_ids": [str(bancarios[0])],
            "accion": "accion_inexistente",
        },
    )

    assert response.status_code == 400

    with session_factory() as db_session:
        assert db_session.scalars(
            select(Conciliacion)
        ).all() == []

        assert db_session.get(
            MovimientoPrevisto,
            previstos[0],
        ).estado == "PENDIENTE"

        assert db_session.get(
            MovimientoBancario,
            bancarios[0],
        ).estado == "PENDIENTE"


def test_revision_manual_ofrece_acciones_de_conciliacion(
    monkeypatch,
) -> None:
    """La pantalla permite distinguir una aplicación parcial de un cierre."""

    client, _, _, _ = crear_escenario_seleccion_manual(
        previstos_datos=[(100000, "INGRESO")],
        bancarios_datos=[(99500, "INGRESO")],
    )

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    assert 'name="accion"' in response.text
    assert 'value="parcial"' in response.text
    assert 'value="aceptar_diferencia"' in response.text

    assert "Conciliar parcialmente" in response.text
    assert "Aceptar diferencia" in response.text

    # Conservamos la confirmación exacta existente.
    assert 'value="exacta"' in response.text


@pytest.mark.parametrize(
    ("accion", "estado_ultimo", "cierra_ultimo"),
    [
        ("parcial", "PARCIAL", False),
        ("aceptar_diferencia", "CONCILIADO", True),
    ],
)
def test_revision_agrupada_varios_previstos_un_bancario(
    monkeypatch,
    accion,
    estado_ultimo,
    cierra_ultimo,
) -> None:
    """Concilia dos previstos con un ingreso de 1.199,62 €."""

    client, session_factory, previstos, bancarios = (
        crear_escenario_seleccion_manual(
            previstos_datos=[
                (100000, "INGRESO"),
                (20000, "INGRESO"),
            ],
            bancarios_datos=[
                (119962, "INGRESO"),
            ],
        )
    )

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    with session_factory() as db_session:
        with db_session.begin():
            primero = db_session.get(
                MovimientoPrevisto, previstos[0]
            )
            segundo = db_session.get(
                MovimientoPrevisto, previstos[1]
            )

            contrato = Contrato(
                inmueble=primero.inmueble,
                fecha_inicio=date(2026, 1, 1),
                fecha_vencimiento=date(2035, 12, 31),
                genera_factura=True,
                fecha_inicio_facturacion=date(2026, 1, 1),
                fianza=0,
                direccion_facturacion="Dirección de prueba",
                poblacion_facturacion="Madrid",
                provincia_facturacion="Madrid",
                concepto_factura="Alquiler",
            )

            db_session.add(contrato)

            primero.contrato = contrato
            segundo.contrato = contrato

    response = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data={
            "previsto_ids": [str(i) for i in previstos],
            "bancario_ids": [str(i) for i in bancarios],
            "accion": accion,
        },
    )

    assert response.status_code == 302

    with session_factory() as db_session:
        asociaciones = db_session.scalars(
            select(Conciliacion).order_by(Conciliacion.id)
        ).all()

        assert len(asociaciones) == 2

        assert [
            (
                c.movimiento_previsto_id,
                c.importe_asociado,
                c.cierra_previsto,
            )
            for c in asociaciones
        ] == [
            (previstos[0], 100000, False),
            (previstos[1], 19962, cierra_ultimo),
        ]

        assert db_session.get(
            MovimientoPrevisto, previstos[0]
        ).estado == "CONCILIADO"

        assert db_session.get(
            MovimientoPrevisto, previstos[1]
        ).estado == estado_ultimo

        assert db_session.get(
            MovimientoBancario, bancarios[0]
        ).estado == "CONCILIADO"

    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200
    assert "Previsto manual 1" not in response.text

    if accion == "parcial":
        assert "Previsto manual 2" in response.text
        assert "0,38" in response.text
    else:
        assert "Previsto manual 2" not in response.text


@pytest.mark.parametrize(
    ("accion", "estado_previsto", "cierra_previsto"),
    [
        ("parcial", "PARCIAL", False),
        ("aceptar_diferencia", "CONCILIADO", True),
    ],
)
def test_revision_agrupada_un_previsto_varios_bancarios(
    monkeypatch,
    accion,
    estado_previsto,
    cierra_previsto,
) -> None:
    """Concilia una factura con dos ingresos insuficientes."""

    client, session_factory, previstos, bancarios = (
        crear_escenario_seleccion_manual(
            previstos_datos=[
                (120000, "INGRESO"),
            ],
            bancarios_datos=[
                (60000, "INGRESO"),
                (59962, "INGRESO"),
            ],
        )
    )

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    response = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data={
            "previsto_ids": [str(i) for i in previstos],
            "bancario_ids": [str(i) for i in bancarios],
            "accion": accion,
        },
    )

    assert response.status_code == 302

    with session_factory() as db_session:
        asociaciones = db_session.scalars(
            select(Conciliacion).order_by(Conciliacion.id)
        ).all()

        assert len(asociaciones) == 2

        assert [
            (
                c.movimiento_bancario_id,
                c.importe_asociado,
                c.cierra_previsto,
            )
            for c in asociaciones
        ] == [
            (bancarios[0], 60000, False),
            (bancarios[1], 59962, cierra_previsto),
        ]

        assert db_session.get(
            MovimientoPrevisto, previstos[0]
        ).estado == estado_previsto

        for bancario_id in bancarios:
            assert db_session.get(
                MovimientoBancario, bancario_id
            ).estado == "CONCILIADO"

    response = client.get("/conciliacion/revisar")

    assert response.status_code == 200

    if accion == "parcial":
        assert "Previsto manual 1" in response.text
        assert "0,38" in response.text
    else:
        assert "Previsto manual 1" not in response.text

    assert "Bancario manual 1" not in response.text
    assert "Bancario manual 2" not in response.text


def test_revision_agrupada_rechaza_movimientos_sin_asociacion(
    monkeypatch,
) -> None:
    """No confirma una selección donde una factura no recibe importe."""

    client, session_factory, previstos, bancarios = (
        crear_escenario_seleccion_manual(
            previstos_datos=[
                (100000, "INGRESO"),
                (20000, "INGRESO"),
            ],
            bancarios_datos=[
                (60000, "INGRESO"),
            ],
        )
    )

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    response = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data={
            "previsto_ids": [str(i) for i in previstos],
            "bancario_ids": [str(i) for i in bancarios],
            "accion": "parcial",
        },
    )

    assert response.status_code == 400

    with session_factory() as db_session:
        asociaciones = db_session.scalars(
            select(Conciliacion)
        ).all()

        assert asociaciones == []

        for previsto_id in previstos:
            assert db_session.get(
                MovimientoPrevisto, previsto_id
            ).estado == "PENDIENTE"

        assert db_session.get(
            MovimientoBancario, bancarios[0]
        ).estado == "PENDIENTE"


@pytest.mark.parametrize(
    ("accion", "estado_previsto", "cierra_previsto"),
    [
        ("parcial", "PARCIAL", False),
        ("aceptar_diferencia", "CONCILIADO", True),
    ],
)
def test_propuesta_automatica_con_diferencia_se_puede_confirmar(
    monkeypatch,
    accion,
    estado_previsto,
    cierra_previsto,
) -> None:
    client, session_factory, previstos, bancarios = (
        crear_escenario_seleccion_manual(
            previstos_datos=[(120000, "INGRESO")],
            bancarios_datos=[(119962, "INGRESO")],
        )
    )

    # Garantiza una propuesta automática identificable.
    def propuestas_controladas(
        bancarios_disponibles,
        previstos_disponibles,
        aliases_configurados=None,
    ):
        return [
            PropuestaConciliacion(
                bancarios=[bancarios_disponibles[0]],
                previstos=[previstos_disponibles[0]],
                puntuacion=100,
                motivos=["Correspondencia con diferencia."],
            )
        ]

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        propuestas_controladas,
    )

    client.application.config["TESTING"] = True
    client.application.config["PROPAGATE_EXCEPTIONS"] = True

    pagina = client.get("/conciliacion/revisar")
    assert pagina.status_code == 200
    assert "Conciliar parcialmente" in pagina.text
    assert "Aceptar diferencia" in pagina.text

    respuesta = client.post(
        "/conciliacion/revisar/propuestas/aceptar",
        data={
            "previsto_ids": [str(previstos[0])],
            "bancario_ids": [str(bancarios[0])],
            "accion": accion,
        },
    )

    assert respuesta.status_code == 302

    with session_factory() as db_session:
        asociacion = db_session.scalar(select(Conciliacion))

        assert asociacion is not None
        assert asociacion.importe_asociado == 119962
        assert asociacion.cierra_previsto is cierra_previsto
        assert asociacion.cierra_bancario is False

        assert db_session.get(
            MovimientoPrevisto, previstos[0]
        ).estado == estado_previsto

        assert db_session.get(
            MovimientoBancario, bancarios[0]
        ).estado == "CONCILIADO"


@pytest.mark.parametrize(
    ("naturaleza", "otra_naturaleza"),
    [
        ("INGRESO", "GASTO"),
        ("GASTO", "INGRESO"),
    ],
)
def test_revision_manual_separa_movimientos_por_naturaleza(
    monkeypatch,
    naturaleza,
    otra_naturaleza,
) -> None:
    client, _, previstos, bancarios = (
        crear_escenario_seleccion_manual(
            previstos_datos=[
                (100000, naturaleza),
                (20000, otra_naturaleza),
            ],
            bancarios_datos=[
                (100000, naturaleza),
                (20000, otra_naturaleza),
            ],
        )
    )

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    response = client.get("/conciliacion/revisar")
    assert response.status_code == 200

    manual = response.text.split(
        'class="revision__seccion revision__seccion--manual"',
        1,
    )[1]

    formularios = re.findall(
        r'<form\b[^>]*class="revision-manual__formulario"'
        r'[^>]*>.*?</form>',
        manual,
        re.S,
    )

    assert len(formularios) == 2

    formulario_ingresos = next(
        formulario
        for formulario in formularios
        if 'id="revision-manual-formulario-ingresos"' in formulario
    )

    formulario_gastos = next(
        formulario
        for formulario in formularios
        if 'id="revision-manual-formulario-gastos"' in formulario
    )

    formularios_por_naturaleza = {
        "INGRESO": formulario_ingresos,
        "GASTO": formulario_gastos,
    }

    formulario = formularios_por_naturaleza[naturaleza]
    otro = formularios_por_naturaleza[otra_naturaleza]

    for nombre, id_movimiento in (
        ("previsto_ids", previstos[0]),
        ("bancario_ids", bancarios[0]),
    ):
        casilla = (
            rf'<input\b(?=[^>]*name="{nombre}")'
            rf'(?=[^>]*value="{id_movimiento}")[^>]*>'
        )

        assert re.search(casilla, formulario, re.S)
        assert not re.search(casilla, otro, re.S)

    for nombre, id_movimiento in (
        ("previsto_ids", previstos[1]),
        ("bancario_ids", bancarios[1]),
    ):
        casilla = (
            rf'<input\b(?=[^>]*name="{nombre}")'
            rf'(?=[^>]*value="{id_movimiento}")[^>]*>'
        )

        assert re.search(casilla, otro, re.S)
        assert not re.search(casilla, formulario, re.S)


def test_revision_manual_cada_formulario_tiene_totales_y_acciones(
    monkeypatch,
) -> None:
    client, _, _, _ = crear_escenario_seleccion_manual(
        previstos_datos=[
            (100000, "INGRESO"),
            (30000, "GASTO"),
        ],
        bancarios_datos=[
            (99500, "INGRESO"),
            (30000, "GASTO"),
        ],
    )

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    response = client.get("/conciliacion/revisar")
    assert response.status_code == 200

    manual = response.text.split(
        'class="revision__seccion revision__seccion--manual"',
        1,
    )[1]

    formularios = re.findall(
        r'<form\b[^>]*class="revision-manual__formulario"'
        r'[^>]*>.*?</form>',
        manual,
        re.S,
    )

    assert len(formularios) == 2

    for formulario in formularios:
        assert (
            'action="/conciliacion/revisar/manual/confirmar"'
            in formulario
        )

        for clase in (
            "revision-manual__total-previstos",
            "revision-manual__total-bancarios",
            "revision-manual__diferencia",
        ):
            assert re.search(
                rf'<strong\b[^>]*class="[^"]*\b{re.escape(clase)}\b[^"]*"',
                formulario,
                re.S,
            )

        for accion in (
            "exacta",
            "parcial",
            "aceptar_diferencia",
        ):
            assert re.search(
                rf'<button\b(?=[^>]*name="accion")'
                rf'(?=[^>]*value="{accion}")[^>]*>',
                formulario,
                re.S,
            )

        # Ninguna casilla comienza seleccionada.
        casillas = re.findall(
            r'<input\b[^>]*type="checkbox"[^>]*>',
            formulario,
            re.S,
        )

        assert casillas
        assert all(
            not re.search(r'\bchecked(?:\s|=|>)', casilla)
            for casilla in casillas
        )


def test_revision_manual_rechaza_naturalezas_mezcladas(
    monkeypatch,
) -> None:
    client, session_factory, previstos, bancarios = (
        crear_escenario_seleccion_manual(
            previstos_datos=[
                (100000, "INGRESO"),
                (20000, "GASTO"),
            ],
            bancarios_datos=[
                (120000, "INGRESO"),
            ],
        )
    )

    monkeypatch.setattr(
        rutas_conciliacion,
        "buscar_propuestas_conciliacion",
        lambda *args, **kwargs: [],
    )

    response = client.post(
        "/conciliacion/revisar/manual/confirmar",
        data={
            "previsto_ids": [
                str(previstos[0]),
                str(previstos[1]),
            ],
            "bancario_ids": [str(bancarios[0])],
            "accion": "exacta",
        },
    )

    assert response.status_code == 400

    with session_factory() as db_session:
        assert db_session.scalars(
            select(Conciliacion)
        ).all() == []

        for previsto_id in previstos:
            assert db_session.get(
                MovimientoPrevisto, previsto_id
            ).estado == "PENDIENTE"

        assert db_session.get(
            MovimientoBancario, bancarios[0]
        ).estado == "PENDIENTE"


from io import BytesIO
from datetime import date
from sqlalchemy import select

from contab.database import Base
from contab.models import (
    Inmueble,
    MovimientoBancario,
    MovimientoPrevisto,
)
from contab.app import create_app



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



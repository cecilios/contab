from io import BytesIO

from sqlalchemy import select

from contab.database import Base
from contab.models import MovimientoBancario
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


def test_formulario_importar_movimientos() -> None:
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



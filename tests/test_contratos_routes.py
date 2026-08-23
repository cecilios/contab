"""Pruebas de las rutas web del módulo de contratos."""

from datetime import date

from sqlalchemy import select

from contab.app import create_app
from contab.database import Base
from contab.models import (
    Contrato,
    Inmueble,
    Inquilino,
    RentaContrato,
    RevisionRenta,
)
from contab.contratos.services import crear_contrato



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
    """Selecciona la base de datos utilizada por los tests web."""
    client.post(
        "/",
        data={"database": "test"},
    )


def test_listado_contratos_vacio() -> None:
    """Comprueba que se informa cuando todavía no existen contratos."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.get("/contratos/")

    assert response.status_code == 200
    assert "Contratos" in response.text
    assert "No hay contratos registrados." in response.text


def test_formulario_nuevo_contrato_muestra_inmuebles_e_inquilinos() -> None:
    """Comprueba que el formulario ofrece inmuebles activos e inquilinos."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        session.add(
            Inmueble(
                referencia="LOCAL-1",
                codigo_facturacion="A1",
                descripcion="Local comercial",
                direccion="Dirección",
                poblacion="Pontevedra",
                provincia="Pontevedra",
            )
        )
        session.add(
            Inquilino(
                nombre="Ana Pérez",
                nif="11111111A",
            )
        )
        session.commit()

    response = client.get("/contratos/nuevo")

    assert response.status_code == 200
    assert "Nuevo contrato" in response.text
    assert "LOCAL-1" in response.text
    assert "Ana Pérez" in response.text


def test_formulario_nuevo_contrato_no_muestra_inmuebles_inactivos() -> None:
    """Comprueba que no pueden seleccionarse inmuebles inactivos."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        session.add(
            Inmueble(
                referencia="INACTIVO-1",
                codigo_facturacion="I1",
                descripcion="Local inactivo",
                direccion="Dirección",
                poblacion="Pontevedra",
                provincia="Pontevedra",
                activo=False,
            )
        )
        session.commit()

    response = client.get("/contratos/nuevo")

    assert response.status_code == 200
    assert "INACTIVO-1" not in response.text


def test_crear_contrato_desde_formulario() -> None:
    """Comprueba que el alta crea conjuntamente contrato, renta y revisión."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        primero = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )
        segundo = Inquilino(
            nombre="Luis García",
            nif="22222222B",
        )

        session.add_all([inmueble, primero, segundo])
        session.commit()

        inmueble_id = inmueble.id
        primero_id = primero.id
        segundo_id = segundo.id

    response = client.post(
        "/contratos/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_seleccionado": [
                str(primero_id),
                str(segundo_id),
            ],
            f"titular_orden_{primero_id}": "2",
            f"titular_orden_{segundo_id}": "1",
            "fecha_inicio": "15/09/2026",
            "fecha_vencimiento": "14/09/2031",
            "fecha_inicio_facturacion": "01/10/2026",
            "fianza": "1500,00",
            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección de facturación",
            "codigo_postal_facturacion": "36001",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Alquiler local comercial",
            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/10/2027",
            "metodo_revision": "IPC",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "LOCAL-1" in response.text
    assert "Ana Pérez" in response.text

    with session_factory() as session:
        contratos = session.scalars(select(Contrato)).all()
        rentas = session.scalars(select(RentaContrato)).all()
        revisiones = session.scalars(select(RevisionRenta)).all()

        assert len(contratos) == 1
        assert len(rentas) == 1
        assert len(revisiones) == 1

        contrato = contratos[0]

        assert contrato.inmueble_id == inmueble_id
        assert contrato.fecha_inicio == date(2026, 9, 15)
        assert contrato.fecha_inicio_facturacion == date(2026, 10, 1)
        assert contrato.fianza == 150000
        assert contrato.iva_porcentaje == 2100
        assert contrato.retencion_porcentaje == 1900

        assert rentas[0].importe == 150000
        assert revisiones[0].fecha_prevista == date(2027, 10, 1)

        assert len(contrato.titulares) == 2

        titulares = sorted(
            contrato.titulares,
            key=lambda titular: titular.orden,
        )

        assert titulares[0].inquilino_id == segundo_id
        assert titulares[0].orden == 1

        assert titulares[1].inquilino_id == primero_id
        assert titulares[1].orden == 2


def test_crear_contrato_rechaza_orden_titulares_repetido() -> None:
    """Comprueba que dos titulares no pueden compartir el mismo orden."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        primero = Inquilino(nombre="Ana Pérez", nif="11111111A")
        segundo = Inquilino(nombre="Luis García", nif="22222222B")

        session.add_all([inmueble, primero, segundo])
        session.commit()

        inmueble_id = inmueble.id
        primero_id = primero.id
        segundo_id = segundo.id

    response = client.post(
        "/contratos/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_seleccionado": [
                str(primero_id),
                str(segundo_id),
            ],
            f"titular_orden_{primero_id}": "1",
            f"titular_orden_{segundo_id}": "1",
            "fecha_inicio": "15/09/2026",
            "fecha_vencimiento": "14/09/2031",
            "fecha_inicio_facturacion": "01/10/2026",
            "fianza": "1500,00",
            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección",
            "codigo_postal_facturacion": "36001",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Alquiler",
            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/10/2027",
            "metodo_revision": "IPC",
        },
    )

    assert response.status_code == 400
    assert "El orden de los titulares no puede repetirse." in response.text


def test_crear_contrato_rechaza_orden_titulares_no_consecutivo() -> None:
    """Comprueba que el orden de titulares debe ser consecutivo desde 1."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        primero = Inquilino(nombre="Ana Pérez", nif="11111111A")
        segundo = Inquilino(nombre="Luis García", nif="22222222B")

        session.add_all([inmueble, primero, segundo])
        session.commit()

        inmueble_id = inmueble.id
        primero_id = primero.id
        segundo_id = segundo.id

    response = client.post(
        "/contratos/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_seleccionado": [
                str(primero_id),
                str(segundo_id),
            ],
            f"titular_orden_{primero_id}": "1",
            f"titular_orden_{segundo_id}": "3",
            "fecha_inicio": "15/09/2026",
            "fecha_vencimiento": "14/09/2031",
            "fecha_inicio_facturacion": "01/10/2026",
            "fianza": "1500,00",
            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección",
            "codigo_postal_facturacion": "36001",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Alquiler",
            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/10/2027",
            "metodo_revision": "IPC",
        },
    )

    assert response.status_code == 400
    assert (
        "El orden de los titulares debe ser consecutivo desde 1."
        in response.text
    )


def test_crear_contrato_rechaza_fecha_inexistente() -> None:
    """Comprueba que una fecha inexistente no crea parcialmente el contrato."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        session.add_all([inmueble, inquilino])
        session.commit()

        inmueble_id = inmueble.id
        inquilino_id = inquilino.id

    response = client.post(
        "/contratos/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_seleccionado": [str(inquilino_id)],
            f"titular_orden_{inquilino_id}": "1",
            "fecha_inicio": "30/02/2026",
            "fecha_vencimiento": "14/09/2031",
            "fecha_inicio_facturacion": "01/10/2026",
            "fianza": "1500,00",
            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección",
            "codigo_postal_facturacion": "36001",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Alquiler",
            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/10/2027",
            "metodo_revision": "IPC",
        },
    )

    assert response.status_code == 400
    assert "La fecha indicada no es válida." in response.text

    with session_factory() as session:
        assert session.scalars(select(Contrato)).all() == []
        assert session.scalars(select(RentaContrato)).all() == []
        assert session.scalars(select(RevisionRenta)).all() == []


def test_crear_contrato_rechaza_fecha_inexistente() -> None:
    """Comprueba que una fecha inexistente no crea parcialmente el contrato."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        session.add_all([inmueble, inquilino])
        session.commit()

        inmueble_id = inmueble.id
        inquilino_id = inquilino.id

    response = client.post(
        "/contratos/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_seleccionado": [str(inquilino_id)],
            f"titular_orden_{inquilino_id}": "1",
            "fecha_inicio": "30/02/2026",
            "fecha_vencimiento": "14/09/2031",
            "fecha_inicio_facturacion": "01/10/2026",
            "fianza": "1500,00",
            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección",
            "codigo_postal_facturacion": "36001",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Alquiler",
            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/10/2027",
            "metodo_revision": "IPC",
        },
    )

    assert response.status_code == 400
    assert (
        "La fecha indicada no es válida o no tiene el formato dd/mm/aaaa."
        in response.text
    )

    with session_factory() as session:
        assert session.scalars(select(Contrato)).all() == []
        assert session.scalars(select(RentaContrato)).all() == []
        assert session.scalars(select(RevisionRenta)).all() == []

def test_formulario_editar_contrato_muestra_datos_actuales() -> None:
    """Comprueba que el formulario de edición muestra los datos del contrato."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        session.add_all([inmueble, inquilino])
        session.flush()

        contrato = crear_contrato(
            inmueble=inmueble,
            titulares=[inquilino],
            fecha_inicio=date(2026, 9, 15),
            fecha_vencimiento=date(2031, 9, 14),
            fecha_inicio_facturacion=date(2026, 10, 1),
            fianza=150000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección de facturación",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler local",
            renta_inicial=150000,
            fecha_primera_revision=date(2027, 10, 1),
            metodo_revision="IPC",
        )

        session.add(contrato)
        session.commit()
        contrato_id = contrato.id

    response = client.get(f"/contratos/{contrato_id}/editar")

    assert response.status_code == 200
    assert "Editar contrato" in response.text
    assert "15/09/2026" in response.text
    assert "14/09/2031" in response.text
    assert "01/10/2026" in response.text
    assert 'value="1500,00"' in response.text
    assert 'value="21,00"' in response.text
    assert 'value="19,00"' in response.text
    assert "Ana Pérez" in response.text


def test_editar_contrato_guarda_cambios() -> None:
    """Comprueba que pueden corregirse los datos de un contrato existente."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        session.add_all([inmueble, inquilino])
        session.flush()

        contrato = crear_contrato(
            inmueble=inmueble,
            titulares=[inquilino],
            fecha_inicio=date(2026, 9, 15),
            fecha_vencimiento=date(2031, 9, 14),
            fecha_inicio_facturacion=date(2026, 10, 1),
            fianza=150000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección antigua",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Concepto antiguo",
            renta_inicial=150000,
            fecha_primera_revision=date(2027, 10, 1),
            metodo_revision="IPC",
        )

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id
        inmueble_id = inmueble.id
        inquilino_id = inquilino.id

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_seleccionado": [str(inquilino_id)],
            f"titular_orden_{inquilino_id}": "1",
            "fecha_inicio": "15/09/2026",
            "fecha_vencimiento": "30/09/2031",
            "fecha_inicio_facturacion": "01/10/2026",
            "fianza": "1600,00",
            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección corregida",
            "codigo_postal_facturacion": "36002",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Concepto corregido",
            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/10/2027",
            "metodo_revision": "IPC",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        assert contrato.fecha_vencimiento == date(2031, 9, 30)
        assert contrato.fianza == 160000
        assert contrato.direccion_facturacion == "Dirección corregida"
        assert contrato.codigo_postal_facturacion == "36002"
        assert contrato.concepto_factura == "Concepto corregido"


def test_editar_contrato_permite_reordenar_titulares() -> None:
    """Comprueba que puede corregirse el orden de los titulares."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        primero = Inquilino(nombre="Ana Pérez", nif="11111111A")
        segundo = Inquilino(nombre="Luis García", nif="22222222B")

        session.add_all([inmueble, primero, segundo])
        session.flush()

        contrato = crear_contrato(
            inmueble=inmueble,
            titulares=[primero, segundo],
            fecha_inicio=date(2026, 9, 15),
            fecha_vencimiento=date(2031, 9, 14),
            fecha_inicio_facturacion=date(2026, 10, 1),
            fianza=150000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=150000,
            fecha_primera_revision=date(2027, 10, 1),
            metodo_revision="IPC",
        )

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id
        inmueble_id = inmueble.id
        primero_id = primero.id
        segundo_id = segundo.id

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_seleccionado": [
                str(primero_id),
                str(segundo_id),
            ],
            f"titular_orden_{primero_id}": "2",
            f"titular_orden_{segundo_id}": "1",
            "fecha_inicio": "15/09/2026",
            "fecha_vencimiento": "14/09/2031",
            "fecha_inicio_facturacion": "01/10/2026",
            "fianza": "1500,00",
            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección",
            "codigo_postal_facturacion": "36001",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Alquiler",
            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/10/2027",
            "metodo_revision": "IPC",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        titulares = sorted(
            contrato.titulares,
            key=lambda titular: titular.orden,
        )

        assert titulares[0].inquilino_id == segundo_id
        assert titulares[0].orden == 1
        assert titulares[1].inquilino_id == primero_id
        assert titulares[1].orden == 2


def test_editar_contrato_inexistente_devuelve_404() -> None:
    """Comprueba que editar un contrato inexistente devuelve 404."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.get("/contratos/99999/editar")

    assert response.status_code == 404


def test_formulario_finalizar_contrato_responde() -> None:
    """Comprueba que puede abrirse la confirmación de finalización."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        session.add_all([inmueble, inquilino])
        session.flush()

        contrato = crear_contrato(
            inmueble=inmueble,
            titulares=[inquilino],
            fecha_inicio=date(2026, 9, 15),
            fecha_vencimiento=date(2031, 9, 14),
            fecha_inicio_facturacion=date(2026, 10, 1),
            fianza=150000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=150000,
            fecha_primera_revision=date(2027, 10, 1),
            metodo_revision="IPC",
        )

        session.add(contrato)
        session.commit()
        contrato_id = contrato.id

    response = client.get(
        f"/contratos/{contrato_id}/finalizar"
    )

    assert response.status_code == 200
    assert "Finalizar contrato" in response.text
    assert "LOCAL-1" in response.text
    assert "Fecha de finalización" in response.text
    assert "Cancelar" in response.text


def test_finalizar_contrato_guarda_fecha_fin() -> None:
    """Comprueba que finalizar un contrato guarda su fecha de fin."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        session.add_all([inmueble, inquilino])
        session.flush()

        contrato = crear_contrato(
            inmueble=inmueble,
            titulares=[inquilino],
            fecha_inicio=date(2026, 9, 15),
            fecha_vencimiento=date(2031, 9, 14),
            fecha_inicio_facturacion=date(2026, 10, 1),
            fianza=150000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=150000,
            fecha_primera_revision=date(2027, 10, 1),
            metodo_revision="IPC",
        )

        session.add(contrato)
        session.commit()
        contrato_id = contrato.id

    response = client.post(
        f"/contratos/{contrato_id}/finalizar",
        data={
            "fecha_fin": "31/08/2028",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "FINALIZADO" in response.text

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        assert contrato.fecha_fin == date(2028, 8, 31)


def test_finalizar_contrato_rechaza_fecha_anterior_al_inicio() -> None:
    """Comprueba que un contrato no puede finalizar antes de comenzar."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        session.add_all([inmueble, inquilino])
        session.flush()

        contrato = crear_contrato(
            inmueble=inmueble,
            titulares=[inquilino],
            fecha_inicio=date(2026, 9, 15),
            fecha_vencimiento=date(2031, 9, 14),
            fecha_inicio_facturacion=date(2026, 10, 1),
            fianza=150000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=150000,
            fecha_primera_revision=date(2027, 10, 1),
            metodo_revision="IPC",
        )

        session.add(contrato)
        session.commit()
        contrato_id = contrato.id

    response = client.post(
        f"/contratos/{contrato_id}/finalizar",
        data={
            "fecha_fin": "14/09/2026",
        },
    )

    assert response.status_code == 400
    assert (
        "La fecha de finalización no puede ser anterior "
        "al inicio del contrato."
        in response.text
    )

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        assert contrato.fecha_fin is None


def test_finalizar_contrato_rechaza_fecha_invalida() -> None:
    """Comprueba que se rechaza una fecha de finalización inexistente."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        session.add_all([inmueble, inquilino])
        session.flush()

        contrato = crear_contrato(
            inmueble=inmueble,
            titulares=[inquilino],
            fecha_inicio=date(2026, 9, 15),
            fecha_vencimiento=date(2031, 9, 14),
            fecha_inicio_facturacion=date(2026, 10, 1),
            fianza=150000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=150000,
            fecha_primera_revision=date(2027, 10, 1),
            metodo_revision="IPC",
        )

        session.add(contrato)
        session.commit()
        contrato_id = contrato.id

    response = client.post(
        f"/contratos/{contrato_id}/finalizar",
        data={
            "fecha_fin": "31/02/2028",
        },
    )

    assert response.status_code == 400
    assert (
        "La fecha indicada no es válida o no tiene el formato dd/mm/aaaa."
        in response.text
    )


def test_finalizar_contrato_inexistente_devuelve_404() -> None:
    """Comprueba que finalizar un contrato inexistente devuelve 404."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.get("/contratos/99999/finalizar")

    assert response.status_code == 404


def test_formulario_editar_contrato_muestra_fecha_fin() -> None:
    """Comprueba que la edición muestra la fecha de finalización existente."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        session.add_all([inmueble, inquilino])
        session.flush()

        contrato = crear_contrato(
            inmueble=inmueble,
            titulares=[inquilino],
            fecha_inicio=date(2026, 9, 15),
            fecha_vencimiento=date(2031, 9, 14),
            fecha_inicio_facturacion=date(2026, 10, 1),
            fianza=150000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=150000,
            fecha_primera_revision=date(2027, 10, 1),
            metodo_revision="IPC",
        )
        contrato.fecha_fin = date(2028, 8, 31)

        session.add(contrato)
        session.commit()
        contrato_id = contrato.id

    response = client.get(f"/contratos/{contrato_id}/editar")

    assert response.status_code == 200
    assert 'value="31/08/2028"' in response.text


def test_editar_contrato_permite_eliminar_fecha_fin() -> None:
    """Comprueba que puede corregirse una finalización introducida por error."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-1",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        session.add_all([inmueble, inquilino])
        session.flush()

        contrato = crear_contrato(
            inmueble=inmueble,
            titulares=[inquilino],
            fecha_inicio=date(2026, 9, 15),
            fecha_vencimiento=date(2031, 9, 14),
            fecha_inicio_facturacion=date(2026, 10, 1),
            fianza=150000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=150000,
            fecha_primera_revision=date(2027, 10, 1),
            metodo_revision="IPC",
        )
        contrato.fecha_fin = date(2028, 8, 31)

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id
        inmueble_id = inmueble.id
        inquilino_id = inquilino.id

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_seleccionado": [str(inquilino_id)],
            f"titular_orden_{inquilino_id}": "1",
            "fecha_inicio": "15/09/2026",
            "fecha_vencimiento": "14/09/2031",
            "fecha_fin": "",
            "fecha_inicio_facturacion": "01/10/2026",
            "fianza": "1500,00",
            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección",
            "codigo_postal_facturacion": "36001",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Alquiler",
            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/10/2027",
            "metodo_revision": "IPC",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)
        assert contrato.fecha_fin is None


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
from contab.contratos.services import (
    crear_anexo_prorroga,
    crear_anexo_renta_permanente,
    crear_anexo_renta_temporal,
    crear_contrato,
)



def _crear_contrato_para_test(session) -> Contrato:
    """Crea y persiste un contrato completo para pruebas de rutas."""
    inmueble = Inmueble(
        referencia="LOCAL-ANEXO",
        codigo_facturacion="AX",
        descripcion="Local para anexos",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )
    inquilino = Inquilino(
        nombre="Ana Pérez",
        nif="99999999R",
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
    session.refresh(contrato)

    return contrato



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
    assert "No hay contratos vigentes." in response.text
    assert "No hay contratos finalizados." in response.text


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
    assert "Finalizados" in response.text
    assert "LOCAL-1" in response.text
    assert "31/08/2028" in response.text

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


def test_seleccionar_tipo_anexo_responde() -> None:
    """Comprueba que puede elegirse el tipo de anexo a crear."""
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
        f"/contratos/{contrato_id}/anexo"
    )

    assert response.status_code == 200
    assert "Añadir anexo" in response.text
    assert "Prórroga del contrato" in response.text
    assert "Cambio permanente de renta" in response.text
    assert "Cambio temporal de renta" in response.text


def test_formulario_anexo_prorroga_responde() -> None:
    """Comprueba que puede abrirse el formulario de prórroga."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.get(
        f"/contratos/{contrato_id}/anexo/prorroga"
    )

    assert response.status_code == 200
    assert "Prórroga del contrato" in response.text
    assert "Fecha del anexo" in response.text
    assert "Nueva fecha de vencimiento" in response.text


def test_formulario_anexo_renta_permanente_responde() -> None:
    """Comprueba que puede abrirse el formulario de cambio permanente."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.get(
        f"/contratos/{contrato_id}/anexo/renta-permanente"
    )

    assert response.status_code == 200
    assert "Cambio permanente de renta" in response.text
    assert "Fecha de efecto" in response.text
    assert "Nueva renta" in response.text


def test_formulario_anexo_renta_temporal_responde() -> None:
    """Comprueba que puede abrirse el formulario de cambio temporal."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.get(
        f"/contratos/{contrato_id}/anexo/renta-temporal"
    )

    assert response.status_code == 200
    assert "Cambio temporal de renta" in response.text
    assert "Fecha desde" in response.text
    assert "Fecha hasta" in response.text


def test_anexo_contrato_inexistente_devuelve_404() -> None:
    """Comprueba que no pueden añadirse anexos a un contrato inexistente."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.get("/contratos/99999/anexo")

    assert response.status_code == 404


def test_guardar_anexo_prorroga() -> None:
    """Comprueba que una prórroga se guarda y actualiza el vencimiento."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.post(
        f"/contratos/{contrato_id}/anexo/prorroga",
        data={
            "fecha": "01/06/2031",
            "nueva_fecha_vencimiento": "14/09/2036",
            "descripcion": "Prórroga por cinco años",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        assert contrato.fecha_vencimiento == date(2036, 9, 14)
        assert len(contrato.anexos) == 1

        anexo = contrato.anexos[0]

        assert anexo.tipo == "PRORROGA"
        assert anexo.fecha == date(2031, 6, 1)
        assert anexo.nueva_fecha_vencimiento == date(2036, 9, 14)


def test_guardar_anexo_renta_permanente() -> None:
    """Comprueba que un cambio permanente crea una nueva renta vinculada."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.post(
        f"/contratos/{contrato_id}/anexo/renta-permanente",
        data={
            "fecha": "20/05/2028",
            "fecha_desde": "01/06/2028",
            "importe": "1750,00",
            "descripcion": "Nueva renta pactada",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        rentas = sorted(
            contrato.rentas,
            key=lambda renta: renta.fecha_desde,
        )

        assert len(contrato.anexos) == 1
        assert len(rentas) == 2

        anexo = contrato.anexos[0]
        nueva_renta = rentas[-1]

        assert anexo.tipo == "CAMBIO_RENTA"
        assert nueva_renta.fecha_desde == date(2028, 6, 1)
        assert nueva_renta.importe == 175000
        assert nueva_renta.anexo_id == anexo.id


def test_guardar_anexo_renta_temporal() -> None:
    """Comprueba que un cambio temporal crea un ajuste vinculado."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.post(
        f"/contratos/{contrato_id}/anexo/renta-temporal",
        data={
            "fecha": "20/05/2028",
            "fecha_desde": "01/06/2028",
            "fecha_hasta": "31/12/2028",
            "tipo": "IMPORTE_FIJO",
            "valor": "1200,00",
            "descripcion": "Renta temporal reducida",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        assert len(contrato.anexos) == 1
        assert len(contrato.ajustes_renta) == 1

        anexo = contrato.anexos[0]
        ajuste = contrato.ajustes_renta[0]

        assert anexo.tipo == "CAMBIO_RENTA"
        assert ajuste.fecha_desde == date(2028, 6, 1)
        assert ajuste.fecha_hasta == date(2028, 12, 31)
        assert ajuste.tipo == "IMPORTE_FIJO"
        assert ajuste.valor == 120000
        assert ajuste.anexo_id == anexo.id


def test_historico_anexos_vacio() -> None:
    """Comprueba que se informa cuando un contrato no tiene anexos."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.get(
        f"/contratos/{contrato_id}/anexos"
    )

    assert response.status_code == 200
    assert "Histórico de anexos" in response.text
    assert "No hay anexos registrados." in response.text


def test_historico_anexos_muestra_prorroga_y_cambios_renta() -> None:
    """Comprueba que el histórico muestra los efectos de los anexos."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)

        with session.begin_nested():
            anexo_prorroga = crear_anexo_prorroga(
                contrato=contrato,
                fecha=date(2028, 5, 10),
                nueva_fecha_vencimiento=date(2036, 9, 14),
                descripcion="Prórroga acordada",
            )

            anexo_renta, renta = crear_anexo_renta_permanente(
                contrato=contrato,
                fecha=date(2028, 6, 15),
                fecha_desde=date(2028, 7, 1),
                importe=175000,
                descripcion="Nueva renta",
            )

            anexo_temporal, ajuste = crear_anexo_renta_temporal(
                contrato=contrato,
                fecha=date(2029, 1, 15),
                fecha_desde=date(2029, 2, 1),
                fecha_hasta=date(2029, 4, 30),
                tipo="IMPORTE_FIJO",
                valor=120000,
                descripcion="Reducción temporal",
            )

            session.add_all(
                [
                    anexo_prorroga,
                    anexo_renta,
                    anexo_temporal,
                ]
            )

        session.commit()
        contrato_id = contrato.id

    response = client.get(
        f"/contratos/{contrato_id}/anexos"
    )

    assert response.status_code == 200

    assert "Prórroga acordada" in response.text
    assert "14/09/2036" in response.text

    assert "Nueva renta" in response.text
    assert "1.750,00" in response.text
    assert "01/07/2028" in response.text

    assert "Reducción temporal" in response.text
    assert "01/02/2029" in response.text
    assert "30/04/2029" in response.text
    assert "1.200,00" in response.text


def test_historico_anexos_contrato_inexistente_devuelve_404() -> None:
    """Comprueba que el histórico de un contrato inexistente devuelve 404."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.get("/contratos/99999/anexos")

    assert response.status_code == 404


def test_anexo_prorroga_rechaza_vencimiento_no_posterior() -> None:
    """Comprueba que una prórroga debe ampliar realmente el vencimiento."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.post(
        f"/contratos/{contrato_id}/anexo/prorroga",
        data={
            "fecha": "01/06/2031",
            "nueva_fecha_vencimiento": "14/09/2031",
            "descripcion": "",
        },
    )

    assert response.status_code == 400
    assert "debe ser posterior" in response.text

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)
        assert contrato.anexos == []


def test_anexo_renta_permanente_rechaza_fecha_que_no_es_dia_uno() -> None:
    """Comprueba que una renta permanente debe comenzar el día 1."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.post(
        f"/contratos/{contrato_id}/anexo/renta-permanente",
        data={
            "fecha": "20/05/2028",
            "fecha_desde": "15/06/2028",
            "importe": "1750,00",
            "descripcion": "",
        },
    )

    assert response.status_code == 400
    assert "día 1 del mes" in response.text

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)
        assert len(contrato.rentas) == 1
        assert contrato.anexos == []


def test_anexo_renta_temporal_rechaza_fecha_hasta_que_no_es_fin_de_mes() -> None:
    """Comprueba que un ajuste temporal debe terminar a fin de mes."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.post(
        f"/contratos/{contrato_id}/anexo/renta-temporal",
        data={
            "fecha": "20/05/2028",
            "fecha_desde": "01/06/2028",
            "fecha_hasta": "29/11/2028",
            "tipo": "IMPORTE_FIJO",
            "valor": "1200,00",
            "descripcion": "",
        },
    )

    assert response.status_code == 400
    assert "último día del mes" in response.text

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)
        assert contrato.ajustes_renta == []
        assert contrato.anexos == []


def test_anexo_renta_temporal_rechaza_porcentaje_superior_a_cien() -> None:
    """Comprueba que una reducción porcentual no puede superar el 100 %."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.post(
        f"/contratos/{contrato_id}/anexo/renta-temporal",
        data={
            "fecha": "20/05/2028",
            "fecha_desde": "01/06/2028",
            "fecha_hasta": "30/11/2028",
            "tipo": "REDUCCION_PORCENTUAL",
            "valor": "120,00",
            "descripcion": "",
        },
    )

    assert response.status_code == 400
    assert "entre 0 % y 100 %" in response.text


def test_formulario_nuevo_contrato_no_muestra_fecha_resolucion() -> None:
    """Comprueba que fecha de resolucion no se muestra en un contrato nuevo"""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.get("/contratos/nuevo")

    assert response.status_code == 200
    assert "Fecha de resolución" not in response.text


def test_editar_contrato_vigente_no_muestra_fecha_resolucion() -> None:
    """Comprueba que fecha de resolucion no se muestra en un contrato vigente"""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.get(
        f"/contratos/{contrato_id}/editar"
    )

    assert response.status_code == 200
    assert "Fecha de resolución" not in response.text
    

def test_lista_contratos_separa_vigentes_y_finalizados() -> None:
    """Comprueba que la lista separa contratos vigentes y finalizados."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        vigente = _crear_contrato_para_test(session)

        inmueble = Inmueble(
            referencia="LOCAL-FINALIZADO",
            codigo_facturacion="AF",
            descripcion="Local finalizado",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre="Luis García",
            nif="88888888Q",
        )

        session.add_all([inmueble, inquilino])
        session.flush()

        finalizado = crear_contrato(
            inmueble=inmueble,
            titulares=[inquilino],
            fecha_inicio=date(2024, 1, 1),
            fecha_vencimiento=date(2029, 12, 31),
            fecha_inicio_facturacion=date(2024, 1, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=100000,
            fecha_primera_revision=date(2025, 1, 1),
            metodo_revision="IPC",
        )

        finalizado.fecha_fin = date(2026, 6, 30)

        session.add(finalizado)
        session.commit()

    response = client.get("/contratos/")

    assert response.status_code == 200

    html = response.text

    assert "Vigentes" in html
    assert "Finalizados" in html

    posicion_vigentes = html.index("Vigentes")
    posicion_finalizados = html.index("Finalizados")
    posicion_contrato_vigente = html.index("LOCAL-ANEXO")
    posicion_contrato_finalizado = html.index("LOCAL-FINALIZADO")

    assert posicion_vigentes < posicion_contrato_vigente < posicion_finalizados
    assert posicion_finalizados < posicion_contrato_finalizado

    assert "Resolución:" in html
    assert "30/06/2026" in html


def test_editar_contrato_rechaza_inicio_posterior_a_renta_historica() -> None:
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)

        contrato.rentas.append(
            RentaContrato(
                fecha_desde=date(2028, 6, 1),
                importe=175000,
            )
        )

        session.commit()
        contrato_id = contrato.id
        inmueble_id = contrato.inmueble_id
        inquilino_id = contrato.titulares[0].inquilino_id

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_seleccionado": [str(inquilino_id)],
            f"titular_orden_{inquilino_id}": "1",
            "fecha_inicio": "01/07/2028",
            "fecha_vencimiento": "30/09/2031",
            "fecha_inicio_facturacion": "01/08/2028",
            "fianza": "1600,00",
            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección corregida",
            "codigo_postal_facturacion": "36002",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Concepto corregido",
            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/07/2029",
            "metodo_revision": "IPC",
        },
    )

    assert response.status_code == 400
    assert "renta ya registrada" in response.text


def test_editar_contrato_rechaza_vencimiento_anterior_a_prorroga() -> None:
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)

        anexo = crear_anexo_prorroga(
            contrato=contrato,
            fecha=date(2030, 6, 1),
            nueva_fecha_vencimiento=date(2036, 9, 14),
            descripcion="Prórroga",
        )

        session.add(anexo)
        session.commit()

        contrato_id = contrato.id
        inmueble_id = contrato.inmueble_id
        inquilino_id = contrato.titulares[0].inquilino_id

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_seleccionado": [str(inquilino_id)],
            f"titular_orden_{inquilino_id}": "1",
            "fecha_inicio": "01/07/2028",
            "fecha_vencimiento": "14/09/2031",
            "fecha_inicio_facturacion": "01/07/2028",
            "fianza": "1500,00",
            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección",
            "codigo_postal_facturacion": "36001",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Alquiler",
            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/08/2028",
            "metodo_revision": "IPC",
        },
    )

    assert response.status_code == 400
    assert "vencimiento establecido por una prórroga" in response.text


def test_editar_contrato_rechaza_inicio_posterior_a_ajuste() -> None:
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)

        anexo, ajuste = crear_anexo_renta_temporal(
            contrato=contrato,
            fecha=date(2028, 5, 20),
            fecha_desde=date(2028, 6, 1),
            fecha_hasta=date(2028, 8, 31),
            tipo="IMPORTE_FIJO",
            valor=120000,
            descripcion="Reducción temporal",
        )

        session.add(anexo)
        session.commit()

        contrato_id = contrato.id
        inmueble_id = contrato.inmueble_id
        inquilino_id = contrato.titulares[0].inquilino_id

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_seleccionado": [str(inquilino_id)],
            f"titular_orden_{inquilino_id}": "1",
            "fecha_inicio": "01/07/2028",
            "fecha_vencimiento": "14/09/2031",
            "fecha_inicio_facturacion": "01/08/2028",
            "fianza": "1500,00",
            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección",
            "codigo_postal_facturacion": "36001",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Alquiler",
            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/10/2028",
            "metodo_revision": "IPC",
        },
    )

    assert response.status_code == 400
    assert "ajuste de renta ya registrado" in response.text



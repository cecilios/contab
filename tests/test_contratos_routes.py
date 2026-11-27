"""Pruebas de las rutas web del módulo de contratos."""

import pytest
import re

from datetime import date
from sqlalchemy import select
from werkzeug.datastructures import MultiDict

from contab.app import create_app
from contab.database import Base
from contab.contratos.routes import _titulares_formulario, _resolver_titulares
from contab.config import CategoriaContable

from contab.facturacion.services import (
    contabilizar_ingreso_sin_factura,
    crear_factura,
)
from contab.models import (
    AjusteRenta,
    Contrato,
    Inmueble,
    Inquilino,
    RentaContrato,
    RevisionRenta,
    SolicitudReembolso,
)
from contab.contratos.services import (
    ContratoError,
    crear_anexo_carencia,
    crear_anexo_prorroga,
    crear_anexo_renta_permanente,
    crear_anexo_renta_temporal,
    crear_contrato,
)



def _crear_inmueble_prueba(**datos) -> Inmueble:
    """Construye inmuebles válidos para las pruebas."""

    es_hijo = (
        datos.get("inmueble_padre") is not None
        or datos.get("inmueble_padre_id") is not None
    )

    if es_hijo:
        propiedad = {
            "porcentaje_titular": None,
            "tipo_derecho": None,
            "porcentaje_derecho": None,
            "fecha_adquisicion": None,
            "tipo_adquisicion": None,
            "importe_adquisicion": None,
            "gastos_adquisicion": None,
            "fecha_transmision": None,
        }
    else:
        propiedad = {
            "porcentaje_titular": 10000,
            "tipo_derecho": "PLENA_PROPIEDAD",
            "porcentaje_derecho": 10000,
            "fecha_adquisicion": date(2020, 1, 1),
            "tipo_adquisicion": "ONEROSA",
            "importe_adquisicion": 0,
            "gastos_adquisicion": 0,
            "fecha_transmision": None,
        }

    return Inmueble(**{**propiedad, **datos})


def _datos_nuevo_contrato_valido(
    inmueble_id: int,
) -> dict[str, str]:
    """Devuelve un formulario de alta válido que cada test puede modificar."""
    return {
        "inmueble_id": str(inmueble_id),
        **_datos_titulares(
            ("Ana Pérez", "11111111A"),
        ),
        "fecha_inicio": "15/09/2026",
        "fecha_vencimiento": "14/09/2031",
        "genera_factura": "on",
        "fecha_inicio_facturacion": "01/10/2026",
        "fianza": "1500,00",
        "iva_porcentaje": "21,00",
        "retencion_porcentaje": "19,00",
        "direccion_facturacion": "Dirección",
        "codigo_postal_facturacion": "36001",
        "poblacion_facturacion": "Pontevedra",
        "provincia_facturacion": "Pontevedra",
        "concepto_factura": "Alquiler local",
        "renta_inicial": "1500,00",
        "fecha_primera_revision": "01/10/2027",
        "metodo_revision": "IPC_NACIONAL",
    }


def _preparar_alta_contrato():
    """Prepara aplicación, inmueble e inquilino para probar un alta."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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

    return (
        client,
        session_factory,
        inmueble_id,
    )


def _crear_contrato_para_test(
    session,
    genera_factura: bool = True,
) -> Contrato:
    """Crea y persiste un contrato completo para pruebas de rutas."""
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-ANEXO",
        tipo="L",
        codigo_facturacion="AX",
        descripcion="Local para anexos",
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
        genera_factura=genera_factura,
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
        metodo_revision="IPC_NACIONAL",
    )

    session.add(contrato)
    session.commit()
    session.refresh(contrato)

    return contrato


def _datos_titulares(
    *titulares: tuple[str, str],
) -> dict[str, str]:
    datos = {}

    for posicion in range(1, 5):
        if posicion <= len(titulares):
            nombre, nif = titulares[posicion - 1]
        else:
            nombre, nif = "", ""

        datos[f"titular_{posicion}_nombre"] = nombre
        datos[f"titular_{posicion}_nif"] = nif

    return datos


def _etiqueta_control(html: str, identificador: str) -> str:
    """Obtiene la etiqueta HTML de apertura de un control."""

    resultado = re.search(
        rf'<(?:input|select)\b[^>]*'
        rf'\bid="{re.escape(identificador)}"[^>]*>',
        html,
    )

    assert resultado is not None, (
        f"No se encuentra el control {identificador}"
    )

    return resultado.group(0)


def _texto_label(html: str, identificador: str) -> str:
    """Obtiene el contenido de la etiqueta de un campo."""

    resultado = re.search(
        rf'<label\b[^>]*'
        rf'\bfor="{re.escape(identificador)}"[^>]*>'
        rf'(.*?)</label>',
        html,
        re.DOTALL,
    )

    assert resultado is not None, (
        f"No se encuentra la etiqueta {identificador}"
    )

    return resultado.group(1)


def crear_app_test():
    """Crea una aplicación con una base SQLite aislada para las pruebas."""
    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="test-secret-key",
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
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        session.add(
            _crear_inmueble_prueba(
                referencia="LOCAL-1",
                tipo="L",
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
    assert 'name="titular_1_nombre"' in response.text
    assert 'name="titular_1_nif"' in response.text
    assert 'name="titular_4_nombre"' in response.text
    assert 'name="titular_4_nif"' in response.text


def test_formulario_nuevo_contrato_no_muestra_inmuebles_inactivos() -> None:
    """Comprueba que no pueden seleccionarse inmuebles inactivos."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        session.add(
            _crear_inmueble_prueba(
                referencia="INACTIVO-1",
                tipo="L",
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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
            "titular_1_nombre": "Luis García",
            "titular_1_nif": "22222222B",
            "titular_2_nombre": "Ana Pérez",
            "titular_2_nif": "11111111A",
            "titular_3_nombre": "",
            "titular_3_nif": "",
            "titular_4_nombre": "",
            "titular_4_nif": "",
            "fecha_inicio": "15/09/2026",
            "fecha_vencimiento": "14/09/2031",
            "genera_factura": "on",
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
            "metodo_revision": "IPC_NACIONAL",
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
        assert contrato.genera_factura is True


def test_crear_contrato_rechaza_fecha_inexistente() -> None:
    """Comprueba que una fecha inexistente no crea parcialmente el contrato."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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
            "titular_1_nombre": "Ana Pérez",
            "titular_1_nif": "11111111A",
            "titular_2_nombre": "",
            "titular_2_nif": "",
            "titular_3_nombre": "",
            "titular_3_nif": "",
            "titular_4_nombre": "",
            "titular_4_nif": "",
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
            "metodo_revision": "IPC_NACIONAL",
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




def test_crear_contrato_rechaza_error_metodo_actualizacion() -> None:
    """Comprueba que si no se ha seleccionado método de actualización da error"""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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

    response = client.post(
        "/contratos/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_1_nombre": "Ana Pérez",
            "titular_1_nif": "11111111A",
            "titular_2_nombre": "",
            "titular_2_nif": "",
            "titular_3_nombre": "",
            "titular_3_nif": "",
            "titular_4_nombre": "",
            "titular_4_nif": "",
            "fecha_inicio": "15/02/2026",
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
            "metodo_revision": "",
            "genera_factura": "on",
        },
    )

    assert response.status_code == 400
    assert (
        "La revisión debe indicar un método de actualización."
        in response.text
    )

    with session_factory() as session:
        assert session.scalar(
            select(Contrato)
        ) is None


def test_formulario_editar_contrato_muestra_datos_actuales() -> None:
    """Comprueba que el formulario de edición muestra los datos del contrato."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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
            genera_factura = True,
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
            metodo_revision="IPC_NACIONAL",
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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
            genera_factura = True,
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
            metodo_revision="IPC_NACIONAL",
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
            **_datos_titulares(
                ("Ana Pérez", "11111111A"),
            ),
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
            "metodo_revision": "IPC_NACIONAL",
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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
            genera_factura = True,
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
            metodo_revision="IPC_NACIONAL",
        )

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id
        inmueble_id = inmueble.id

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_1_nombre": "Luis García",
            "titular_1_nif": "22222222B",
            "titular_2_nombre": "Ana Pérez",
            "titular_2_nif": "11111111A",
            "titular_3_nombre": "",
            "titular_3_nif": "",
            "titular_4_nombre": "",
            "titular_4_nif": "",
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
            "metodo_revision": "IPC_NACIONAL",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        titulares = sorted(
            contrato.titulares,
            key=lambda titular: titular.orden,
        )

        assert titulares[0].inquilino.nombre == "Luis García"
        assert titulares[0].orden == 1
        assert titulares[1].inquilino.nombre == "Ana Pérez"
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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
            genera_factura = True,
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
            metodo_revision="IPC_NACIONAL",
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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
            genera_factura = True,
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
            metodo_revision="IPC_NACIONAL",
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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
            genera_factura = True,
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
            metodo_revision="IPC_NACIONAL",
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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
            genera_factura = True,
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
            metodo_revision="IPC_NACIONAL",
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
    assert 'name="fecha_fin"' in response.text


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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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
            genera_factura = True,
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
            metodo_revision="IPC_NACIONAL",
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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
            genera_factura = True,
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
            metodo_revision="IPC_NACIONAL",
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
            **_datos_titulares(
                ("Ana Pérez", "11111111A"),
            ),
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
            "metodo_revision": "IPC_NACIONAL",
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
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
            genera_factura = True,
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
            metodo_revision="IPC_NACIONAL",
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
            "numero": "1",
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
            "numero": "1",
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
            "numero": "1",
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
                numero=1,
                fecha=date(2028, 5, 10),
                nueva_fecha_vencimiento=date(2036, 9, 14),
                descripcion="Prórroga acordada",
            )

            anexo_renta, renta = crear_anexo_renta_permanente(
                contrato=contrato,
                numero=2,
                fecha=date(2028, 6, 15),
                fecha_desde=date(2028, 7, 1),
                importe=175000,
                descripcion="Nueva renta",
            )

            anexo_temporal, ajuste = crear_anexo_renta_temporal(
                contrato=contrato,
                numero=3,
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
            "numero": "1",
            "fecha": "01/06/2031",
            "nueva_fecha_vencimiento": "14/09/2031",
            "descripcion": "",
        },
    )

    assert response.status_code == 400
    assert "debe ser posterior" in response.text
    assert 'name="fecha"' in response.text
    assert (
        'name="nueva_fecha_vencimiento"'
        in response.text
    )
    assert 'name="descripcion"' in response.text

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
            "numero": "1",
            "fecha": "20/05/2028",
            "fecha_desde": "15/06/2028",
            "importe": "1750,00",
            "descripcion": "",
        },
    )

    assert response.status_code == 400
    assert "día 1 del mes" in response.text
    assert 'name="fecha"' in response.text
    assert 'name="fecha_desde"' in response.text
    assert 'name="importe"' in response.text
    assert 'name="descripcion"' in response.text

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
            "numero": "1",
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
    assert 'name="fecha"' in response.text
    assert 'name="fecha_desde"' in response.text
    assert 'name="fecha_hasta"' in response.text
    assert 'name="tipo"' in response.text
    assert 'name="valor"' in response.text
    assert 'name="descripcion"' in response.text

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
            "numero": "1",
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


def test_lista_contratos_separa_y_ordena_por_inmueble() -> None:
    """Separa contratos vigentes y finalizados y los ordena por inmueble."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    def crear_contrato_lista(
        session,
        *,
        referencia: str,
        codigo_facturacion: str,
        nombre: str,
        nif: str,
        fecha_inicio: date,
        fecha_fin: date | None = None,
    ) -> Contrato:
        inmueble = _crear_inmueble_prueba(
            referencia=referencia,
            tipo="L",
            codigo_facturacion=codigo_facturacion,
            descripcion=f"Local {referencia}",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre=nombre,
            nif=nif,
        )

        session.add_all([inmueble, inquilino])
        session.flush()

        contrato = crear_contrato(
            inmueble=inmueble,
            titulares=[inquilino],
            fecha_inicio=fecha_inicio,
            fecha_vencimiento=date(2031, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=fecha_inicio,
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=100000,
            fecha_primera_revision=date(
                fecha_inicio.year + 1,
                fecha_inicio.month,
                1,
            ),
            metodo_revision="IPC_NACIONAL",
        )

        contrato.fecha_fin = fecha_fin

        session.add(contrato)

        return contrato

    with session_factory() as session:
        # Se crean deliberadamente en un orden distinto
        # del orden alfabético esperado.
        crear_contrato_lista(
            session,
            referencia="LOCAL-C",
            codigo_facturacion="AC",
            nombre="Inquilino C",
            nif="33333333C",
            fecha_inicio=date(2026, 3, 1),
        )
        crear_contrato_lista(
            session,
            referencia="LOCAL-A",
            codigo_facturacion="AA",
            nombre="Inquilino A",
            nif="11111111A",
            fecha_inicio=date(2026, 1, 1),
        )
        crear_contrato_lista(
            session,
            referencia="LOCAL-B",
            codigo_facturacion="AB",
            nombre="Inquilino B",
            nif="22222222B",
            fecha_inicio=date(2026, 2, 1),
        )

        crear_contrato_lista(
            session,
            referencia="FINAL-C",
            codigo_facturacion="FC",
            nombre="Inquilino Final C",
            nif="66666666F",
            fecha_inicio=date(2024, 3, 1),
            fecha_fin=date(2026, 6, 30),
        )
        crear_contrato_lista(
            session,
            referencia="FINAL-A",
            codigo_facturacion="FA",
            nombre="Inquilino Final A",
            nif="44444444D",
            fecha_inicio=date(2024, 1, 1),
            fecha_fin=date(2026, 4, 30),
        )
        crear_contrato_lista(
            session,
            referencia="FINAL-B",
            codigo_facturacion="FB",
            nombre="Inquilino Final B",
            nif="55555555E",
            fecha_inicio=date(2024, 2, 1),
            fecha_fin=date(2026, 5, 31),
        )

        session.commit()

    response = client.get("/contratos/")

    assert response.status_code == 200

    html = response.text

    assert "Vigentes" in html
    assert "Finalizados" in html

    posicion_vigentes = html.index("Vigentes")
    posicion_finalizados = html.index("Finalizados")

    posicion_local_a = html.index("LOCAL-A")
    posicion_local_b = html.index("LOCAL-B")
    posicion_local_c = html.index("LOCAL-C")

    assert (
        posicion_vigentes
        < posicion_local_a
        < posicion_local_b
        < posicion_local_c
        < posicion_finalizados
    )

    posicion_final_a = html.index("FINAL-A")
    posicion_final_b = html.index("FINAL-B")
    posicion_final_c = html.index("FINAL-C")

    assert (
        posicion_finalizados
        < posicion_final_a
        < posicion_final_b
        < posicion_final_c
    )

    assert "Resolución:" in html
    assert "30/04/2026" in html
    assert "31/05/2026" in html
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
            "titular_1_nombre": "Ana Pérez",
            "titular_1_nif": "99999999R",
            "titular_2_nombre": "",
            "titular_2_nif": "",
            "titular_3_nombre": "",
            "titular_3_nif": "",
            "titular_4_nombre": "",
            "titular_4_nif": "",
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
            "metodo_revision": "IPC_NACIONAL",
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
            numero=1,
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
            "titular_1_nombre": "Ana Pérez",
            "titular_1_nif": "99999999R",
            "titular_2_nombre": "",
            "titular_2_nif": "",
            "titular_3_nombre": "",
            "titular_3_nif": "",
            "titular_4_nombre": "",
            "titular_4_nif": "",
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
            "metodo_revision": "IPC_NACIONAL",
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
            numero=1,
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
            "titular_1_nombre": "Ana Pérez",
            "titular_1_nif": "99999999R",
            "titular_2_nombre": "",
            "titular_2_nif": "",
            "titular_3_nombre": "",
            "titular_3_nif": "",
            "titular_4_nombre": "",
            "titular_4_nif": "",
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
            "metodo_revision": "IPC_NACIONAL",
        },
    )

    assert response.status_code == 400
    assert "ajuste de renta ya registrado" in response.text


def test_titulares_formulario_ignora_bloques_vacios() -> None:
    datos = MultiDict(
        {
            "titular_1_nombre": "Ana Pérez",
            "titular_1_nif": "11111111H",
            "titular_2_nombre": "",
            "titular_2_nif": "",
            "titular_3_nombre": "",
            "titular_3_nif": "",
            "titular_4_nombre": "",
            "titular_4_nif": "",
        }
    )

    assert _titulares_formulario(datos) == [
        ("Ana Pérez", "11111111H", 1),
    ]


def test_titulares_formulario_exige_nombre_y_nif() -> None:
    datos = MultiDict(
        {
            "titular_1_nombre": "Ana Pérez",
            "titular_1_nif": "",
        }
    )

    with pytest.raises(
        ValueError,
        match="debe indicar nombre y NIF",
    ):
        _titulares_formulario(datos)


def test_titulares_formulario_rechaza_nif_repetido() -> None:
    datos = MultiDict(
        {
            "titular_1_nombre": "Ana Pérez",
            "titular_1_nif": "11111111H",
            "titular_2_nombre": "Ana Pérez",
            "titular_2_nif": "11111111H",
        }
    )

    with pytest.raises(
        ValueError,
        match="No puede repetirse el mismo NIF",
    ):
        _titulares_formulario(datos)


def test_titulares_formulario_exige_al_menos_un_titular() -> None:
    datos = MultiDict()

    with pytest.raises(
        ValueError,
        match="al menos un titular",
    ):
        _titulares_formulario(datos)


def test_resolver_titulares_reutiliza_inquilino_existente() -> None:
    app = crear_app_test()

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        existente = Inquilino(
            nombre="Ana Pérez",
            nif="11111111H",
        )
        session.add(existente)
        session.commit()

        existente_id = existente.id

    with session_factory() as session:
        titulares = _resolver_titulares(
            session,
            [
                ("Ana Pérez", "11111111H", 1),
            ],
        )

        inquilino, orden = titulares[0]

        assert inquilino.id == existente_id
        assert orden == 1


def test_resolver_titulares_crea_inquilino_nuevo() -> None:
    app = crear_app_test()

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        with session.begin():
            titulares = _resolver_titulares(
                session,
                [
                    ("Luis García", "22222222J", 1),
                ],
            )

            inquilino, orden = titulares[0]

            assert inquilino.nombre == "Luis García"
            assert inquilino.nif == "22222222J"
            assert orden == 1

    with session_factory() as session:
        guardado = session.scalar(
            select(Inquilino).where(
                Inquilino.nif == "22222222J"
            )
        )

        assert guardado is not None
        assert guardado.nombre == "Luis García"


def test_resolver_titulares_rechaza_nombre_distinto_para_nif_existente() -> None:
    app = crear_app_test()

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        session.add(
            Inquilino(
                nombre="Ana Pérez",
                nif="11111111H",
            )
        )
        session.commit()

    with session_factory() as session:
        with pytest.raises(
            ContratoError,
            match="ya pertenece",
        ):
            _resolver_titulares(
                session,
                [
                    ("María López", "11111111H", 1),
                ],
            )


def test_nuevo_contrato_crea_inquilino_desde_formulario() -> None:
    """Comprueba que el alta crea un inquilino inexistente por su NIF."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-NUEVO",
            tipo="L",
            codigo_facturacion="N1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        session.add(inmueble)
        session.commit()

        inmueble_id = inmueble.id

    response = client.post(
        "/contratos/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            "titular_1_nombre": "María López",
            "titular_1_nif": "33333333C",
            "titular_2_nombre": "",
            "titular_2_nif": "",
            "titular_3_nombre": "",
            "titular_3_nif": "",
            "titular_4_nombre": "",
            "titular_4_nif": "",
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
            "metodo_revision": "IPC_NACIONAL",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        inquilino = session.scalar(
            select(Inquilino).where(
                Inquilino.nif == "33333333C"
            )
        )

        assert inquilino is not None
        assert inquilino.nombre == "María López"

        contrato = session.scalar(select(Contrato))

        assert contrato is not None
        assert len(contrato.titulares) == 1
        assert contrato.titulares[0].inquilino_id == inquilino.id
        assert contrato.titulares[0].orden == 1


def test_nuevo_contrato_reutiliza_inquilino_por_nif() -> None:
    """Comprueba que el alta reutiliza un inquilino ya existente."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-EXISTENTE",
            tipo="L",
            codigo_facturacion="E1",
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
            "titular_1_nombre": "Ana Pérez",
            "titular_1_nif": "11111111A",
            "titular_2_nombre": "",
            "titular_2_nif": "",
            "titular_3_nombre": "",
            "titular_3_nif": "",
            "titular_4_nombre": "",
            "titular_4_nif": "",
            "fecha_inicio": "15/09/2026",
            "fecha_vencimiento": "14/09/2031",
            "genera_factura": "on",
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
            "metodo_revision": "IPC_NACIONAL",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        inquilinos = session.scalars(
            select(Inquilino)
        ).all()

        assert len(inquilinos) == 1
        assert inquilinos[0].id == inquilino_id

        contrato = session.scalar(select(Contrato))

        assert contrato is not None
        assert len(contrato.titulares) == 1
        assert contrato.titulares[0].inquilino_id == inquilino_id
        assert contrato.titulares[0].orden == 1


def test_formulario_contrato_muestra_metodos_revision() -> None:
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        session.add(
            _crear_inmueble_prueba(
                referencia="LOCAL-1",
                tipo="L",
                codigo_facturacion="A1",
                descripcion="Local comercial",
                direccion="Dirección",
                poblacion="Pontevedra",
                provincia="Pontevedra",
            )
        )
        session.commit()

    response = client.get("/contratos/nuevo")

    assert response.status_code == 200
    assert "IPC Nacional" in response.text
    assert "IPC Autonómico" in response.text
    assert "IRAV" in response.text
    assert "Fijo" in response.text
    assert 'value="IPC_NACIONAL"' in response.text


def test_formulario_nuevo_contrato_marca_genera_factura_por_defecto() -> None:
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    response = client.get("/contratos/nuevo")

    assert response.status_code == 200
    assert 'name="genera_factura"' in response.text
    assert "checked" in _etiqueta_control(
        response.text,
        "genera_factura",
    )


def test_editar_contrato_que_genera_factura_lo_muestra_en_on() -> None:
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
    assert 'name="genera_factura"' in response.text
    assert "checked" in _etiqueta_control(
        response.text,
        "genera_factura",
    )


def test_editar_contrato_que_no_genera_factura_lo_muestra_en_off() -> None:
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(
            session,
            genera_factura=False,
        )
        contrato_id = contrato.id

    response = client.get(
        f"/contratos/{contrato_id}/editar"
    )

    assert response.status_code == 200
    assert 'name="genera_factura"' in response.text
    assert "checked" not in _etiqueta_control(
        response.text,
        "genera_factura",
    )


def test_editar_contrato_permite_desactivar_genera_factura() -> None:
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(
            session,
            genera_factura=True,
        )

        contrato_id = contrato.id
        inmueble_id = contrato.inmueble_id

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data={
            "inmueble_id": str(inmueble_id),

            **_datos_titulares(
                ("Ana Pérez", "99999999R"),
            ),

            # NO incluimos "genera_factura":
            # checkbox desmarcado = clave ausente

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
            "metodo_revision": "IPC_NACIONAL",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(
            Contrato,
            contrato_id,
        )

        assert contrato is not None
        assert contrato.genera_factura is False




def test_editar_contrato_permite_activar_genera_factura() -> None:
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(
            session,
            genera_factura=False,
        )

        contrato_id = contrato.id
        inmueble_id = contrato.inmueble_id

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data={
            "inmueble_id": str(inmueble_id),

            **_datos_titulares(
                ("Ana Pérez", "99999999R"),
            ),

            "fecha_inicio": "15/09/2026",
            "fecha_vencimiento": "14/09/2031",
            "genera_factura": "on",
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
            "metodo_revision": "IPC_NACIONAL",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(
            Contrato,
            contrato_id,
        )

        assert contrato is not None
        assert contrato.genera_factura is True


def test_crear_contrato_sin_factura_no_exige_datos_facturacion() -> None:
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            tipo="P",
            referencia="PISO-1",
            codigo_facturacion="P1",
            descripcion="Piso",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        session.add(inmueble)
        session.commit()

        inmueble_id = inmueble.id

    response = client.post(
        "/contratos/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            **_datos_titulares(
                ("Ana Pérez", "11111111A"),
            ),
            "fecha_inicio": "15/09/2026",
            "fecha_vencimiento": "14/09/2031",
            # genera_factura ausente → False
            "fecha_inicio_facturacion": "01/10/2026",
            "fianza": "1500,00",
            "iva_porcentaje": "",
            "retencion_porcentaje": "",
            "direccion_facturacion": "",
            "codigo_postal_facturacion": "",
            "poblacion_facturacion": "",
            "provincia_facturacion": "",
            "concepto_factura": "",
            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/10/2027",
            "metodo_revision": "IPC_NACIONAL",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        assert contrato is not None
        assert contrato.genera_factura is False
        assert contrato.iva_porcentaje == 0
        assert contrato.retencion_porcentaje == 0
        assert contrato.direccion_facturacion == ""
        assert contrato.codigo_postal_facturacion == ""
        assert contrato.poblacion_facturacion == ""
        assert contrato.provincia_facturacion == ""
        assert contrato.concepto_factura == ""


def test_editar_contrato_sin_factura_permite_datos_facturacion_vacios() -> None:
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(
            session,
            genera_factura=True,
        )

        contrato_id = contrato.id
        inmueble_id = contrato.inmueble_id

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data={
            "inmueble_id": str(inmueble_id),
            **_datos_titulares(
                ("Ana Pérez", "11111111A"),
            ),

            # genera_factura no se envía:
            # checkbox desmarcado -> False

            "fecha_inicio": "15/09/2026",
            "fecha_vencimiento": "14/09/2031",
            "fecha_inicio_facturacion": "01/10/2026",
            "fianza": "1500,00",

            "iva_porcentaje": "",
            "retencion_porcentaje": "",
            "direccion_facturacion": "",
            "codigo_postal_facturacion": "",
            "poblacion_facturacion": "",
            "provincia_facturacion": "",
            "concepto_factura": "",

            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/10/2027",
            "metodo_revision": "IPC_NACIONAL",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(
            Contrato,
            contrato_id,
        )

        assert contrato is not None
        assert contrato.genera_factura is False
        assert contrato.iva_porcentaje == 0
        assert contrato.retencion_porcentaje == 0
        assert contrato.direccion_facturacion == ""
        assert contrato.codigo_postal_facturacion == ""
        assert contrato.poblacion_facturacion == ""
        assert contrato.provincia_facturacion == ""
        assert contrato.concepto_factura == ""


def test_editar_contrato_sin_factura_permite_guardar_datos_facturacion() -> None:
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(
            session,
            genera_factura=False,
        )

        contrato_id = contrato.id
        inmueble_id = contrato.inmueble_id

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data={
            "inmueble_id": str(inmueble_id),
            **_datos_titulares(
                ("Ana Pérez", "11111111A"),
            ),

            # genera_factura sigue sin enviarse -> False

            "fecha_inicio": "15/09/2026",
            "fecha_vencimiento": "14/09/2031",
            "fecha_inicio_facturacion": "01/10/2026",
            "fianza": "1500,00",

            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección futura",
            "codigo_postal_facturacion": "36001",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Alquiler vivienda",

            "renta_inicial": "1500,00",
            "fecha_primera_revision": "01/10/2027",
            "metodo_revision": "IPC_NACIONAL",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(
            Contrato,
            contrato_id,
        )

        assert contrato is not None
        assert contrato.genera_factura is False

        assert contrato.iva_porcentaje == 2100
        assert contrato.retencion_porcentaje == 1900
        assert contrato.direccion_facturacion == "Dirección futura"
        assert contrato.codigo_postal_facturacion == "36001"
        assert contrato.poblacion_facturacion == "Pontevedra"
        assert contrato.provincia_facturacion == "Pontevedra"
        assert contrato.concepto_factura == "Alquiler vivienda"


def test_formulario_contrato_excluye_inmuebles_subdivididos() -> None:
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble_subdividido = _crear_inmueble_prueba(
            referencia="ALOPEZ-COMUN",
            tipo="T",
            codigo_facturacion="ALC",
            descripcion="Inmueble completo",
            direccion="Avenida López, 1",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        local = _crear_inmueble_prueba(
            referencia="ALOPEZ-LOCAL1",
            tipo="L",
            codigo_facturacion="AL1",
            descripcion="Local arrendable",
            direccion="Avenida López, 1",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=10000,
            inmueble_padre=inmueble_subdividido,
        )

        session.add_all([
            inmueble_subdividido,
            local,
        ])
        session.commit()

    response = client.get("/contratos/nuevo")

    assert response.status_code == 200
    assert "ALOPEZ-LOCAL1" in response.text
    assert "ALOPEZ-COMUN" not in response.text


def test_nuevo_contrato_muestra_error_si_nif_tiene_otro_nombre() -> None:
    """Conserva el formulario si el NIF pertenece a otro nombre."""
    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    # Preparamos un inmueble y un inquilino ya existente.
    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        inquilino = Inquilino(
            nombre="Gómez y Pérez, S.L.",
            nif="B88777666",
        )

        session.add_all([inmueble, inquilino])
        session.commit()

        inmueble_id = inmueble.id

    # Enviamos el mismo NIF con un nombre diferente.
    response = client.post(
        "/contratos/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            **_datos_titulares(
                (
                    "GOMEZ Y PEREZ, S.L.",
                    "B88777666",
                ),
            ),
            "fecha_inicio": "01/09/2026",
            "fecha_vencimiento": "31/08/2031",
            "genera_factura": "on",
            "fecha_inicio_facturacion": "01/09/2026",
            "fianza": "1000,00",
            "iva_porcentaje": "21,00",
            "retencion_porcentaje": "19,00",
            "direccion_facturacion": "Dirección",
            "codigo_postal_facturacion": "36001",
            "poblacion_facturacion": "Pontevedra",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Alquiler local",
            "renta_inicial": "1000,00",
            "fecha_primera_revision": "01/09/2027",
            "metodo_revision": "IPC_NACIONAL",
        },
    )

    assert response.status_code == 400
    assert (
        "El NIF B88777666 ya pertenece a "
        "&#39;Gómez y Pérez, S.L.&#39;"
        in response.text
    )
    assert 'name="metodo_revision"' in response.text
    assert 'value="IPC_NACIONAL"' in response.text

    # El intento fallido no debe crear ningún contrato.
    with session_factory() as session:
        assert session.scalar(
            select(Contrato)
        ) is None


def test_nuevo_contrato_rechaza_nombre_distinto_para_nif() -> None:
    """Muestra el error de titulares sin abandonar el formulario."""
    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(
        inmueble_id
    )
    datos["titular_1_nombre"] = "ANA PEREZ"

    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 400
    assert "ya pertenece a" in response.text
    assert "Ana Pérez" in response.text
    assert 'name="metodo_revision"' in response.text

    with session_factory() as session:
        assert session.scalar(
            select(Contrato)
        ) is None


def test_nuevo_contrato_rechaza_metodo_revision_vacio() -> None:
    """Muestra el error producido al crear la revisión inicial."""
    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(
        inmueble_id
    )
    datos["metodo_revision"] = ""

    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 400
    assert (
        "La revisión debe indicar un método de actualización."
        in response.text
    )
    assert 'name="metodo_revision"' in response.text

    with session_factory() as session:
        assert session.scalar(
            select(Contrato)
        ) is None


def test_nuevo_contrato_rechaza_renta_inicial_negativa() -> None:
    """Captura el error de la renta creada dentro del contrato."""
    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(
        inmueble_id
    )
    datos["renta_inicial"] = "-1,00"

    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 400
    assert (
        "El importe de la renta no puede ser negativo."
        in response.text
    )
    assert 'name="metodo_revision"' in response.text

    with session_factory() as session:
        assert session.scalar(
            select(Contrato)
        ) is None


def test_nuevo_contrato_rechaza_inmueble_inexistente() -> None:
    """Muestra el error si el inmueble dejó de existir."""
    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(
        inmueble_id
    )
    datos["inmueble_id"] = "999999"

    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 400
    assert (
        "El inmueble seleccionado no existe."
        in response.text
    )
    assert 'name="metodo_revision"' in response.text

    with session_factory() as session:
        assert session.scalar(
            select(Contrato)
        ) is None


def test_nuevo_contrato_rechaza_contrato_solapado() -> None:
    """Muestra el error y conserva únicamente el primer contrato."""
    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(
        inmueble_id
    )

    # Creamos correctamente el primer contrato.
    primera_respuesta = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert primera_respuesta.status_code == 302

    # Intentamos crear otro contrato para el mismo período.
    segunda_respuesta = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert segunda_respuesta.status_code == 400
    assert (
        "El inmueble ya tiene un contrato que se solapa"
        in segunda_respuesta.text
    )
    assert (
        'name="metodo_revision"'
        in segunda_respuesta.text
    )

    with session_factory() as session:
        assert len(
            session.scalars(
                select(Contrato)
            ).all()
        ) == 1


def test_nuevo_contrato_captura_campo_ausente() -> None:
    """Un campo ausente no debe producir un error interno."""
    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(
        inmueble_id
    )
    del datos["metodo_revision"]

    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 400
    assert 'name="metodo_revision"' in response.text

    with session_factory() as session:
        assert session.scalar(
            select(Contrato)
        ) is None


@pytest.mark.parametrize(
    ("campo", "mensaje"),
    [
        (
            "direccion_facturacion",
            "La dirección de facturación es obligatoria.",
        ),
        (
            "poblacion_facturacion",
            "La población de facturación es obligatoria.",
        ),
        (
            "provincia_facturacion",
            "La provincia de facturación es obligatoria.",
        ),
        (
            "concepto_factura",
            "El concepto de factura es obligatorio.",
        ),
    ],
)
def test_nuevo_contrato_exige_datos_facturacion(
    campo: str,
    mensaje: str,
) -> None:
    """Comprueba los datos obligatorios cuando se genera factura."""
    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(
        inmueble_id
    )
    datos[campo] = ""

    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 400
    assert mensaje in response.text
    assert 'name="metodo_revision"' in response.text

    with session_factory() as session:
        assert session.scalar(
            select(Contrato)
        ) is None


def test_seleccionar_tipo_anexo_muestra_carencia() -> None:
    """Comprueba que la selección de anexos ofrece crear una carencia."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.get(
        f"/contratos/{contrato_id}/anexo"
    )

    assert response.status_code == 200
    assert "Período de carencia" in response.text


def test_formulario_anexo_carencia_responde() -> None:
    """Comprueba que puede abrirse el formulario de carencia."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.get(
        f"/contratos/{contrato_id}/anexo/carencia"
    )

    assert response.status_code == 200
    assert "Período de carencia" in response.text
    assert 'name="fecha"' in response.text
    assert 'name="fecha_desde"' in response.text
    assert 'name="fecha_hasta"' in response.text
    assert 'name="descripcion"' in response.text


def test_crear_anexo_carencia_desde_formulario() -> None:
    """Comprueba que el formulario persiste un anexo de carencia."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.post(
        f"/contratos/{contrato_id}/anexo/carencia",
        data={
            "numero": "1",
            "fecha": "15/10/2026",
            "fecha_desde": "01/11/2026",
            "fecha_hasta": "31/01/2027",
            "descripcion": "Carencia de tres meses",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        assert len(contrato.anexos) == 1

        anexo = contrato.anexos[0]

        assert anexo.tipo == "CARENCIA"
        assert anexo.fecha == date(2026, 10, 15)
        assert anexo.fecha_desde == date(2026, 11, 1)
        assert anexo.fecha_hasta == date(2027, 1, 31)
        assert anexo.descripcion == "Carencia de tres meses"


def test_crear_anexo_carencia_muestra_error_de_validacion() -> None:
    """Comprueba que los errores de dominio vuelven al formulario."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    response = client.post(
        f"/contratos/{contrato_id}/anexo/carencia",
        data={
            "fecha": "15/10/2026",
            "fecha_desde": "02/11/2026",
            "fecha_hasta": "31/01/2027",
            "descripcion": "",
        },
    )

    assert response.status_code == 400
    assert "primer día del mes" in response.text
    assert 'value="02/11/2026"' in response.text
    assert 'value="31/01/2027"' in response.text


def test_historico_anexos_muestra_carencia() -> None:
    """Comprueba que el histórico muestra el período de carencia."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)

        anexo = crear_anexo_carencia(
            contrato=contrato,
            numero=1,
            fecha=date(2026, 10, 15),
            fecha_desde=date(2026, 11, 1),
            fecha_hasta=date(2027, 1, 31),
            descripcion="Carencia de tres meses",
        )

        session.add(anexo)
        session.commit()

        contrato_id = contrato.id

    response = client.get(
        f"/contratos/{contrato_id}/anexos"
    )

    assert response.status_code == 200
    assert "Carencia" in response.text
    assert "01/11/2026" in response.text
    assert "31/01/2027" in response.text
    assert "Carencia de tres meses" in response.text


def test_anexo_rechaza_numero_duplicado() -> None:
    """No permite repetir el número de anexo de un contrato."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)
        contrato_id = contrato.id

    # Primer anexo: número 1.
    response = client.post(
        f"/contratos/{contrato_id}/anexo/prorroga",
        data={
            "numero": "1",
            "fecha": "01/06/2031",
            "nueva_fecha_vencimiento": "14/09/2036",
            "descripcion": "Primera prórroga",
        },
    )

    assert response.status_code == 302

    # Segundo anexo: mismo número, aunque con otras fechas.
    response = client.post(
        f"/contratos/{contrato_id}/anexo/prorroga",
        data={
            "numero": "1",
            "fecha": "01/06/2032",
            "nueva_fecha_vencimiento": "14/09/2041",
            "descripcion": "Segunda prórroga",
        },
    )

    assert response.status_code == 400
    assert (
        "Ya existe un anexo con ese número"
        in response.text
    )

    # El intento fallido no debe alterar el contrato.
    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        assert len(contrato.anexos) == 1

        anexo = contrato.anexos[0]

        assert anexo.numero == 1
        assert anexo.descripcion == "Primera prórroga"

        assert contrato.fecha_vencimiento == date(
            2036, 9, 14
        )


@pytest.mark.parametrize(
    "genera_factura, fecha_revision, metodo, numero_revisiones",
    [
        pytest.param(
            True, "01/10/2027", "IPC_NACIONAL", 1,
            id="con-factura-y-revision",
        ),
        pytest.param(
            True, "", "", None,
            id="con-factura-sin-revision",
        ),
        pytest.param(
            False, "", "", 0,
            id="sin-factura-sin-revision",
        ),
        pytest.param(
            False, "01/10/2027", "IPC_NACIONAL", 1,
            id="sin-factura-con-revision",
        ),
        pytest.param(
            False, "01/10/2027", "", None,
            id="solo-fecha",
        ),
        pytest.param(
            False, "", "IPC_NACIONAL", None,
            id="solo-metodo",
        ),
    ],
)
def test_alta_contrato_opcionalidad_primera_revision(
    genera_factura,
    fecha_revision,
    metodo,
    numero_revisiones,
) -> None:
    """Comprueba la opcionalidad de la revisión desde el formulario."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)

    if not genera_factura:
        datos.pop("genera_factura")

    datos["fecha_primera_revision"] = fecha_revision
    datos["metodo_revision"] = metodo

    # El usuario cumplimenta el formulario de alta
    # e intenta guardar el nuevo contrato.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    if numero_revisiones is None:
        assert response.status_code == 400

        # Un alta rechazada no debe dejar registros
        # contractuales parcialmente creados.
        with session_factory() as session:
            assert session.scalar(select(Contrato)) is None
            assert session.scalar(select(RentaContrato)) is None
            assert session.scalar(select(RevisionRenta)) is None

        return

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        assert contrato is not None
        assert contrato.genera_factura is genera_factura

        # El contrato conserva su renta inicial.
        assert len(contrato.rentas) == 1
        assert contrato.rentas[0].importe == 150000

        # La primera revisión es opcional cuando
        # el contrato no genera factura.
        assert (
            len(contrato.revisiones_renta)
            == numero_revisiones
        )

        if numero_revisiones == 1:
            revision = contrato.revisiones_renta[0]

            assert revision.fecha_prevista == date(2027, 10, 1)
            assert revision.metodo == metodo
            assert revision.estado == "PENDIENTE"


@pytest.mark.parametrize(
    (
        "revision_existente, genera_factura, "
        "fecha_revision, metodo, resultado"
    ),
    [
        pytest.param(
            False, False, "", "", 302,
            id="conservar-sin-revision",
        ),
        pytest.param(
            False, False, "01/11/2027", "IPC_NACIONAL", 302,
            id="anadir-primera-revision",
        ),
        pytest.param(
            False, True, "", "", 400,
            id="activar-factura-sin-revision",
        ),
        pytest.param(
            False, True, "01/11/2027", "IPC_NACIONAL", 302,
            id="activar-factura-con-revision",
        ),
        pytest.param(
            True, False, "01/11/2027", "IPC_NACIONAL", 302,
            id="modificar-revision-existente",
        ),
        pytest.param(
            True, False, "", "", 400,
            id="no-eliminar-revision-existente",
        ),
        pytest.param(
            False, False, "01/11/2027", "", 400,
            id="solo-fecha",
        ),
        pytest.param(
            False, False, "", "IPC_NACIONAL", 400,
            id="solo-metodo",
        ),
    ],
)
def test_editar_contrato_opcionalidad_primera_revision(
    revision_existente,
    genera_factura,
    fecha_revision,
    metodo,
    resultado,
) -> None:
    """Permite editar contratos con o sin primera revisión."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)
    datos.pop("genera_factura")

    if not revision_existente:
        datos["fecha_primera_revision"] = ""
        datos["metodo_revision"] = ""

    # El usuario crea inicialmente un contrato sin factura,
    # con o sin primera revisión de renta.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        contrato_id = contrato.id

        revision_id = (
            contrato.revisiones_renta[0].id
            if revision_existente
            else None
        )

    url_editar = f"/contratos/{contrato_id}/editar"

    # El usuario abre el formulario de edición.
    response = client.get(url_editar)

    assert response.status_code == 200

    # Modifica la fianza y los datos de revisión.
    datos["fianza"] = "1600,00"
    datos["fecha_primera_revision"] = fecha_revision
    datos["metodo_revision"] = metodo

    if genera_factura:
        datos["genera_factura"] = "on"

    # El usuario intenta guardar las modificaciones.
    response = client.post(
        url_editar,
        data=datos,
    )

    assert response.status_code == resultado

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        if resultado == 400:
            # Una modificación rechazada no debe alterar
            # ningún dato del contrato ni de sus revisiones.
            assert contrato.genera_factura is False
            assert contrato.fianza == 150000

            assert len(contrato.revisiones_renta) == (
                1 if revision_existente else 0
            )

            if revision_existente:
                revision = contrato.revisiones_renta[0]

                assert revision.id == revision_id
                assert revision.fecha_prevista == date(
                    2027, 10, 1
                )
                assert revision.metodo == "IPC_NACIONAL"

            return

        # Las modificaciones válidas quedan guardadas.
        assert contrato.genera_factura is genera_factura
        assert contrato.fianza == 160000

        assert len(contrato.revisiones_renta) == (
            1 if fecha_revision else 0
        )

        if fecha_revision:
            revision = contrato.revisiones_renta[0]

            assert revision.fecha_prevista == date(
                2027, 11, 1
            )
            assert revision.metodo == metodo
            assert revision.estado == "PENDIENTE"

            # Modificar una revisión existente no supone
            # eliminarla y crear otra distinta.
            if revision_existente:
                assert revision.id == revision_id


@pytest.mark.parametrize(
    "con_historico",
    [
        pytest.param(False, id="sin-historico"),
        pytest.param(True, id="con-historico"),
    ],
)
@pytest.mark.parametrize(
    "modificacion",
    [
        "inmueble",
        "sustituir-titular",
        "anadir-titular",
        "eliminar-titular",
        "reordenar-titulares",
        "conservar-identidad",
    ],
)
def test_editar_contrato_protege_identidad(
    con_historico,
    modificacion,
) -> None:
    """Protege la identidad contractual desde la edición."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)

    datos.update(
        _datos_titulares(
            ("Ana Pérez", "11111111A"),
            ("Luis García", "22222222B"),
        )
    )

    # El usuario crea un contrato con dos titulares.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        # Se prepara otro inmueble al que podría
        # trasladarse el contrato.
        otro_inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-2",
            tipo="L",
            codigo_facturacion="A2",
            descripcion="Otro local",
            direccion="Otra dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        session.add(otro_inmueble)

        if con_historico:
            # El usuario formaliza una prórroga
            # del contrato mediante un anexo.
            anexo = crear_anexo_prorroga(
                contrato=contrato,
                numero=1,
                fecha=date(2030, 6, 1),
                nueva_fecha_vencimiento=date(2036, 9, 14),
                descripcion="Prórroga",
            )

            session.add(anexo)

            datos["fecha_vencimiento"] = "14/09/2036"

        session.commit()

        contrato_id = contrato.id
        otro_inmueble_id = otro_inmueble.id

    titulares_esperados = [
        "11111111A",
        "22222222B",
    ]

    inmueble_esperado = inmueble_id

    # El usuario modifica la identidad del contrato.
    if modificacion == "inmueble":
        datos["inmueble_id"] = str(otro_inmueble_id)
        inmueble_esperado = otro_inmueble_id

    elif modificacion == "sustituir-titular":
        datos.update(
            _datos_titulares(
                ("Ana Pérez", "11111111A"),
                ("María López", "33333333C"),
            )
        )

        titulares_esperados = [
            "11111111A",
            "33333333C",
        ]

    elif modificacion == "anadir-titular":
        datos.update(
            _datos_titulares(
                ("Ana Pérez", "11111111A"),
                ("Luis García", "22222222B"),
                ("María López", "33333333C"),
            )
        )

        titulares_esperados = [
            "11111111A",
            "22222222B",
            "33333333C",
        ]

    elif modificacion == "eliminar-titular":
        datos.update(
            _datos_titulares(
                ("Ana Pérez", "11111111A"),
            )
        )

        titulares_esperados = ["11111111A"]

    elif modificacion == "reordenar-titulares":
        datos.update(
            _datos_titulares(
                ("Luis García", "22222222B"),
                ("Ana Pérez", "11111111A"),
            )
        )

        titulares_esperados = [
            "22222222B",
            "11111111A",
        ]

    # Aprovecha también para corregir la fianza.
    datos["fianza"] = "1600,00"

    debe_rechazarse = (
        con_historico
        and modificacion not in (
            "reordenar-titulares",
            "conservar-identidad",
        )
    )

    # El usuario intenta guardar las modificaciones.
    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data=datos,
    )

    if debe_rechazarse:
        assert response.status_code == 400

        if modificacion == "inmueble":
            assert (
                "No puede modificarse el inmueble"
                in response.text
            )
        else:
            assert (
                "No pueden modificarse los titulares"
                in response.text
            )

    else:
        assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        titulares = sorted(
            contrato.titulares,
            key=lambda titular: titular.orden,
        )

        nifs = [
            titular.inquilino.nif
            for titular in titulares
        ]

        if debe_rechazarse:
            # La operación rechazada no modifica
            # el inmueble, los titulares ni la fianza.
            assert contrato.inmueble_id == inmueble_id

            assert nifs == [
                "11111111A",
                "22222222B",
            ]

            assert contrato.fianza == 150000

            # Tampoco deja un nuevo inquilino creado
            # como consecuencia del intento rechazado.
            assert session.scalar(
                select(Inquilino).where(
                    Inquilino.nif == "33333333C"
                )
            ) is None

        else:
            # Las modificaciones permitidas
            # quedan correctamente persistidas.
            assert contrato.inmueble_id == inmueble_esperado
            assert nifs == titulares_esperados
            assert contrato.fianza == 160000

        # El histórico contractual permanece intacto.
        assert len(contrato.anexos) == (
            1 if con_historico else 0
        )

        if con_historico:
            assert contrato.anexos[0].tipo == "PRORROGA"

            assert (
                contrato.fecha_vencimiento
                == date(2036, 9, 14)
            )


@pytest.mark.parametrize(
    "historico",
    [
        "sin-historico",
        "renta-posterior",
        "revision-posterior",
        "revision-aplicada",
        "revision-no-aplicada",
        "ajuste",
        "anexo",
    ],
)
@pytest.mark.parametrize(
    "modificar_inicio",
    [
        pytest.param(False, id="conservar-inicio"),
        pytest.param(True, id="modificar-inicio"),
    ],
)
def test_editar_contrato_protege_fecha_inicio(
    historico,
    modificar_inicio,
) -> None:
    """Impide modificar el inicio cuando existe histórico."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)

    # El usuario crea un contrato con renta inicial
    # y primera revisión pendiente.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        # Se prepara el histórico correspondiente
        # al caso de prueba.
        if historico == "renta-posterior":
            contrato.rentas.append(
                RentaContrato(
                    fecha_desde=date(2028, 6, 1),
                    importe=175000,
                )
            )

        elif historico == "revision-posterior":
            contrato.revisiones_renta.append(
                RevisionRenta(
                    fecha_prevista=date(2028, 10, 1),
                    metodo="IPC_NACIONAL",
                    estado="PENDIENTE",
                )
            )

        elif historico == "revision-aplicada":
            revision = contrato.revisiones_renta[0]
            revision.estado = "APLICADA"
            revision.fecha_resolucion = date(2027, 10, 1)
            revision.porcentaje_aplicado = 0

        elif historico == "revision-no-aplicada":
            revision = contrato.revisiones_renta[0]
            revision.estado = "NO_APLICADA"
            revision.fecha_resolucion = date(2027, 10, 1)

        elif historico == "ajuste":
            contrato.ajustes_renta.append(
                AjusteRenta(
                    fecha_desde=date(2028, 6, 1),
                    fecha_hasta=date(2028, 8, 31),
                    tipo="IMPORTE_FIJO",
                    valor=120000,
                )
            )

        elif historico == "anexo":
            anexo = crear_anexo_prorroga(
                contrato=contrato,
                numero=1,
                fecha=date(2030, 6, 1),
                nueva_fecha_vencimiento=date(2036, 9, 14),
                descripcion="Prórroga",
            )

            session.add(anexo)

            datos["fecha_vencimiento"] = "14/09/2036"

        session.commit()
        contrato_id = contrato.id

    # El usuario intenta adelantar la fecha de inicio.
    # La nueva fecha no contradice cronológicamente
    # ninguno de los registros históricos.
    if modificar_inicio:
        datos["fecha_inicio"] = "01/09/2026"

    # También intenta corregir la fianza.
    datos["fianza"] = "1600,00"

    debe_rechazarse = (
        modificar_inicio
        and historico != "sin-historico"
    )

    # El usuario guarda el formulario de edición.
    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data=datos,
    )

    if debe_rechazarse:
        assert response.status_code == 400
        assert (
            "No puede modificarse la fecha de inicio"
            in response.text
        )

    else:
        assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        renta_inicial = min(
            contrato.rentas,
            key=lambda renta: renta.fecha_desde,
        )

        if debe_rechazarse:
            # La operación rechazada no modifica
            # el contrato ni su renta inicial.
            assert contrato.fecha_inicio == date(
                2026, 9, 15
            )
            assert renta_inicial.fecha_desde == date(
                2026, 9, 15
            )
            assert contrato.fianza == 150000

        else:
            fecha_esperada = (
                date(2026, 9, 1)
                if modificar_inicio
                else date(2026, 9, 15)
            )

            assert contrato.fecha_inicio == fecha_esperada
            assert renta_inicial.fecha_desde == fecha_esperada
            assert contrato.fianza == 160000


@pytest.mark.parametrize(
    "operacion",
    [
        "editar",
        "finalizar",
    ],
)
@pytest.mark.parametrize(
    "historico, debe_rechazarse",
    [
        pytest.param(
            "sin-historico", False,
            id="sin-historico",
        ),
        pytest.param(
            "renta-posterior", True,
            id="renta-posterior",
        ),
        pytest.param(
            "revision-pendiente", False,
            id="revision-pendiente",
        ),
        pytest.param(
            "revision-aplicada", True,
            id="revision-aplicada",
        ),
        pytest.param(
            "revision-no-aplicada", True,
            id="revision-no-aplicada",
        ),
        pytest.param(
            "ajuste-posterior", True,
            id="ajuste-posterior",
        ),
        pytest.param(
            "ajuste-en-limite", False,
            id="ajuste-en-limite",
        ),
        pytest.param(
            "anexo-posterior", True,
            id="anexo-posterior",
        ),
        pytest.param(
            "prorroga-anterior", False,
            id="prorroga-anterior",
        ),
    ],
)
def test_fecha_fin_respeta_historico_contractual(
    operacion,
    historico,
    debe_rechazarse,
) -> None:
    """Aplica las mismas restricciones al editar y finalizar."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)

    # El usuario crea un contrato con renta inicial
    # y primera revisión pendiente.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        # Se prepara el histórico contractual
        # correspondiente a cada caso de prueba.
        if historico == "renta-posterior":
            contrato.rentas.append(
                RentaContrato(
                    fecha_desde=date(2028, 10, 1),
                    importe=175000,
                )
            )

        elif historico in (
            "revision-pendiente",
            "revision-aplicada",
            "revision-no-aplicada",
        ):
            revision = RevisionRenta(
                fecha_prevista=date(2028, 10, 1),
                metodo="IPC_NACIONAL",
                estado="PENDIENTE",
            )

            if historico == "revision-aplicada":
                revision.estado = "APLICADA"
                revision.fecha_resolucion = date(
                    2028, 10, 1
                )
                revision.porcentaje_aplicado = 0

            elif historico == "revision-no-aplicada":
                revision.estado = "NO_APLICADA"
                revision.fecha_resolucion = date(
                    2028, 10, 1
                )

            contrato.revisiones_renta.append(revision)

        elif historico in (
            "ajuste-posterior",
            "ajuste-en-limite",
        ):
            fecha_hasta = (
                date(2028, 10, 31)
                if historico == "ajuste-posterior"
                else date(2028, 8, 31)
            )

            contrato.ajustes_renta.append(
                AjusteRenta(
                    fecha_desde=date(2028, 6, 1),
                    fecha_hasta=fecha_hasta,
                    tipo="IMPORTE_FIJO",
                    valor=120000,
                )
            )

        elif historico in (
            "anexo-posterior",
            "prorroga-anterior",
        ):
            fecha_anexo = (
                date(2028, 10, 1)
                if historico == "anexo-posterior"
                else date(2028, 6, 1)
            )

            anexo = crear_anexo_prorroga(
                contrato=contrato,
                numero=1,
                fecha=fecha_anexo,
                nueva_fecha_vencimiento=date(
                    2036, 9, 14
                ),
                descripcion="Prórroga",
            )

            session.add(anexo)

            datos["fecha_vencimiento"] = "14/09/2036"

        session.commit()
        contrato_id = contrato.id

    # El usuario intenta establecer como fecha
    # de finalización el 31 de agosto de 2028.
    fecha_fin = "31/08/2028"

    if operacion == "editar":
        datos["fecha_fin"] = fecha_fin

        response = client.post(
            f"/contratos/{contrato_id}/editar",
            data=datos,
        )

    else:
        response = client.post(
            f"/contratos/{contrato_id}/finalizar",
            data={
                "fecha_fin": fecha_fin,
            },
        )

    if debe_rechazarse:
        assert response.status_code == 400
    else:
        assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        # Una finalización rechazada no debe
        # modificar la fecha de fin del contrato.
        if debe_rechazarse:
            assert contrato.fecha_fin is None
        else:
            assert contrato.fecha_fin == date(
                2028, 8, 31
            )


@pytest.mark.parametrize(
    "operacion",
    [
        "editar",
        "finalizar",
    ],
)
@pytest.mark.parametrize(
    "fecha_fin, resultado",
    [
        pytest.param(
            "30/09/2026", 400,
            id="antes-del-periodo",
        ),
        pytest.param(
            "01/10/2026", 302,
            id="inicio-del-periodo",
        ),
        pytest.param(
            "15/10/2026", 302,
            id="durante-el-periodo",
        ),
        pytest.param(
            "31/10/2026", 302,
            id="fin-del-periodo",
        ),
        pytest.param(
            "15/11/2026", 302,
            id="despues-del-periodo",
        ),
    ],
)
def test_fecha_fin_respeta_alquiler_sin_factura(
    operacion,
    fecha_fin,
    resultado,
) -> None:
    """La finalización debe respetar los alquileres contabilizados."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)
    datos.pop("genera_factura")

    # El usuario crea un contrato sin factura.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    categorias = {
        "ING_ALQUILERES": CategoriaContable(
            codigo="ING_ALQUILERES",
            naturaleza="INGRESO",
            nombre="Alquileres",
            activa=True,
            subcategorias=(),
        ),
    }

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        # El usuario contabiliza el 2 de noviembre
        # el alquiler correspondiente a octubre.
        apunte, movimiento = (
            contabilizar_ingreso_sin_factura(
                contrato=contrato,
                periodo=date(2026, 10, 1),
                fecha=date(2026, 11, 2),
                categorias=categorias,
            )
        )

        session.add_all([apunte, movimiento])
        session.commit()

        contrato_id = contrato.id
        apunte_id = apunte.id
        movimiento_id = movimiento.id

    # El usuario intenta establecer la fecha
    # de finalización desde una de las dos operaciones.
    if operacion == "editar":
        datos["fecha_fin"] = fecha_fin

        response = client.post(
            f"/contratos/{contrato_id}/editar",
            data=datos,
        )

    else:
        response = client.post(
            f"/contratos/{contrato_id}/finalizar",
            data={
                "fecha_fin": fecha_fin,
            },
        )

    assert response.status_code == resultado

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        if resultado == 400:
            assert contrato.fecha_fin is None
        else:
            dia, mes, anio = map(
                int,
                fecha_fin.split("/"),
            )

            assert contrato.fecha_fin == date(
                anio, mes, dia
            )

        # La operación no modifica el alquiler
        # previamente contabilizado.
        assert len(contrato.movimientos_previstos) == 1

        movimiento = contrato.movimientos_previstos[0]

        assert movimiento.id == movimiento_id
        assert movimiento.apunte.id == apunte_id

        assert movimiento.apunte.periodo_desde == date(
            2026, 10, 1
        )
        assert movimiento.apunte.periodo_hasta == date(
            2026, 10, 31
        )
        assert movimiento.apunte.fecha == date(
            2026, 11, 2
        )
        assert movimiento.apunte.total == 150000


@pytest.mark.parametrize(
    "historico",
    [
        "sin-historico",
        "anexo",
        "revision-resuelta",
        "factura",
        "alquiler-sin-factura",
    ],
)
@pytest.mark.parametrize(
    "modificar_inicio_facturacion",
    [
        pytest.param(False, id="conservar-inicio"),
        pytest.param(True, id="modificar-inicio"),
    ],
)
def test_editar_contrato_protege_inicio_facturacion(
    historico,
    modificar_inicio_facturacion,
) -> None:
    """Protege el inicio de facturación si hay alquileres registrados."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)

    if historico == "alquiler-sin-factura":
        datos.pop("genera_factura")

    # El usuario crea un contrato.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        # Se prepara el histórico correspondiente
        # al caso de prueba.
        if historico == "anexo":
            anexo = crear_anexo_prorroga(
                contrato=contrato,
                numero=1,
                fecha=date(2030, 6, 1),
                nueva_fecha_vencimiento=date(
                    2036, 9, 14
                ),
                descripcion="Prórroga",
            )

            session.add(anexo)

            datos["fecha_vencimiento"] = "14/09/2036"

        elif historico == "revision-resuelta":
            revision = contrato.revisiones_renta[0]
            revision.estado = "NO_APLICADA"
            revision.fecha_resolucion = date(
                2027, 10, 1
            )

        elif historico == "factura":
            # El usuario registra la factura
            # correspondiente a diciembre.
            factura = crear_factura(
                contrato=contrato,
                periodo=date(2026, 12, 1),
                fecha_emision=date(2026, 12, 1),
            )

            session.add(factura)

        elif historico == "alquiler-sin-factura":
            categorias = {
                "ING_ALQUILERES": CategoriaContable(
                    codigo="ING_ALQUILERES",
                    naturaleza="INGRESO",
                    nombre="Alquileres",
                    activa=True,
                    subcategorias=(),
                ),
            }

            # El usuario contabiliza el alquiler
            # de diciembre sin emitir factura.
            apunte, movimiento = (
                contabilizar_ingreso_sin_factura(
                    contrato=contrato,
                    periodo=date(2026, 12, 1),
                    fecha=date(2026, 12, 1),
                    categorias=categorias,
                )
            )

            session.add_all([apunte, movimiento])

        session.commit()
        contrato_id = contrato.id

    # El usuario intenta retrasar el inicio
    # de facturación de octubre a noviembre.
    if modificar_inicio_facturacion:
        datos["fecha_inicio_facturacion"] = "01/11/2026"

    # También corrige la fianza.
    datos["fianza"] = "1600,00"

    debe_rechazarse = (
        modificar_inicio_facturacion
        and historico in (
            "factura",
            "alquiler-sin-factura",
        )
    )

    # El usuario guarda las modificaciones.
    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data=datos,
    )

    if debe_rechazarse:
        assert response.status_code == 400
        assert (
            "No puede modificarse la fecha de inicio de facturación"
            in response.text
        )

    else:
        assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        if debe_rechazarse:
            # Una modificación rechazada no altera
            # los datos originales del contrato.
            assert (
                contrato.fecha_inicio_facturacion
                == date(2026, 10, 1)
            )
            assert contrato.fianza == 150000

        else:
            fecha_esperada = (
                date(2026, 11, 1)
                if modificar_inicio_facturacion
                else date(2026, 10, 1)
            )

            assert (
                contrato.fecha_inicio_facturacion
                == fecha_esperada
            )
            assert contrato.fianza == 160000


@pytest.mark.parametrize(
    "historico, renta_protegida",
    [
        ("sin-historico", False),
        ("prorroga", False),
        ("renta-posterior", True),
        ("revision-aplicada", True),
        ("revision-no-aplicada", True),
        ("cambio-renta-temporal", True),
        ("factura", True),
        ("alquiler-sin-factura", True),
    ],
)
@pytest.mark.parametrize(
    "modificar_renta",
    [
        pytest.param(False, id="conservar-renta"),
        pytest.param(True, id="modificar-renta"),
    ],
)
def test_editar_contrato_protege_renta_inicial(
    historico,
    renta_protegida,
    modificar_renta,
) -> None:
    """Protege la renta inicial cuando existe histórico relevante."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)

    if historico == "alquiler-sin-factura":
        datos.pop("genera_factura")

    # El usuario crea un contrato con una renta inicial
    # de 1500 euros y una primera revisión pendiente.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        # Se prepara el histórico correspondiente
        # al caso de prueba.
        if historico == "prorroga":
            anexo = crear_anexo_prorroga(
                contrato=contrato,
                numero=1,
                fecha=date(2030, 6, 1),
                nueva_fecha_vencimiento=date(
                    2036, 9, 14
                ),
                descripcion="Prórroga",
            )

            session.add(anexo)

            datos["fecha_vencimiento"] = "14/09/2036"

        elif historico == "renta-posterior":
            contrato.rentas.append(
                RentaContrato(
                    fecha_desde=date(2028, 6, 1),
                    importe=175000,
                )
            )

        elif historico == "revision-aplicada":
            revision = contrato.revisiones_renta[0]
            revision.estado = "APLICADA"
            revision.fecha_resolucion = date(
                2027, 10, 1
            )
            revision.porcentaje_aplicado = 0

        elif historico == "revision-no-aplicada":
            revision = contrato.revisiones_renta[0]
            revision.estado = "NO_APLICADA"
            revision.fecha_resolucion = date(
                2027, 10, 1
            )

        elif historico == "cambio-renta-temporal":
            anexo, ajuste = crear_anexo_renta_temporal(
                contrato=contrato,
                numero=1,
                fecha=date(2028, 5, 20),
                fecha_desde=date(2028, 6, 1),
                fecha_hasta=date(2028, 8, 31),
                tipo="IMPORTE_FIJO",
                valor=120000,
                descripcion="Reducción temporal",
            )

            session.add_all([anexo, ajuste])

        elif historico == "factura":
            # El usuario registra una factura de alquiler.
            factura = crear_factura(
                contrato=contrato,
                periodo=date(2026, 12, 1),
                fecha_emision=date(2026, 12, 1),
            )

            session.add(factura)

        elif historico == "alquiler-sin-factura":
            categorias = {
                "ING_ALQUILERES": CategoriaContable(
                    codigo="ING_ALQUILERES",
                    naturaleza="INGRESO",
                    nombre="Alquileres",
                    activa=True,
                    subcategorias=(),
                ),
            }

            # El usuario contabiliza un alquiler sin factura.
            apunte, movimiento = (
                contabilizar_ingreso_sin_factura(
                    contrato=contrato,
                    periodo=date(2026, 12, 1),
                    fecha=date(2026, 12, 1),
                    categorias=categorias,
                )
            )

            session.add_all([apunte, movimiento])

        session.commit()
        contrato_id = contrato.id

    # El usuario intenta corregir la renta inicial.
    if modificar_renta:
        datos["renta_inicial"] = "1600,00"

    # También modifica otro campo del contrato.
    datos["fianza"] = "1700,00"

    debe_rechazarse = (
        renta_protegida and modificar_renta
    )

    # El usuario guarda el formulario de edición.
    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data=datos,
    )

    if debe_rechazarse:
        assert response.status_code == 400
        assert (
            "No puede modificarse la renta inicial"
            in response.text
        )

    else:
        assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        renta_inicial = min(
            contrato.rentas,
            key=lambda renta: renta.fecha_desde,
        )

        if debe_rechazarse:
            # La modificación rechazada no altera
            # la renta inicial ni la fianza.
            assert renta_inicial.importe == 150000
            assert contrato.fianza == 150000

        else:
            importe_esperado = (
                160000 if modificar_renta else 150000
            )

            assert renta_inicial.importe == importe_esperado
            assert contrato.fianza == 170000

        # Las rentas posteriores permanecen intactas.
        if historico == "renta-posterior":
            assert len(contrato.rentas) == 2

            renta_posterior = max(
                contrato.rentas,
                key=lambda renta: renta.fecha_desde,
            )

            assert renta_posterior.importe == 175000

        # Los alquileres ya registrados no se modifican.
        if historico == "factura":
            assert contrato.facturas[0].base == 150000

        elif historico == "alquiler-sin-factura":
            movimiento = contrato.movimientos_previstos[0]

            assert movimiento.apunte.total == 150000


@pytest.mark.parametrize(
    "historico, revision_protegida",
    [
        ("pendiente", False),
        ("revision-posterior", True),
        ("revision-aplicada", True),
        ("revision-no-aplicada", True),
    ],
)
@pytest.mark.parametrize(
    "modificacion",
    [
        "conservar",
        "fecha",
        "metodo",
        "fecha-y-metodo",
    ],
)
def test_editar_contrato_protege_primera_revision(
    historico,
    revision_protegida,
    modificacion,
) -> None:
    """Protege los datos iniciales de revisión cuando existe histórico."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)

    # El usuario crea un contrato con una primera
    # revisión pendiente.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))
        revision = contrato.revisiones_renta[0]

        # Se prepara el histórico correspondiente.
        if historico == "revision-posterior":
            contrato.revisiones_renta.append(
                RevisionRenta(
                    fecha_prevista=date(2028, 10, 1),
                    metodo="IPC_NACIONAL",
                    estado="PENDIENTE",
                )
            )

        elif historico == "revision-aplicada":
            revision.estado = "APLICADA"
            revision.fecha_resolucion = date(
                2027, 10, 1
            )
            revision.porcentaje_aplicado = 0

        elif historico == "revision-no-aplicada":
            revision.estado = "NO_APLICADA"
            revision.fecha_resolucion = date(
                2027, 10, 1
            )

        session.commit()

        contrato_id = contrato.id
        revision_id = revision.id
        estado_original = revision.estado
        fecha_resolucion_original = revision.fecha_resolucion

    # El usuario intenta modificar la primera revisión.
    if modificacion in ("fecha", "fecha-y-metodo"):
        datos["fecha_primera_revision"] = "01/11/2027"

    if modificacion in ("metodo", "fecha-y-metodo"):
        datos["metodo_revision"] = "IRAV"

    # También intenta corregir la fianza.
    datos["fianza"] = "1600,00"

    debe_rechazarse = (
        revision_protegida
        and modificacion != "conservar"
    )

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data=datos,
    )

    if debe_rechazarse:
        assert response.status_code == 400
        assert (
            "No pueden modificarse los datos de la primera revisión"
            in response.text
        )

    else:
        assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)
        revision = session.get(RevisionRenta, revision_id)

        assert revision is not None

        if debe_rechazarse:
            # Una modificación rechazada no altera
            # la revisión ni otros datos del contrato.
            assert revision.fecha_prevista == date(
                2027, 10, 1
            )
            assert revision.metodo == "IPC_NACIONAL"
            assert contrato.fianza == 150000

        else:
            fecha_esperada = (
                date(2027, 11, 1)
                if modificacion in (
                    "fecha", "fecha-y-metodo"
                )
                else date(2027, 10, 1)
            )

            metodo_esperado = (
                "IRAV"
                if modificacion in (
                    "metodo", "fecha-y-metodo"
                )
                else "IPC_NACIONAL"
            )

            assert revision.fecha_prevista == fecha_esperada
            assert revision.metodo == metodo_esperado
            assert contrato.fianza == 160000

        # No se altera el estado de la revisión
        # ni su fecha de resolución.
        assert revision.estado == estado_original

        assert (
            revision.fecha_resolucion
            == fecha_resolucion_original
        )

        assert len(contrato.revisiones_renta) == (
            2 if historico == "revision-posterior" else 1
        )

        if historico == "revision-posterior":
            posterior = max(
                contrato.revisiones_renta,
                key=lambda revision: revision.fecha_prevista,
            )

            assert posterior.fecha_prevista == date(
                2028, 10, 1
            )
            assert posterior.metodo == "IPC_NACIONAL"
            assert posterior.estado == "PENDIENTE"


@pytest.mark.parametrize(
    "historico, genera_factura_original",
    [
        ("sin-historico", True),
        ("sin-historico", False),
        ("factura", True),
        ("alquiler-sin-factura", False),
    ],
)
@pytest.mark.parametrize(
    "modificar_genera_factura",
    [
        pytest.param(False, id="conservar"),
        pytest.param(True, id="modificar"),
    ],
)
def test_editar_contrato_protege_genera_factura(
    historico,
    genera_factura_original,
    modificar_genera_factura,
) -> None:
    """Impide cambiar el régimen de facturación con alquileres registrados."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)

    if not genera_factura_original:
        datos.pop("genera_factura")

    # El usuario crea un contrato con el régimen
    # de facturación correspondiente.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        if historico == "factura":
            # El usuario registra una factura de alquiler.
            factura = crear_factura(
                contrato=contrato,
                periodo=date(2026, 12, 1),
                fecha_emision=date(2026, 12, 1),
            )

            session.add(factura)

        elif historico == "alquiler-sin-factura":
            categorias = {
                "ING_ALQUILERES": CategoriaContable(
                    codigo="ING_ALQUILERES",
                    naturaleza="INGRESO",
                    nombre="Alquileres",
                    activa=True,
                    subcategorias=(),
                ),
            }

            # El usuario contabiliza un alquiler sin factura.
            apunte, movimiento = (
                contabilizar_ingreso_sin_factura(
                    contrato=contrato,
                    periodo=date(2026, 12, 1),
                    fecha=date(2026, 12, 1),
                    categorias=categorias,
                )
            )

            session.add_all([apunte, movimiento])

        session.commit()
        contrato_id = contrato.id

    genera_factura_propuesto = (
        not genera_factura_original
        if modificar_genera_factura
        else genera_factura_original
    )

    # El usuario activa o desactiva la opción
    # de generar factura.
    if genera_factura_propuesto:
        datos["genera_factura"] = "on"
    else:
        datos.pop("genera_factura", None)

    datos["fianza"] = "1600,00"

    debe_rechazarse = (
        modificar_genera_factura
        and historico != "sin-historico"
    )

    # El usuario intenta guardar los cambios.
    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data=datos,
    )

    if debe_rechazarse:
        assert response.status_code == 400
        assert (
            "No puede modificarse la opción de generar factura"
            in response.text
        )

    else:
        assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        if debe_rechazarse:
            # La modificación rechazada conserva
            # el régimen original y la fianza.
            assert (
                contrato.genera_factura
                is genera_factura_original
            )
            assert contrato.fianza == 150000

        else:
            assert (
                contrato.genera_factura
                is genera_factura_propuesto
            )
            assert contrato.fianza == 160000

        # Los alquileres históricos no se modifican.
        if historico == "factura":
            assert len(contrato.facturas) == 1
            assert contrato.facturas[0].base == 150000

        elif historico == "alquiler-sin-factura":
            assert len(contrato.movimientos_previstos) == 1

            movimiento = contrato.movimientos_previstos[0]

            assert movimiento.apunte.total == 150000


def test_editar_contrato_permite_corregir_datos_facturacion(
) -> None:
    """Permite modificar datos futuros sin alterar facturas históricas."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)

    # El usuario crea un contrato que genera facturas.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        # El usuario registra una factura con los
        # datos fiscales y de facturación originales.
        factura = crear_factura(
            contrato=contrato,
            periodo=date(2026, 12, 1),
            fecha_emision=date(2026, 12, 1),
        )

        session.add(factura)
        session.commit()

        contrato_id = contrato.id
        factura_id = factura.id

    # El usuario corrige los datos del contrato
    # que se utilizarán en las facturas futuras.
    datos.update(
        {
            "fianza": "1700,00",
            "iva_porcentaje": "10,00",
            "retencion_porcentaje": "15,00",
            "direccion_facturacion": "Nueva dirección",
            "codigo_postal_facturacion": "36002",
            "poblacion_facturacion": "Vigo",
            "provincia_facturacion": "Pontevedra",
            "concepto_factura": "Nuevo concepto",
        }
    )

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        # Los nuevos datos quedan guardados.
        assert contrato.fianza == 170000
        assert contrato.iva_porcentaje == 1000
        assert contrato.retencion_porcentaje == 1500

        assert (
            contrato.direccion_facturacion
            == "Nueva dirección"
        )
        assert contrato.codigo_postal_facturacion == "36002"
        assert contrato.poblacion_facturacion == "Vigo"
        assert contrato.provincia_facturacion == "Pontevedra"
        assert contrato.concepto_factura == "Nuevo concepto"

        # La factura histórica conserva sus datos.
        assert len(contrato.facturas) == 1

        factura = contrato.facturas[0]

        assert factura.id == factura_id
        assert factura.iva_porcentaje == 2100
        assert factura.retencion_porcentaje == 1900
        assert factura.direccion_facturacion == "Dirección"
        assert factura.codigo_postal_facturacion == "36001"
        assert factura.poblacion_facturacion == "Pontevedra"
        assert factura.provincia_facturacion == "Pontevedra"
        assert factura.lineas[0].concepto == "Alquiler local"
        assert factura.base == 150000
        assert factura.iva_importe == 31500
        assert factura.retencion_importe == 28500
        assert factura.total == 153000


@pytest.mark.parametrize(
    "con_historico",
    [
        pytest.param(False, id="sin-historico"),
        pytest.param(True, id="con-historico"),
    ],
)
def test_formulario_editar_contrato_protege_campos(
    con_historico,
) -> None:
    """El formulario refleja las restricciones del contrato."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)

    # El usuario crea un contrato.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        if con_historico:
            # Registra una factura de alquiler.
            factura = crear_factura(
                contrato=contrato,
                periodo=date(2026, 12, 1),
                fecha_emision=date(2026, 12, 1),
            )

            session.add(factura)

            # Posteriormente resuelve una revisión.
            revision = contrato.revisiones_renta[0]
            revision.estado = "NO_APLICADA"
            revision.fecha_resolucion = date(
                2027, 10, 1
            )

        session.commit()
        contrato_id = contrato.id

    # El usuario abre el formulario de edición.
    response = client.get(
        f"/contratos/{contrato_id}/editar"
    )

    assert response.status_code == 200

    html = response.text

    # Los controles de texto protegidos son de solo lectura.
    for campo in (
        "fecha_inicio",
        "fecha_inicio_facturacion",
        "renta_inicial",
        "fecha_primera_revision",
    ):
        control = _etiqueta_control(html, campo)

        assert (
            "readonly" in control
        ) is con_historico

    # Los selectores y checkbox protegidos se deshabilitan.
    for campo in (
        "inmueble_id",
        "metodo_revision",
        "genera_factura",
    ):
        control = _etiqueta_control(html, campo)

        assert (
            "disabled" in control
        ) is con_historico

    # Estos campos permanecen siempre editables.
    for campo in (
        "fecha_vencimiento",
        "fianza",
        "iva_porcentaje",
        "retencion_porcentaje",
        "direccion_facturacion",
        "codigo_postal_facturacion",
        "poblacion_facturacion",
        "provincia_facturacion",
        "concepto_factura",
    ):
        control = _etiqueta_control(html, campo)

        assert "readonly" not in control
        assert "disabled" not in control

    # Los titulares pueden reordenarse.
    assert "readonly" not in _etiqueta_control(
        html, "titular_1_nombre"
    )

    assert "readonly" not in _etiqueta_control(
        html, "titular_1_nif"
    )

    if con_historico:
        assert (
            "Solo se permite reordenar los titulares existentes"
            in html
        )

        # Los controles deshabilitados deben conservar
        # sus valores al enviar el formulario.
        for campo, valor in (
            ("inmueble_id", str(inmueble_id)),
            ("metodo_revision", "IPC_NACIONAL"),
            ("genera_factura", "on"),
        ):
            assert re.search(
                rf'<input\b'
                rf'(?=[^>]*\btype="hidden")'
                rf'(?=[^>]*\bname="{campo}")'
                rf'(?=[^>]*\bvalue="{re.escape(valor)}")'
                rf'[^>]*>',
                html,
            )


@pytest.mark.parametrize(
    "genera_factura",
    [
        pytest.param(False, id="sin-factura"),
        pytest.param(True, id="con-factura"),
    ],
)
def test_formulario_contrato_indica_campos_obligatorios(
    genera_factura,
) -> None:
    """Los asteriscos reflejan los requisitos del contrato."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(
            session,
            genera_factura=genera_factura,
        )

        contrato_id = contrato.id

    # El usuario abre el formulario de edición.
    response = client.get(
        f"/contratos/{contrato_id}/editar"
    )

    assert response.status_code == 200

    html = response.text

    # Los campos generales son siempre obligatorios.
    for campo in (
        "inmueble_id",
        "fecha_inicio",
        "fecha_vencimiento",
        "fecha_inicio_facturacion",
        "fianza",
        "renta_inicial",
    ):
        assert "(*)" in _texto_label(html, campo)

    # Estos campos solo son obligatorios cuando
    # el contrato genera factura.
    for campo in (
        "iva_porcentaje",
        "retencion_porcentaje",
        "direccion_facturacion",
        "poblacion_facturacion",
        "provincia_facturacion",
        "concepto_factura",
        "fecha_primera_revision",
        "metodo_revision",
    ):
        etiqueta = _texto_label(html, campo)

        assert (
            "(*)" in etiqueta
        ) is genera_factura

    # El código postal es siempre opcional.
    assert "(*)" not in _texto_label(
        html, "codigo_postal_facturacion"
    )


@pytest.mark.parametrize(
    "operacion",
    [
        "nuevo",
        "editar",
    ],
)
def test_formulario_contrato_muestra_nota_titulares_y_clases(
    operacion,
) -> None:
    """Incluye información para el usuario y clases de presentación."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    if operacion == "nuevo":
        url = "/contratos/nuevo"

    else:
        session_factory = app.extensions[
            "contab_databases"
        ]["test"]

        with session_factory() as session:
            contrato = _crear_contrato_para_test(session)
            contrato_id = contrato.id

        url = f"/contratos/{contrato_id}/editar"

    # El usuario abre el formulario.
    response = client.get(url)

    assert response.status_code == 200

    html = response.text

    assert (
        "Para corregir el nombre o NIF de un titular existente"
        in html
    )

    # El formulario dispone de clases específicas
    # para controlar su presentación desde CSS.
    for clase in (
        "formulario-contrato",
        "formulario-contrato__inmueble",
        "formulario-contrato__titulares",
        "formulario-contrato__titular",
        "formulario-contrato__nota-titulares",
        "formulario-contrato__fecha-inicio",
        "formulario-contrato__fecha-vencimiento",
        "formulario-contrato__genera-factura",
        "formulario-contrato__facturacion",
        "formulario-contrato__renta",
        "formulario-contrato__revision",
        "formulario-contrato__obligatorio",
        "formulario-contrato__acciones",
    ):
        assert re.search(
            rf'class="[^"]*\b{re.escape(clase)}\b[^"]*"',
            html,
        )


def test_editar_contrato_conserva_inmueble_inactivo() -> None:
    """Permite editar un contrato cuyo inmueble ya está inactivo."""

    client, session_factory, inmueble_id = (
        _preparar_alta_contrato()
    )

    datos = _datos_nuevo_contrato_valido(inmueble_id)

    # El usuario crea un contrato.
    response = client.post(
        "/contratos/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.scalar(select(Contrato))

        # Posteriormente se desactiva el inmueble.
        contrato.inmueble.activo = False

        session.commit()
        contrato_id = contrato.id

    # El usuario abre el contrato para corregir otro dato.
    response = client.get(
        f"/contratos/{contrato_id}/editar"
    )

    assert response.status_code == 200

    # El inmueble original debe aparecer seleccionado,
    # aunque ya no esté activo.
    assert re.search(
        rf'<option\b'
        rf'(?=[^>]*\bvalue="{inmueble_id}")'
        rf'(?=[^>]*\bselected\b)'
        rf'[^>]*>',
        response.text,
    )

    datos["fianza"] = "1600,00"

    response = client.post(
        f"/contratos/{contrato_id}/editar",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        assert contrato.inmueble_id == inmueble_id
        assert contrato.inmueble.activo is False
        assert contrato.fianza == 160000


@pytest.mark.parametrize(
    "operacion",
    [
        "editar",
        "finalizar",
    ],
)
@pytest.mark.parametrize(
    "con_reembolso",
    [
        False,
        True,
    ],
)
def test_formulario_contrato_advierte_sobre_gastos(
    operacion,
    con_reembolso,
) -> None:
    """Advierte de las posibles consecuencias sobre gastos históricos."""

    app = crear_app_test()
    client = app.test_client()
    seleccionar_base(client)

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato_para_test(session)

        if con_reembolso:
            session.add(
                SolicitudReembolso(
                    contrato=contrato,
                    fecha_envio=date(2028, 6, 1),
                )
            )

        session.commit()
        contrato_id = contrato.id

    # El usuario abre el formulario correspondiente.
    response = client.get(
        f"/contratos/{contrato_id}/{operacion}"
    )

    assert response.status_code == 200

    mensaje = (
        "La modificación de la fecha de finalización "
        "puede afectar a la coherencia del reparto "
        "de gastos"
    )

    # Normalizamos los espacios para no depender
    # de la indentación de la plantilla.
    html = " ".join(response.text.split())

    assert (mensaje in html) is con_reembolso


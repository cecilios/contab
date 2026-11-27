"""Pruebas de las rutas web del módulo de inmuebles."""

import pytest
import re

from datetime import date, timedelta
from sqlalchemy import select

from contab.app import create_app
from contab.database import Base
from contab.config import CategoriaContable
from contab.contabilidad.services import crear_apunte_contable
from contab.contratos.services import crear_contrato
from contab.facturacion.services import crear_factura
from contab.models import (
    ApunteContable,
    Contrato,
    DatosFiscalesInmueble,
    DistribucionApunte,
    Inmueble,
    Inquilino,
)


DATOS_PROPIEDAD_FORMULARIO = {
    "porcentaje_titular": "100,00",
    "tipo_derecho": "PLENA_PROPIEDAD",
    "porcentaje_derecho": "100,00",
    "fecha_adquisicion": "01/01/2020",
    "tipo_adquisicion": "ONEROSA",
    "importe_adquisicion": "0,00",
    "gastos_adquisicion": "0,00",
    "fecha_transmision": "",
}


def _crear_app_test():
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


def _crear_inmueble_prueba(**datos) -> Inmueble:
    """Construye un inmueble con datos de propiedad válidos."""

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


def _datos_inmueble_con_propiedad(**cambios) -> dict:
    """Datos completos para probar el formulario de inmuebles."""
    datos = {
        "referencia": "PISO-FISCAL",
        "tipo": "P",
        "codigo_facturacion": "PF1",
        "descripcion": "Piso de prueba",
        "direccion": "Dirección",
        "codigo_postal": "36001",
        "poblacion": "Pontevedra",
        "provincia": "Pontevedra",
        "ref_catastral": "",
        "seguro": "",
        "participacion": "100,00",
        "notas": "",
        **DATOS_PROPIEDAD_FORMULARIO,
    }
    datos.update(cambios)
    return datos


def _preparar_inmueble_fiscal():
    """Crea una aplicación y un inmueble para las pruebas fiscales."""
    app = _crear_app_test()
    client = app.test_client()
    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="PISO-FISCAL",
            tipo="P",
            codigo_facturacion="PF1",
            descripcion="Piso fiscal",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    return client, session_factory, inmueble_id


def _crear_ejercicio_fiscal_prueba(
    session_factory,
    inmueble_id: int,
    ejercicio: int = 2025,
) -> None:
    """Registra datos fiscales válidos para un ejercicio."""

    with session_factory() as session:
        session.add(
            DatosFiscalesInmueble(
                inmueble_id=inmueble_id,
                ejercicio=ejercicio,
                valor_catastral=18000000,
                valor_suelo=7000000,
                valor_construccion=11000000,
                amortizacion_aplicada=420000,
            )
        )
        session.commit()


def _formulario_datos_fiscales(**cambios) -> dict:
    """Prepara un formulario fiscal válido, modificable por los tests."""

    datos = {
        "accion": "editar",
        "ejercicio": "2025",
        "valor_catastral": "200000,00",
        "valor_suelo": "80000,00",
        "valor_construccion": "120000,00",
        "amortizacion_aplicada": "5000,00",
    }

    datos.update(cambios)
    return datos


def _crear_contrato_inmueble_prueba(
    session,
    inmueble: Inmueble,
    *,
    fecha_inicio: date = date(2020, 1, 1),
    fecha_fin: date | None = None,
) -> Contrato:
    """Prepara un contrato para comprobar la integridad del inmueble."""

    inquilino = Inquilino(
        nombre="Ana Pérez",
        nif="11111111A",
    )

    session.add(inquilino)
    session.flush()

    inicio_facturacion = fecha_inicio.replace(day=1)

    if inicio_facturacion < fecha_inicio:
        inicio_facturacion = (
            inicio_facturacion.replace(day=28)
            + timedelta(days=4)
        ).replace(day=1)

    contrato = crear_contrato(
        inmueble=inmueble,
        titulares=[inquilino],
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=date(
            fecha_inicio.year + 5, 12, 31
        ),
        genera_factura=True,
        fecha_inicio_facturacion=inicio_facturacion,
        fianza=150000,
        iva_porcentaje=2100,
        retencion_porcentaje=1900,
        direccion_facturacion="Dirección",
        codigo_postal_facturacion="36001",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
        renta_inicial=150000,
        fecha_primera_revision=date(
            fecha_inicio.year + 1, 1, 1
        ),
        metodo_revision="IPC_NACIONAL",
    )

    contrato.fecha_fin = fecha_fin

    session.add(contrato)

    return contrato


def _crear_apunte_inmueble_prueba(
    session,
    inmueble: Inmueble,
) -> ApunteContable:
    """Prepara un gasto y sus distribuciones, cuando proceda."""

    categorias = {
        "GAS_IBI": CategoriaContable(
            codigo="GAS_IBI",
            naturaleza="GASTO",
            nombre="IBI",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2025, 6, 1),
        naturaleza="GASTO",
        categoria="GAS_IBI",
        concepto="IBI de prueba",
        base=100000,
    )

    session.add(apunte)

    return apunte


def _preparar_inmueble_subdividido_prueba(
    *,
    con_repartos: bool = False,
    padre_activo: bool = True,
    hijo_a_activo: bool = True,
    hijo_b_activo: bool = True,
):
    """Crea un inmueble T con dos locales al 60 % y 40 %."""

    app = _crear_app_test()
    client = app.test_client()
    client.post("/", data={"database": "test"})

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        padre = _crear_inmueble_prueba(
            referencia="TOTAL",
            tipo="T",
            codigo_facturacion="T1",
            descripcion="Inmueble subdividido",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            activo=padre_activo,
        )

        hijo_a = _crear_inmueble_prueba(
            inmueble_padre=padre,
            referencia="LOCAL-A",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local A",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=6000,
            activo=hijo_a_activo,
        )

        hijo_b = _crear_inmueble_prueba(
            inmueble_padre=padre,
            referencia="LOCAL-B",
            tipo="L",
            codigo_facturacion="B1",
            descripcion="Local B",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=4000,
            activo=hijo_b_activo,
        )

        session.add_all([padre, hijo_a, hijo_b])

        if con_repartos:
            # El usuario registra un gasto común.
            _crear_apunte_inmueble_prueba(
                session,
                padre,
            )

        session.commit()

        return (
            client,
            session_factory,
            padre.id,
            hijo_a.id,
            hijo_b.id,
        )





@pytest.mark.parametrize(
    ("campo", "mensaje"),
    [
        ("referencia", "La referencia es obligatoria."),
        ("codigo_facturacion", "El código de facturación es obligatorio."),
        ("descripcion", "La descripción es obligatoria."),
        ("direccion", "La dirección es obligatoria."),
        ("poblacion", "La población es obligatoria."),
        ("provincia", "La provincia es obligatoria."),
    ],
)
def test_crear_inmueble_rechaza_campos_obligatorios_vacios(
    campo, mensaje
) -> None:
    """Comprueba que los campos obligatorios no pueden quedar vacíos."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    datos = {
        "referencia": "LOCAL-1",
        "tipo": "L",
        "codigo_facturacion": "A1",
        "descripcion": "Local comercial",
        "direccion": "Dirección",
        "codigo_postal": "",
        "poblacion": "Pontevedra",
        "provincia": "Pontevedra",
        "ref_catastral": "",
        "seguro": "",
        "participacion": "100,00",
        "notas": "",
    }

    datos[campo] = ""

    response = client.post(
        "/inmuebles/nuevo",
        data=datos,
    )

    assert response.status_code == 400
    assert mensaje in response.text


def test_listado_inmuebles_vacio() -> None:
    """Comprueba que el listado informa cuando no existen inmuebles."""
    app = _crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/inmuebles/")

    assert response.status_code == 200
    assert "Inmuebles" in response.text
    assert (
        "No hay inmuebles subdivididos."
        in response.text
    )
    assert (
        "No hay inmuebles independientes."
        in response.text
    )
    assert "Inmuebles subdivididos" in response.text
    assert "Inmuebles independientes" in response.text


def test_listado_muestra_inmuebles_registrados() -> None:
    """Comprueba que el listado muestra los inmuebles almacenados."""
    app = _crear_app_test()
    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        session.add(
            _crear_inmueble_prueba(
                referencia="LOCAL-1",
                tipo="L",
                codigo_facturacion="A1",
                descripcion="Local comercial",
                direccion="Rúa Michelena, 18",
                poblacion="Pontevedra",
                provincia="Pontevedra",
            )
        )
        session.commit()

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/inmuebles/")

    assert response.status_code == 200
    assert "LOCAL-1" in response.text
    assert "Local comercial" in response.text
    assert "No hay inmuebles registrados." not in response.text


def test_formulario_nuevo_inmueble_responde() -> None:
    """Comprueba que puede abrirse el formulario de alta de inmuebles."""
    app = _crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/inmuebles/nuevo")

    assert response.status_code == 200
    assert "Nuevo inmueble" in response.text
    assert "Referencia" in response.text
    assert "Código de facturación" in response.text


def test_crear_inmueble_desde_formulario() -> None:
    """Comprueba que un inmueble válido se guarda desde la interfaz web."""
    app = _crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "referencia": "LOCAL-2",
            "tipo": "L",
            "codigo_facturacion": "A2",
            "descripcion": "Segundo local",
            "direccion": "Rúa da Oliva, 20",
            "codigo_postal": "36001",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "POL-12345",
            "participacion": "100,00",
            "notas": "",
            **DATOS_PROPIEDAD_FORMULARIO,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "LOCAL-2" in response.text
    assert "Segundo local" in response.text


def test_crear_inmueble_rechaza_referencia_vacia() -> None:
    """Comprueba que no puede crearse un inmueble sin referencia."""
    app = _crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "referencia": "",
            "codigo_facturacion": "A2",
            "descripcion": "Segundo local",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "100,00",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "La referencia es obligatoria." in response.text


def test_crear_inmueble_convierte_participacion_a_centesimas() -> None:
    """Comprueba que 32,56 % se almacena internamente como 3256."""
    app = _crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "referencia": "PARTE-A",
            "tipo": "L",
            "codigo_facturacion": "A3",
            "descripcion": "Parte A",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "32,56",
            "notas": "",
            **DATOS_PROPIEDAD_FORMULARIO,
        },
    )

    assert response.status_code == 302

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = session.query(Inmueble).filter_by(
            referencia="PARTE-A"
        ).one()

        assert inmueble.participacion == 3256


def test_listado_muestra_base_activa() -> None:
    """Comprueba que la interfaz muestra la base de datos seleccionada."""
    app = _crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/inmuebles/")

    assert response.status_code == 200
    assert "Base activa:" in response.text
    assert "test" in response.text


def test_crear_inmueble_rechaza_participacion_cero() -> None:
    """Comprueba que la participación debe ser superior al 0 %."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "referencia": "LOCAL-1",
            "tipo": "L",
            "codigo_facturacion": "A1",
            "descripcion": "Local comercial",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "0",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "La participación debe ser superior al 0 %." in response.text


def test_crear_inmueble_rechaza_participacion_superior_a_cien() -> None:
    """Comprueba que la participación no puede superar el 100 %."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "referencia": "LOCAL-1",
            "tipo": "L",
            "codigo_facturacion": "A1",
            "descripcion": "Local comercial",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "100,01",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "La participación no puede superar el 100 %." in response.text


def test_crear_inmueble_rechaza_participacion_no_numerica() -> None:
    """Comprueba que la participación debe contener un porcentaje válido."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "referencia": "LOCAL-1",
            "tipo": "L",
            "codigo_facturacion": "A1",
            "descripcion": "Local comercial",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "abc",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "La participación debe ser un porcentaje válido." in response.text


def test_crear_inmueble_rechaza_referencia_duplicada() -> None:
    """Comprueba que dos inmuebles no pueden compartir referencia."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    datos = {
        "referencia": "LOCAL-1",
        "tipo": "L",
        "codigo_facturacion": "A1",
        "descripcion": "Local comercial",
        "direccion": "Dirección",
        "codigo_postal": "",
        "poblacion": "Pontevedra",
        "provincia": "Pontevedra",
        "ref_catastral": "",
        "seguro": "",
        "participacion": "100,00",
        "notas": "",
        **DATOS_PROPIEDAD_FORMULARIO,
    }

    response = client.post("/inmuebles/nuevo", data=datos)
    assert response.status_code == 302

    datos["codigo_facturacion"] = "A2"

    response = client.post("/inmuebles/nuevo", data=datos)

    assert response.status_code == 400
    assert "Ya existe un inmueble con esa referencia." in response.text


def test_crear_inmueble_rechaza_codigo_facturacion_duplicado() -> None:
    """Comprueba que dos inmuebles no pueden compartir código de facturación."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    datos = {
        "referencia": "LOCAL-1",
        "tipo": "L",
        "codigo_facturacion": "A1",
        "descripcion": "Local comercial",
        "direccion": "Dirección",
        "codigo_postal": "",
        "poblacion": "Pontevedra",
        "provincia": "Pontevedra",
        "ref_catastral": "",
        "seguro": "",
        "participacion": "100,00",
        "notas": "",
        **DATOS_PROPIEDAD_FORMULARIO,
    }

    response = client.post("/inmuebles/nuevo", data=datos)
    assert response.status_code == 302

    datos["referencia"] = "LOCAL-2"

    response = client.post("/inmuebles/nuevo", data=datos)

    assert response.status_code == 400
    assert "Ya existe un inmueble con ese código de facturación." in response.text


def test_formulario_editar_inmueble_muestra_datos_actuales() -> None:
    """Comprueba que el formulario de edición muestra los datos existentes."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección inicial",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=10000,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.get(f"/inmuebles/{inmueble_id}/editar")

    assert response.status_code == 200
    assert "Editar inmueble" in response.text
    assert 'value="LOCAL-1"' in response.text
    assert 'value="Dirección inicial"' in response.text
    assert 'value="100,00"' in response.text


def test_editar_inmueble_guarda_cambios() -> None:
    """Comprueba que los cambios realizados en un inmueble se guardan."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección inicial",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=10000,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.post(
        f"/inmuebles/{inmueble_id}/editar",
        data={
            "referencia": "LOCAL-1",
            "tipo": "L",
            "codigo_facturacion": "A1",
            "descripcion": "Local reformado",
            "direccion": "Nueva dirección",
            "codigo_postal": "36001",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "POL-999",
            "participacion": "32,56",
            "notas": "Datos actualizados",
            **DATOS_PROPIEDAD_FORMULARIO,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Local reformado" in response.text

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        assert inmueble.descripcion == "Local reformado"
        assert inmueble.direccion == "Nueva dirección"
        assert inmueble.participacion == 3256
        assert inmueble.seguro == "POL-999"


def test_editar_inmueble_inexistente_devuelve_404() -> None:
    """Comprueba que editar un inmueble inexistente devuelve 404."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    response = client.get("/inmuebles/99999/editar")

    assert response.status_code == 404


def test_editar_inmueble_rechaza_referencia_de_otro_inmueble() -> None:
    """Comprueba que la edición no puede duplicar la referencia de otro inmueble."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        primero = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Primero",
            direccion="Dirección 1",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        segundo = _crear_inmueble_prueba(
            referencia="LOCAL-2",
            tipo="L",
            codigo_facturacion="A2",
            descripcion="Segundo",
            direccion="Dirección 2",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        session.add_all([primero, segundo])
        session.commit()

        segundo_id = segundo.id

    response = client.post(
        f"/inmuebles/{segundo_id}/editar",
        data={
            "referencia": "LOCAL-1",
            "tipo": "L",
            "codigo_facturacion": "A2",
            "descripcion": "Segundo",
            "direccion": "Dirección 2",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "100,00",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "Ya existe un inmueble con esa referencia." in response.text


def test_confirmar_desactivacion_inmueble() -> None:
    """Comprueba que se muestra confirmación antes de desactivar un inmueble."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

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
            activo=True,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.get(f"/inmuebles/{inmueble_id}/estado")

    assert response.status_code == 200
    assert "Este inmueble quedará inactivo" in response.text
    assert "Permanecerá a efectos históricos" in response.text
    assert "Desactivar" in response.text
    assert "Cancelar" in response.text


def test_desactivar_inmueble() -> None:
    """Comprueba que confirmar la desactivación marca el inmueble como inactivo."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

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
            activo=True,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.post(
        f"/inmuebles/{inmueble_id}/estado",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "INACTIVO" in response.text

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        assert inmueble.activo is False


def test_confirmar_activacion_inmueble() -> None:
    """Comprueba que se muestra confirmación antes de activar un inmueble."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

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
            activo=False,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.get(f"/inmuebles/{inmueble_id}/estado")

    assert response.status_code == 200
    assert "Este inmueble volverá a estar activo" in response.text
    assert "Activar" in response.text
    assert "Cancelar" in response.text


def test_activar_inmueble() -> None:
    """Comprueba que confirmar la activación marca el inmueble como activo."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

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
            activo=False,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.post(
        f"/inmuebles/{inmueble_id}/estado",
        follow_redirects=True,
    )

    assert response.status_code == 200

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        assert inmueble.activo is True


def test_cambiar_estado_inmueble_inexistente_devuelve_404() -> None:
    """Comprueba que cambiar el estado de un inmueble inexistente devuelve 404."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    response = client.get("/inmuebles/99999/estado")

    assert response.status_code == 404


def test_formulario_inmueble_muestra_tipos() -> None:
    app = _crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/inmuebles/nuevo")

    assert response.status_code == 200
    assert "Piso" in response.text
    assert "Local" in response.text
    assert "Garaje" in response.text


def test_crear_local_perteneciente_a_inmueble_subdividido() -> None:
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

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
            participacion=10000,
        )
        session.add(inmueble_subdividido)
        session.commit()
        inmueble_subdividido_id = inmueble_subdividido.id

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "tipo": "L",
            "referencia": "ALOPEZ-LOCAL1",
            "codigo_facturacion": "AL1",
            "descripcion": "Local 1",
            "direccion": "Avenida López, 1",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "32,50",
            "es_parte_inmueble": "on",
            "inmueble_padre_id": str(
                inmueble_subdividido_id
            ),
            "notas": "",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        local = session.scalar(
            select(Inmueble).where(
                Inmueble.referencia
                == "ALOPEZ-LOCAL1"
            )
        )

        assert local is not None
        assert (
            local.inmueble_padre_id
            == inmueble_subdividido_id
        )
        assert local.participacion == 3250


def test_formulario_inmueble_muestra_totales() -> None:
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

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
        session.add(inmueble_subdividido)
        session.commit()

    response = client.get("/inmuebles/nuevo")

    assert response.status_code == 200
    assert "Es parte de un inmueble" in response.text
    assert "ALOPEZ-COMUN" in response.text
    assert "Inmueble completo" in response.text


def test_error_conserva_inmueble_padre_seleccionado() -> None:
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

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
        session.add(inmueble_subdividido)
        session.commit()
        inmueble_subdividido_id = inmueble_subdividido.id

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "tipo": "L",
            "referencia": "",  # Fuerza el error
            "codigo_facturacion": "AL1",
            "descripcion": "Local 1",
            "direccion": "Avenida López, 1",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "32,50",
            "es_parte_inmueble": "on",
            "inmueble_padre_id": str(inmueble_subdividido_id),
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "La referencia es obligatoria." in response.text
    assert "ALOPEZ-COMUN" in response.text

    assert re.search(
        rf'<option[^>]*value="{inmueble_subdividido_id}"'
        r'[^>]*selected',
        response.text,
    )

    assert re.search(
        r'<input[^>]*name="es_parte_inmueble"'
        r'[^>]*checked',
        response.text,
    )


def test_listado_muestra_jerarquia_inmuebles() -> None:
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

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
            descripcion="Local 1",
            direccion="Avenida López, 1",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=3250,
            inmueble_padre=inmueble_subdividido,
        )

        independiente = _crear_inmueble_prueba(
            referencia="PISO-1",
            tipo="P",
            codigo_facturacion="P1",
            descripcion="Piso independiente",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        session.add_all([
            inmueble_subdividido,
            local,
            independiente,
        ])
        session.commit()

    response = client.get("/inmuebles/")

    assert response.status_code == 200
    assert "ALOPEZ-COMUN" in response.text
    assert "ALOPEZ-LOCAL1" in response.text
    assert "PISO-1" in response.text
    assert "Inmuebles independientes" in response.text

    assert (
        response.text.index("ALOPEZ-COMUN")
        < response.text.index("ALOPEZ-LOCAL1")
    )

    assert response.text.count(
        "ALOPEZ-LOCAL1"
    ) == 1




def test_crear_local_rechaza_padre_que_no_es_total() -> None:
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        padre_incorrecto = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local independiente",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        session.add(padre_incorrecto)
        session.commit()
        padre_id = padre_incorrecto.id

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "tipo": "L",
            "referencia": "LOCAL-2",
            "codigo_facturacion": "A2",
            "descripcion": "Local subordinado",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "50,00",
            "es_parte_inmueble": "on",
            "inmueble_padre_id": str(padre_id),
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert (
        "no es un inmueble subdividido"
        in response.text
    )

    with session_factory() as session:
        local = session.scalar(
            select(Inmueble).where(
                Inmueble.referencia == "LOCAL-2"
            )
        )

        assert local is None


def test_editar_inmueble_total_con_hijos_rechaza_cambio_tipo() -> None:
    """No permite cambiar el tipo de un inmueble T con hijos."""
    app = _crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="EDIFICIO-1",
            tipo="T",
            codigo_facturacion="E1",
            descripcion="Edificio completo",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=10000,
        )

        hijo = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local del edificio",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=5000,
            inmueble_padre=inmueble,
        )

        session.add_all([inmueble, hijo])
        session.commit()
        inmueble_id = inmueble.id

    response = client.post(
        f"/inmuebles/{inmueble_id}/editar",
        data={
            "referencia": "EDIFICIO-1",
            "tipo": "L",
            "codigo_facturacion": "E1",
            "descripcion": "Edificio completo",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "100,00",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert (
        "No se puede cambiar el tipo de un "
        "inmueble subdividido que tiene hijos."
    ) in response.text

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        assert inmueble.tipo == "T"
        assert session.scalar(
            select(Inmueble.id).where(
                Inmueble.inmueble_padre_id == inmueble_id
            )
        ) is not None


def test_crear_inmueble_guarda_datos_propiedad() -> None:
    app = _crear_app_test()
    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = _datos_inmueble_con_propiedad(
        porcentaje_titular="75,50",
        tipo_derecho="USUFRUCTO",
        porcentaje_derecho="50,25",
        fecha_adquisicion="15/06/2019",
        tipo_adquisicion="LUCRATIVA",
        importe_adquisicion="150000,75",
        gastos_adquisicion="3500,50",
        fecha_transmision="31/12/2025",
    )

    response = client.post("/inmuebles/nuevo", data=datos)

    assert response.status_code == 302

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = session.scalar(
            select(Inmueble).where(
                Inmueble.referencia == "PISO-FISCAL"
            )
        )

        assert inmueble is not None
        assert inmueble.porcentaje_titular == 7550
        assert inmueble.tipo_derecho == "USUFRUCTO"
        assert inmueble.porcentaje_derecho == 5025
        assert inmueble.fecha_adquisicion == date(2019, 6, 15)
        assert inmueble.tipo_adquisicion == "LUCRATIVA"
        assert inmueble.importe_adquisicion == 15000075
        assert inmueble.gastos_adquisicion == 350050
        assert inmueble.fecha_transmision == date(2025, 12, 31)


def test_editar_inmueble_muestra_y_guarda_datos_propiedad() -> None:
    app = _crear_app_test()
    client = app.test_client()
    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="PISO-FISCAL",
            tipo="P",
            codigo_facturacion="PF1",
            descripcion="Piso de prueba",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            porcentaje_titular=7550,
            tipo_derecho="USUFRUCTO",
            porcentaje_derecho=5025,
            fecha_adquisicion=date(2019, 6, 15),
            tipo_adquisicion="LUCRATIVA",
            importe_adquisicion=15000075,
            gastos_adquisicion=350050,
            fecha_transmision=None,
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.get(
        f"/inmuebles/{inmueble_id}/editar"
    )

    assert response.status_code == 200
    assert 'value="75,50"' in response.text
    assert 'value="50,25"' in response.text
    assert 'value="15/06/2019"' in response.text
    assert 'value="150000,75"' in response.text
    assert 'value="3500,50"' in response.text

    datos = _datos_inmueble_con_propiedad(
        porcentaje_titular="80,00",
        tipo_derecho="PLENA_PROPIEDAD",
        porcentaje_derecho="100,00",
        fecha_adquisicion="01/02/2020",
        tipo_adquisicion="ONEROSA",
        importe_adquisicion="200000,00",
        gastos_adquisicion="5000,00",
        fecha_transmision="30/09/2026",
    )

    response = client.post(
        f"/inmuebles/{inmueble_id}/editar",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        assert inmueble.porcentaje_titular == 8000
        assert inmueble.tipo_derecho == "PLENA_PROPIEDAD"
        assert inmueble.porcentaje_derecho == 10000
        assert inmueble.fecha_adquisicion == date(2020, 2, 1)
        assert inmueble.tipo_adquisicion == "ONEROSA"
        assert inmueble.importe_adquisicion == 20000000
        assert inmueble.gastos_adquisicion == 500000
        assert inmueble.fecha_transmision == date(2026, 9, 30)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("porcentaje_titular", "101,00"),
        ("porcentaje_derecho", "-1,00"),
        ("fecha_adquisicion", "31/02/2020"),
        ("tipo_derecho", "OTRO"),
        ("tipo_adquisicion", "OTRA"),
        ("importe_adquisicion", "-100,00"),
        ("gastos_adquisicion", "abc"),
        ("fecha_transmision", "31/12/2019"),
    ],
)
def test_crear_inmueble_rechaza_datos_propiedad_invalidos(
    campo, valor
) -> None:
    app = _crear_app_test()
    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = _datos_inmueble_con_propiedad()
    datos[campo] = valor

    response = client.post(
        "/inmuebles/nuevo",
        data=datos,
    )

    assert response.status_code == 400

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = session.scalar(
            select(Inmueble).where(
                Inmueble.referencia == "PISO-FISCAL"
            )
        )

        assert inmueble is None


def test_crear_inmueble_hijo_no_guarda_datos_propiedad() -> None:
    app = _crear_app_test()
    client = app.test_client()
    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        padre = _crear_inmueble_prueba(
            referencia="EDIFICIO-FISCAL",
            tipo="T",
            codigo_facturacion="EF1",
            descripcion="Edificio",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        session.add(padre)
        session.commit()
        padre_id = padre.id

    datos = _datos_inmueble_con_propiedad(
        referencia="LOCAL-HIJO",
        tipo="L",
        codigo_facturacion="LH1",
        participacion="25,00",
        es_parte_inmueble="on",
        inmueble_padre_id=str(padre_id),
    )

    response = client.post(
        "/inmuebles/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        hijo = session.scalar(
            select(Inmueble).where(
                Inmueble.referencia == "LOCAL-HIJO"
            )
        )

        assert hijo is not None
        assert hijo.inmueble_padre_id == padre_id
        assert hijo.participacion == 2500

        assert hijo.porcentaje_titular is None
        assert hijo.tipo_derecho is None
        assert hijo.porcentaje_derecho is None
        assert hijo.fecha_adquisicion is None
        assert hijo.tipo_adquisicion is None
        assert hijo.importe_adquisicion is None
        assert hijo.gastos_adquisicion is None
        assert hijo.fecha_transmision is None


def test_listar_datos_fiscales_ordena_ejercicios() -> None:
    app = _crear_app_test()
    client = app.test_client()
    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="PISO-FISCAL",
            tipo="P",
            codigo_facturacion="PF1",
            descripcion="Piso de prueba",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        session.add(inmueble)
        session.flush()

        session.add_all([
            DatosFiscalesInmueble(
                inmueble_id=inmueble.id,
                ejercicio=2024,
                valor_catastral=17000000,
                valor_suelo=6500000,
                valor_construccion=10500000,
                amortizacion_aplicada=400000,
            ),
            DatosFiscalesInmueble(
                inmueble_id=inmueble.id,
                ejercicio=2025,
                valor_catastral=17500000,
                valor_suelo=6800000,
                valor_construccion=10700000,
                amortizacion_aplicada=410000,
            ),
        ])
        inmueble_id = inmueble.id
        session.commit()

    response = client.get(
        f"/inmuebles/{inmueble_id}/datos-fiscales"
    )

    assert response.status_code == 200
    assert "Datos fiscales del inmueble" in response.text
    assert "PISO-FISCAL" in response.text
    assert response.text.index("2025") < response.text.index("2024")


@pytest.mark.parametrize("tipo", ["P", "L", "G", "T"])
def test_datos_fiscales_permite_inmuebles_sin_padre(
    tipo
) -> None:
    app = _crear_app_test()
    client = app.test_client()
    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        inmueble = _crear_inmueble_prueba(
            referencia="INMUEBLE-1",
            tipo=tipo,
            codigo_facturacion="A1",
            descripcion="Inmueble de prueba",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    response = client.get(
        f"/inmuebles/{inmueble_id}/datos-fiscales"
    )

    assert response.status_code == 200
    assert (
        "No hay datos fiscales registrados"
        in response.text
    )


def test_datos_fiscales_no_permite_local_hijo() -> None:
    app = _crear_app_test()
    client = app.test_client()
    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        padre = _crear_inmueble_prueba(
            referencia="TOTAL-1",
            tipo="T",
            codigo_facturacion="T1",
            descripcion="Inmueble subdividido",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        hijo = _crear_inmueble_prueba(
            referencia="HIJO-1",
            tipo="L",
            codigo_facturacion="H1",
            descripcion="Local hijo",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            inmueble_padre=padre,
        )

        session.add_all([padre, hijo])
        session.commit()
        padre_id = padre.id
        hijo_id = hijo.id

    listado = client.get("/inmuebles/")

    assert listado.status_code == 200
    assert (
        f"/inmuebles/{padre_id}/datos-fiscales"
        in listado.text
    )
    assert (
        f"/inmuebles/{hijo_id}/datos-fiscales"
        not in listado.text
    )

    response = client.get(
        f"/inmuebles/{hijo_id}/datos-fiscales"
    )

    assert response.status_code == 404


def test_datos_fiscales_inmueble_inexistente() -> None:
    app = _crear_app_test()
    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.get(
        "/inmuebles/999999/datos-fiscales"
    )

    assert response.status_code == 404


def test_datos_fiscales_nuevo_ejercicio_copia_valores() -> None:
    client, session_factory, inmueble_id = _preparar_inmueble_fiscal()

    with session_factory() as session:
        session.add(
            DatosFiscalesInmueble(
                inmueble_id=inmueble_id,
                ejercicio=2025,
                valor_catastral=18000000,
                valor_suelo=7000000,
                valor_construccion=11000000,
                amortizacion_aplicada=420000,
            )
        )
        session.commit()

    response = client.get(
        f"/inmuebles/{inmueble_id}/datos-fiscales?nuevo=1"
    )

    assert response.status_code == 200
    assert 'name="ejercicio"' in response.text
    assert 'value="2026"' in response.text
    assert 'value="180000,00"' in response.text
    assert 'value="70000,00"' in response.text
    assert 'value="110000,00"' in response.text
    assert 'value="0,00"' in response.text


def test_datos_fiscales_guarda_nuevo_ejercicio() -> None:
    client, session_factory, inmueble_id = _preparar_inmueble_fiscal()

    response = client.post(
        f"/inmuebles/{inmueble_id}/datos-fiscales",
        data={
            "accion": "nuevo",
            "ejercicio": "2026",
            "valor_catastral": "180000,00",
            "valor_suelo": "70000,00",
            "valor_construccion": "110000,00",
            "amortizacion_aplicada": "4200,00",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        datos = session.scalar(
            select(DatosFiscalesInmueble).where(
                DatosFiscalesInmueble.inmueble_id == inmueble_id,
                DatosFiscalesInmueble.ejercicio == 2026,
            )
        )

        assert datos is not None
        assert datos.valor_catastral == 18000000
        assert datos.valor_suelo == 7000000
        assert datos.valor_construccion == 11000000
        assert datos.amortizacion_aplicada == 420000


def test_datos_fiscales_rechaza_desglose_incorrecto() -> None:
    client, session_factory, inmueble_id = _preparar_inmueble_fiscal()

    response = client.post(
        f"/inmuebles/{inmueble_id}/datos-fiscales",
        data={
            "accion": "nuevo",
            "ejercicio": "2026",
            "valor_catastral": "180000,00",
            "valor_suelo": "70000,00",
            "valor_construccion": "100000,00",
            "amortizacion_aplicada": "4200,00",
        },
    )

    assert response.status_code == 400
    assert (
        "debe ser igual al valor catastral"
        in response.text
    )
    assert 'value="100000,00"' in response.text

    with session_factory() as session:
        datos = session.scalar(
            select(DatosFiscalesInmueble).where(
                DatosFiscalesInmueble.inmueble_id == inmueble_id
            )
        )

        assert datos is None


def test_datos_fiscales_rechaza_ejercicio_duplicado() -> None:
    client, session_factory, inmueble_id = _preparar_inmueble_fiscal()

    with session_factory() as session:
        session.add(
            DatosFiscalesInmueble(
                inmueble_id=inmueble_id,
                ejercicio=2025,
                valor_catastral=18000000,
                valor_suelo=7000000,
                valor_construccion=11000000,
                amortizacion_aplicada=0,
            )
        )
        session.commit()

    response = client.post(
        f"/inmuebles/{inmueble_id}/datos-fiscales",
        data={
            "accion": "nuevo",
            "ejercicio": "2025",
            "valor_catastral": "180000,00",
            "valor_suelo": "70000,00",
            "valor_construccion": "110000,00",
            "amortizacion_aplicada": "0,00",
        },
    )

    assert response.status_code == 400
    assert (
        "Ya existen datos fiscales para ese ejercicio."
        in response.text
    )


def test_datos_fiscales_editar_ejercicio_guarda_cambios() -> None:
    client, session_factory, inmueble_id = _preparar_inmueble_fiscal()

    _crear_ejercicio_fiscal_prueba(
        session_factory, inmueble_id
    )

    url = f"/inmuebles/{inmueble_id}/datos-fiscales"

    response = client.get(f"{url}?editar=2025")

    assert response.status_code == 200
    assert 'name="accion"' in response.text
    assert 'value="editar"' in response.text
    assert 'value="180000,00"' in response.text

    response = client.post(
        url,
        data=_formulario_datos_fiscales(),
    )

    assert response.status_code == 302

    with session_factory() as session:
        registro = session.scalar(
            select(DatosFiscalesInmueble).where(
                DatosFiscalesInmueble.inmueble_id == inmueble_id,
                DatosFiscalesInmueble.ejercicio == 2025,
            )
        )

        assert registro is not None
        assert registro.ejercicio == 2025
        assert registro.valor_catastral == 20000000
        assert registro.valor_suelo == 8000000
        assert registro.valor_construccion == 12000000
        assert registro.amortizacion_aplicada == 500000


def test_datos_fiscales_cancelar_edicion_no_modifica_datos() -> None:
    client, session_factory, inmueble_id = _preparar_inmueble_fiscal()

    _crear_ejercicio_fiscal_prueba(
        session_factory, inmueble_id
    )

    url = f"/inmuebles/{inmueble_id}/datos-fiscales"

    response = client.get(f"{url}?editar=2025")

    assert response.status_code == 200
    assert "Cancelar" in response.text

    response = client.get(url)

    assert response.status_code == 200
    assert "Editar" in response.text

    with session_factory() as session:
        registro = session.scalar(
            select(DatosFiscalesInmueble).where(
                DatosFiscalesInmueble.inmueble_id == inmueble_id,
                DatosFiscalesInmueble.ejercicio == 2025,
            )
        )

        assert registro is not None
        assert registro.valor_catastral == 18000000
        assert registro.valor_suelo == 7000000
        assert registro.valor_construccion == 11000000
        assert registro.amortizacion_aplicada == 420000


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("valor_catastral", "-100,00"),
        ("valor_catastral", "abc"),
        ("valor_catastral", ""),
        ("valor_catastral", "100,123"),
        ("valor_suelo", "-1,00"),
        ("valor_suelo", "abc"),
        ("valor_suelo", ""),
        ("valor_suelo", "100,123"),
        ("valor_construccion", "-50,00"),
        ("valor_construccion", ""),
        ("valor_construccion", "100,123"),
        ("amortizacion_aplicada", "-1,00"),
        ("amortizacion_aplicada", "abc"),
        ("amortizacion_aplicada", ""),
        ("amortizacion_aplicada", "100,123"),
    ],
)
def test_datos_fiscales_rechaza_importes_invalidos(
    campo, valor
) -> None:
    client, session_factory, inmueble_id = _preparar_inmueble_fiscal()

    _crear_ejercicio_fiscal_prueba(
        session_factory, inmueble_id
    )

    datos = _formulario_datos_fiscales()
    datos[campo] = valor

    response = client.post(
        f"/inmuebles/{inmueble_id}/datos-fiscales",
        data=datos,
    )

    assert response.status_code == 400
    assert "debe ser un importe no negativo" in response.text

    with session_factory() as session:
        registro = session.scalar(
            select(DatosFiscalesInmueble).where(
                DatosFiscalesInmueble.inmueble_id == inmueble_id,
                DatosFiscalesInmueble.ejercicio == 2025,
            )
        )

        assert registro is not None
        assert registro.valor_catastral == 18000000
        assert registro.valor_suelo == 7000000
        assert registro.valor_construccion == 11000000
        assert registro.amortizacion_aplicada == 420000


def test_datos_fiscales_error_edicion_conserva_valores() -> None:
    client, session_factory, inmueble_id = _preparar_inmueble_fiscal()

    _crear_ejercicio_fiscal_prueba(
        session_factory, inmueble_id
    )

    datos = _formulario_datos_fiscales(
        valor_catastral="250000,00",
        valor_suelo="80000,00",
        valor_construccion="120000,00",
    )

    response = client.post(
        f"/inmuebles/{inmueble_id}/datos-fiscales",
        data=datos,
    )

    assert response.status_code == 400
    assert (
        "debe ser igual al valor catastral"
        in response.text
    )

    assert 'value="250000,00"' in response.text
    assert 'value="80000,00"' in response.text
    assert 'value="120000,00"' in response.text

    with session_factory() as session:
        registro = session.scalar(
            select(DatosFiscalesInmueble).where(
                DatosFiscalesInmueble.inmueble_id == inmueble_id,
                DatosFiscalesInmueble.ejercicio == 2025,
            )
        )

        assert registro.valor_catastral == 18000000
        assert registro.valor_suelo == 7000000
        assert registro.valor_construccion == 11000000


@pytest.mark.parametrize("accion", ["nuevo", "editar"])
def test_datos_fiscales_rechaza_escritura_local_hijo(
    accion
) -> None:
    app = _crear_app_test()
    client = app.test_client()
    client.post("/", data={"database": "test"})

    session_factory = app.extensions["contab_databases"]["test"]

    with session_factory() as session:
        padre = _crear_inmueble_prueba(
            referencia="TOTAL-FISCAL",
            tipo="T",
            codigo_facturacion="TF1",
            descripcion="Inmueble subdividido",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        hijo = _crear_inmueble_prueba(
            referencia="LOCAL-FISCAL",
            tipo="L",
            codigo_facturacion="LF1",
            descripcion="Local hijo",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=5000,
            inmueble_padre=padre,
        )

        session.add_all([padre, hijo])
        session.commit()
        hijo_id = hijo.id

    datos = _formulario_datos_fiscales(
        accion=accion
    )

    response = client.post(
        f"/inmuebles/{hijo_id}/datos-fiscales",
        data=datos,
    )

    assert response.status_code == 404

    with session_factory() as session:
        registros = session.scalars(
            select(DatosFiscalesInmueble).where(
                DatosFiscalesInmueble.inmueble_id == hijo_id
            )
        ).all()

        assert registros == []


def test_datos_fiscales_no_edita_ejercicio_inexistente() -> None:
    client, session_factory, inmueble_id = _preparar_inmueble_fiscal()

    _crear_ejercicio_fiscal_prueba(
        session_factory, inmueble_id
    )

    url = f"/inmuebles/{inmueble_id}/datos-fiscales"

    response = client.get(f"{url}?editar=2024")

    assert response.status_code == 404

    response = client.post(
        url,
        data=_formulario_datos_fiscales(
            ejercicio="2024"
        ),
    )

    assert response.status_code == 404

    with session_factory() as session:
        registros = session.scalars(
            select(DatosFiscalesInmueble).where(
                DatosFiscalesInmueble.inmueble_id == inmueble_id
            )
        ).all()

        assert len(registros) == 1
        assert registros[0].ejercicio == 2025
        assert registros[0].valor_catastral == 18000000


def test_datos_fiscales_rechaza_accion_desconocida() -> None:
    client, session_factory, inmueble_id = _preparar_inmueble_fiscal()

    response = client.post(
        f"/inmuebles/{inmueble_id}/datos-fiscales",
        data=_formulario_datos_fiscales(
            accion="eliminar"
        ),
    )

    assert response.status_code == 400

    with session_factory() as session:
        registros = session.scalars(
            select(DatosFiscalesInmueble).where(
                DatosFiscalesInmueble.inmueble_id == inmueble_id
            )
        ).all()

        assert registros == []


@pytest.mark.parametrize(
    "tipo_original, tipo_nuevo, historico, permitido",
    [
        ("P", "T", "ninguno", True),
        ("T", "L", "ninguno", True),
        ("P", "T", "contrato", False),
        ("P", "T", "apunte", False),
        ("L", "T", "contrato", False),
        ("T", "L", "apunte", False),
        ("P", "L", "contrato", True),
        ("L", "G", "apunte", True),
        ("P", "P", "contrato", True),
        ("T", "T", "apunte", True),
    ],
)
def test_integridad_inmueble_cambio_tipo(
    tipo_original,
    tipo_nuevo,
    historico,
    permitido,
) -> None:
    """Protege los cambios estructurales incompatibles con el histórico."""

    client, session_factory, inmueble_id = (
        _preparar_inmueble_fiscal()
    )

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)
        inmueble.tipo = tipo_original

        if historico == "contrato":
            # El usuario registra un contrato.
            _crear_contrato_inmueble_prueba(
                session,
                inmueble,
            )

        elif historico == "apunte":
            # Se registra histórico contable.
            # Para un inmueble T sin hijos se prepara
            # directamente el registro histórico.
            session.add(
                ApunteContable(
                    inmueble=inmueble,
                    fecha=date(2025, 6, 1),
                    naturaleza="GASTO",
                    categoria="GAS_IBI",
                    concepto="Gasto histórico",
                    base=100000,
                    iva_importe=0,
                    retencion_importe=0,
                    total=100000,
                )
            )

        session.commit()

    # El usuario intenta cambiar el tipo del inmueble
    # y corregir simultáneamente su descripción.
    datos = _datos_inmueble_con_propiedad(
        tipo=tipo_nuevo,
        descripcion="Descripción corregida",
    )

    response = client.post(
        f"/inmuebles/{inmueble_id}/editar",
        data=datos,
    )

    if permitido:
        assert response.status_code == 302

    else:
        assert response.status_code == 400
        assert (
            "No se puede cambiar el tipo"
            in response.text
        )

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        if permitido:
            assert inmueble.tipo == tipo_nuevo
            assert (
                inmueble.descripcion
                == "Descripción corregida"
            )

        else:
            # La operación rechazada no modifica
            # ningún otro dato del inmueble.
            assert inmueble.tipo == tipo_original
            assert inmueble.descripcion == "Piso fiscal"


@pytest.mark.parametrize(
    "con_repartos",
    [False, True],
)
@pytest.mark.parametrize(
    "local",
    ["A", "B"],
)
@pytest.mark.parametrize(
    "modificar_participacion",
    [False, True],
)
def test_integridad_inmueble_participacion(
    con_repartos,
    local,
    modificar_participacion,
) -> None:
    """Protege las participaciones cuando existen repartos históricos."""

    (
        client,
        session_factory,
        padre_id,
        hijo_a_id,
        hijo_b_id,
    ) = _preparar_inmueble_subdividido_prueba(
        con_repartos=con_repartos,
    )

    if local == "A":
        inmueble_id = hijo_a_id
        participacion_original = 6000
        codigo = "A1"
    else:
        inmueble_id = hijo_b_id
        participacion_original = 4000
        codigo = "B1"

    participacion_propuesta = (
        participacion_original + 1000
        if modificar_participacion
        else participacion_original
    )

    # El usuario edita uno de los locales.
    datos = _datos_inmueble_con_propiedad(
        referencia=f"LOCAL-{local}",
        codigo_facturacion=codigo,
        tipo="L",
        descripcion="Descripción corregida",
        es_parte_inmueble="on",
        inmueble_padre_id=str(padre_id),
        participacion=(
            f"{participacion_propuesta / 100:.2f}"
            .replace(".", ",")
        ),
    )

    debe_rechazarse = (
        con_repartos and modificar_participacion
    )

    response = client.post(
        f"/inmuebles/{inmueble_id}/editar",
        data=datos,
    )

    if debe_rechazarse:
        assert response.status_code == 400
        assert (
            "No se puede modificar la participación"
            in response.text
        )

    else:
        assert response.status_code == 302

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        if debe_rechazarse:
            assert (
                inmueble.participacion
                == participacion_original
            )

            assert inmueble.descripcion == f"Local {local}"

        else:
            assert (
                inmueble.participacion
                == participacion_propuesta
            )

            assert (
                inmueble.descripcion
                == "Descripción corregida"
            )

        # Los repartos históricos permanecen intactos.
        distribuciones = session.scalars(
            select(DistribucionApunte)
            .order_by(
                DistribucionApunte.inmueble_id
            )
        ).all()

        if con_repartos:
            assert len(distribuciones) == 2

            assert {
                distribucion.inmueble_id: (
                    distribucion.participacion,
                    distribucion.total,
                )
                for distribucion in distribuciones
            } == {
                hijo_a_id: (6000, 60000),
                hijo_b_id: (4000, 40000),
            }

        else:
            assert distribuciones == []


@pytest.mark.parametrize(
    "con_repartos, padre_activo, permitido",
    [
        (False, True, True),
        (True, True, False),
        (False, False, False),
        (True, False, False),
    ],
)
def test_integridad_inmueble_alta_nuevo_hijo(
    con_repartos,
    padre_activo,
    permitido,
) -> None:
    """Impide ampliar subdivisiones protegidas o inactivas."""

    (
        client,
        session_factory,
        padre_id,
        hijo_a_id,
        hijo_b_id,
    ) = _preparar_inmueble_subdividido_prueba(
        con_repartos=con_repartos,
    )

    if not padre_activo:
        with session_factory() as session:
            # Preparamos una propiedad y sus hijos
            # previamente desactivados.
            for inmueble_id in (
                padre_id,
                hijo_a_id,
                hijo_b_id,
            ):
                inmueble = session.get(
                    Inmueble,
                    inmueble_id,
                )

                inmueble.activo = False

            session.commit()

    # El usuario intenta incorporar un tercer local.
    datos = _datos_inmueble_con_propiedad(
        referencia="LOCAL-C",
        codigo_facturacion="C1",
        descripcion="Local C",
        tipo="L",
        participacion="20,00",
        es_parte_inmueble="on",
        inmueble_padre_id=str(padre_id),
    )

    response = client.post(
        "/inmuebles/nuevo",
        data=datos,
    )

    if permitido:
        assert response.status_code == 302

    else:
        assert response.status_code == 400

    with session_factory() as session:
        padre = session.get(Inmueble, padre_id)

        assert len(padre.locales) == (
            3 if permitido else 2
        )

        hijo_c = session.scalar(
            select(Inmueble).where(
                Inmueble.referencia == "LOCAL-C"
            )
        )

        assert (hijo_c is not None) is permitido

        if permitido:
            assert hijo_c.inmueble_padre_id == padre_id
            assert hijo_c.participacion == 2000
            assert hijo_c.activo is True


@pytest.mark.parametrize(
    "situacion, permitido",
    [
        ("sin-contrato", True),
        ("finalizado-ayer", True),
        ("finaliza-hoy", False),
        ("finaliza-manana", False),
        ("vigente", False),
        ("vencido-no-finalizado", False),
        ("inicio-futuro", False),
    ],
)
def test_integridad_inmueble_desactivar_contrato(
    situacion,
    permitido,
) -> None:
    """Impide desactivar inmuebles con contratos no finalizados."""

    client, session_factory, inmueble_id = (
        _preparar_inmueble_fiscal()
    )

    hoy = date.today()

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        if situacion != "sin-contrato":
            fecha_inicio = hoy - timedelta(days=365)
            fecha_fin = None

            if situacion == "finalizado-ayer":
                fecha_fin = hoy - timedelta(days=1)

            elif situacion == "finaliza-hoy":
                fecha_fin = hoy

            elif situacion == "finaliza-manana":
                fecha_fin = hoy + timedelta(days=1)

            elif situacion == "inicio-futuro":
                fecha_inicio = hoy + timedelta(days=30)

            contrato = _crear_contrato_inmueble_prueba(
                session,
                inmueble,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
            )

            if situacion == "vencido-no-finalizado":
                # El vencimiento por sí solo no supone
                # la finalización del contrato.
                contrato.fecha_vencimiento = (
                    hoy - timedelta(days=1)
                )

            session.commit()

    url = f"/inmuebles/{inmueble_id}/estado"

    # El usuario abre la pantalla de confirmación.
    response = client.get(url)

    assert response.status_code == 200

    mensaje = (
        "No se puede desactivar un inmueble "
        "con contratos vigentes o de inicio futuro."
    )

    html = " ".join(response.text.split())

    assert (mensaje in html) is not permitido

    # Solo se ofrece el botón cuando la operación
    # está permitida.
    boton = re.search(
        r'<button\b[^>]*type="submit"[^>]*>'
        r'\s*Desactivar\s*</button>',
        response.text,
    )

    assert (boton is not None) is permitido

    # Se intenta realizar la operación incluso
    # cuando el botón no está disponible.
    response = client.post(url)

    assert response.status_code == (
        302 if permitido else 400
    )

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        assert inmueble.activo is not permitido


@pytest.mark.parametrize(
    "hijo_a_activo, hijo_b_activo, permitido",
    [
        (True, True, False),
        (True, False, False),
        (False, True, False),
        (False, False, True),
    ],
)
def test_integridad_inmueble_desactivar_padre(
    hijo_a_activo,
    hijo_b_activo,
    permitido,
) -> None:
    """Exige desactivar todos los hijos antes que el inmueble T."""

    (
        client,
        session_factory,
        padre_id,
        hijo_a_id,
        hijo_b_id,
    ) = _preparar_inmueble_subdividido_prueba(
        hijo_a_activo=hijo_a_activo,
        hijo_b_activo=hijo_b_activo,
    )

    url = f"/inmuebles/{padre_id}/estado"

    # El usuario solicita desactivar el inmueble T.
    response = client.get(url)

    assert response.status_code == 200

    mensaje = (
        "Para desactivar un inmueble subdividido "
        "debe desactivar previamente todos "
        "sus inmuebles hijos."
    )

    html = " ".join(response.text.split())

    assert (mensaje in html) is not permitido

    boton = re.search(
        r'<button\b[^>]*type="submit"[^>]*>'
        r'\s*Desactivar\s*</button>',
        response.text,
    )

    assert (boton is not None) is permitido

    # El servidor también debe rechazar una petición
    # directa cuando existen hijos activos.
    response = client.post(url)

    assert response.status_code == (
        302 if permitido else 400
    )

    with session_factory() as session:
        padre = session.get(Inmueble, padre_id)
        hijo_a = session.get(Inmueble, hijo_a_id)
        hijo_b = session.get(Inmueble, hijo_b_id)

        assert padre.activo is not permitido

        # No se modifica automáticamente el estado
        # de ninguno de los hijos.
        assert hijo_a.activo is hijo_a_activo
        assert hijo_b.activo is hijo_b_activo


def test_integridad_inmueble_desactivar_padre_sin_hijos(
) -> None:
    """Permite desactivar un inmueble T que todavía no tiene hijos."""

    client, session_factory, inmueble_id = (
        _preparar_inmueble_fiscal()
    )

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)
        inmueble.tipo = "T"
        session.commit()

    response = client.post(
        f"/inmuebles/{inmueble_id}/estado"
    )

    assert response.status_code == 302

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        assert inmueble.activo is False


@pytest.mark.parametrize(
    "padre_activo",
    [False, True],
)
def test_integridad_inmueble_activar_hijo(
    padre_activo,
) -> None:
    """Impide activar un local cuyo inmueble padre está inactivo."""

    (
        client,
        session_factory,
        padre_id,
        hijo_a_id,
        hijo_b_id,
    ) = _preparar_inmueble_subdividido_prueba(
        padre_activo=padre_activo,
        hijo_a_activo=False,
        hijo_b_activo=False,
    )

    url = f"/inmuebles/{hijo_a_id}/estado"

    # El usuario solicita activar un local.
    response = client.get(url)

    assert response.status_code == 200

    mensaje = (
        "Para activar este inmueble debe activar "
        "previamente el inmueble subdividido "
        "al que pertenece."
    )

    html = " ".join(response.text.split())

    assert (mensaje in html) is not padre_activo

    boton = re.search(
        r'<button\b[^>]*type="submit"[^>]*>'
        r'\s*Activar\s*</button>',
        response.text,
    )

    assert (boton is not None) is padre_activo

    # Se comprueba también la protección del servidor.
    response = client.post(url)

    assert response.status_code == (
        302 if padre_activo else 400
    )

    with session_factory() as session:
        padre = session.get(Inmueble, padre_id)
        hijo_a = session.get(Inmueble, hijo_a_id)
        hijo_b = session.get(Inmueble, hijo_b_id)

        assert padre.activo is padre_activo
        assert hijo_a.activo is padre_activo
        assert hijo_b.activo is False


def test_integridad_inmueble_activar_padre(
) -> None:
    """La activación del padre no activa automáticamente sus hijos."""

    (
        client,
        session_factory,
        padre_id,
        hijo_a_id,
        hijo_b_id,
    ) = _preparar_inmueble_subdividido_prueba(
        padre_activo=False,
        hijo_a_activo=False,
        hijo_b_activo=False,
    )

    # El usuario activa el inmueble T.
    response = client.post(
        f"/inmuebles/{padre_id}/estado"
    )

    assert response.status_code == 302

    with session_factory() as session:
        padre = session.get(Inmueble, padre_id)
        hijo_a = session.get(Inmueble, hijo_a_id)
        hijo_b = session.get(Inmueble, hijo_b_id)

        assert padre.activo is True
        assert hijo_a.activo is False
        assert hijo_b.activo is False


@pytest.mark.parametrize(
    "con_facturas",
    [False, True],
)
def test_integridad_inmueble_codigo_facturacion(
    con_facturas,
) -> None:
    """Permite corregir el código sin modificar las facturas históricas."""

    client, session_factory, inmueble_id = (
        _preparar_inmueble_fiscal()
    )

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        if con_facturas:
            contrato = _crear_contrato_inmueble_prueba(
                session,
                inmueble,
            )

            # El usuario registra una factura con
            # el código original del inmueble.
            factura = crear_factura(
                contrato=contrato,
                periodo=date(2025, 1, 1),
                fecha_emision=date(2025, 1, 1),
            )

            session.add(factura)

        session.commit()

        if con_facturas:
            factura_id = factura.id
            contrato_id = contrato.id
            numero_original = factura.numero_factura

            assert numero_original.endswith("PF1")

    # El usuario abre la edición del inmueble.
    response = client.get(
        f"/inmuebles/{inmueble_id}/editar"
    )

    assert response.status_code == 200

    mensaje = (
        "La modificación del código de facturación "
        "afectará a la numeración de las próximas facturas."
    )

    html = " ".join(response.text.split())

    assert (mensaje in html) is con_facturas

    # El usuario modifica el código de facturación
    # y la referencia del inmueble.
    datos = _datos_inmueble_con_propiedad(
        codigo_facturacion="PF2",
        referencia="PISO-CORREGIDO",
    )

    response = client.post(
        f"/inmuebles/{inmueble_id}/editar",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        assert inmueble.codigo_facturacion == "PF2"
        assert inmueble.referencia == "PISO-CORREGIDO"

        if con_facturas:
            contrato = session.get(Contrato, contrato_id)

            factura = contrato.facturas[0]

            # La numeración histórica no se modifica.
            assert factura.id == factura_id
            assert (
                factura.numero_factura
                == numero_original
            )

            # Una nueva factura utiliza el nuevo código.
            nueva_factura = crear_factura(
                contrato=contrato,
                periodo=date(2025, 2, 1),
                fecha_emision=date(2025, 2, 1),
            )

            assert (
                nueva_factura.numero_factura
                .endswith("PF2")
            )

            assert (
                nueva_factura.numero_secuencia
                == factura.numero_secuencia + 1
            )


@pytest.mark.parametrize(
    "con_repartos",
    [False, True],
)
def test_integridad_inmueble_formulario_participacion(
    con_repartos,
) -> None:
    """El formulario protege visualmente las participaciones históricas."""

    (
        client,
        _,
        _,
        hijo_a_id,
        _,
    ) = _preparar_inmueble_subdividido_prueba(
        con_repartos=con_repartos,
    )

    # El usuario abre la edición de un local.
    response = client.get(
        f"/inmuebles/{hijo_a_id}/editar"
    )

    assert response.status_code == 200

    control = re.search(
        r'<input\b[^>]*\bid="participacion"[^>]*>',
        response.text,
    )

    assert control is not None

    assert (
        "readonly" in control.group(0)
    ) is con_repartos


@pytest.mark.parametrize(
    "con_historico",
    [False, True],
)
def test_integridad_inmueble_formulario_tipo(
    con_historico,
) -> None:
    """No ofrece la conversión a T cuando existe histórico incompatible."""

    client, session_factory, inmueble_id = (
        _preparar_inmueble_fiscal()
    )

    if con_historico:
        with session_factory() as session:
            inmueble = session.get(
                Inmueble,
                inmueble_id,
            )

            _crear_apunte_inmueble_prueba(
                session,
                inmueble,
            )

            session.commit()

    # El usuario abre el formulario de edición.
    response = client.get(
        f"/inmuebles/{inmueble_id}/editar"
    )

    assert response.status_code == 200

    selector = re.search(
        r'<select\b[^>]*\bid="tipo"[^>]*>'
        r'(.*?)</select>',
        response.text,
        re.DOTALL,
    )

    assert selector is not None

    opciones = re.findall(
        r'<option\b[^>]*\bvalue="([^"]+)"',
        selector.group(1),
    )

    assert set(opciones) == (
        {"P", "L", "G"}
        if con_historico
        else {"T", "P", "L", "G"}
    )


def test_integridad_inmueble_permite_corregir_datos(
) -> None:
    """Permite corregir datos descriptivos y de propiedad con histórico."""

    client, session_factory, inmueble_id = (
        _preparar_inmueble_fiscal()
    )

    _crear_ejercicio_fiscal_prueba(
        session_factory,
        inmueble_id,
    )

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        # El inmueble tiene histórico contractual,
        # contable y fiscal.
        _crear_contrato_inmueble_prueba(
            session,
            inmueble,
        )

        _crear_apunte_inmueble_prueba(
            session,
            inmueble,
        )

        session.commit()

    # El usuario corrige los datos generales
    # y de propiedad del inmueble.
    datos = _datos_inmueble_con_propiedad(
        referencia="PISO-CORREGIDO",
        descripcion="Descripción corregida",
        direccion="Nueva dirección",
        codigo_postal="36002",
        poblacion="Vigo",
        ref_catastral="REF-CATASTRAL",
        seguro="Póliza de prueba",
        notas="Datos corregidos",
        porcentaje_titular="50,00",
        tipo_derecho="USUFRUCTO",
        porcentaje_derecho="75,00",
        fecha_adquisicion="01/01/2019",
        tipo_adquisicion="LUCRATIVA",
        importe_adquisicion="120000,00",
        gastos_adquisicion="5000,00",
    )

    response = client.post(
        f"/inmuebles/{inmueble_id}/editar",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        assert inmueble.referencia == "PISO-CORREGIDO"
        assert inmueble.descripcion == "Descripción corregida"
        assert inmueble.direccion == "Nueva dirección"
        assert inmueble.codigo_postal == "36002"
        assert inmueble.poblacion == "Vigo"
        assert inmueble.ref_catastral == "REF-CATASTRAL"
        assert inmueble.seguro == "Póliza de prueba"
        assert inmueble.notas == "Datos corregidos"

        assert inmueble.porcentaje_titular == 5000
        assert inmueble.tipo_derecho == "USUFRUCTO"
        assert inmueble.porcentaje_derecho == 7500
        assert inmueble.fecha_adquisicion == date(
            2019, 1, 1
        )
        assert inmueble.tipo_adquisicion == "LUCRATIVA"
        assert inmueble.importe_adquisicion == 12000000
        assert inmueble.gastos_adquisicion == 500000

        # El histórico contractual y contable
        # permanece asociado al mismo inmueble.
        assert len(inmueble.contratos) == 1
        assert len(inmueble.apuntes_contables) == 1

        assert (
            inmueble.apuntes_contables[0].total
            == 100000
        )

        # Los datos fiscales anuales no se modifican.
        assert len(inmueble.datos_fiscales) == 1

        fiscal = inmueble.datos_fiscales[0]

        assert fiscal.ejercicio == 2025
        assert fiscal.valor_catastral == 18000000
        assert fiscal.valor_suelo == 7000000
        assert fiscal.valor_construccion == 11000000
        assert fiscal.amortizacion_aplicada == 420000


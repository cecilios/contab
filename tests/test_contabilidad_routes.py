"""Pruebas de las rutas web del módulo contable."""

import pytest
import re

from html import unescape
from datetime import date
from sqlalchemy import select

from contab.app import create_app
from contab.database import Base
from contab.contabilidad.services import (
    ContabilidadError,
    crear_apunte_contable,
    eliminar_apunte_contable,
    modificar_apunte_contable,
)
from contab.contabilidad.routes import (
    _comprobar_documento_duplicado,
    _comprobar_continuidad_suministro,
)
from contab.conciliacion.services import (
    ConciliacionError,
    crear_movimiento_desde_apunte,
)
from contab.models import (
    ApunteContable,
    Conciliacion,
    Inmueble,
    MovimientoBancario,
    MovimientoPrevisto,
)
from contab.config import (
    CategoriaContable,
)


def _valor_input(response, nombre: str) -> str:
    """Extrae el valor de un input por su nombre o identificador."""

    coincidencia = re.search(
        rf'(?:name|id)="{re.escape(nombre)}"'
        rf'[^>]*value="([^"]*)"',
        response.text,
        re.DOTALL,
    )

    assert coincidencia is not None

    return unescape(coincidencia.group(1))



def crear_app_test():
    """Crea una aplicación contable aislada para las pruebas."""

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


def test_listado_apuntes_vacio() -> None:
    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/contabilidad/")

    assert response.status_code == 200
    assert "Apuntes contables" in response.text
    assert "No hay apuntes contables registrados." in response.text


def test_listado_muestra_apuntes_ordenados() -> None:
    app = crear_app_test()

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

        antiguo = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 8, 31),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            subcategoria=None,
            concepto="Cuota de agosto",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
        )

        reciente = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 9, 15),
            naturaleza="GASTO",
            categoria="GAS_TRIBUTOS",
            subcategoria="TRU",
            concepto="Tasa de residuos",
            base=12500,
            iva_importe=0,
            retencion_importe=0,
            total=12500,
        )

        session.add_all([
            inmueble,
            antiguo,
            reciente,
        ])
        session.commit()

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/contabilidad/")

    assert response.status_code == 200
    assert "LOCAL-1" in response.text
    assert "Tasa de residuos" in response.text
    assert "125,00" in response.text

    posicion_reciente = response.text.index(
        "Tasa de residuos"
    )
    posicion_antiguo = response.text.index(
        "Cuota de agosto"
    )

    assert posicion_reciente < posicion_antiguo


def test_listado_muestra_importes_negativos() -> None:
    app = crear_app_test()

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

        # El usuario registra un gasto normal de 100 €.
        gasto = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad octubre",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
            importe_negativo=False,
        )

        # Registra una devolución de gastos de 30,25 €.
        devolucion_gasto = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 10, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Devolución de comunidad",
            base=3025,
            iva_importe=0,
            retencion_importe=0,
            total=3025,
            importe_negativo=True,
        )

        # Registra también una regularización negativa de ingresos.
        devolucion_ingreso = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 10, 20),
            naturaleza="INGRESO",
            categoria="ING_OTRAS_RENTAS",
            concepto="Regularización de ingresos",
            base=1250,
            iva_importe=0,
            retencion_importe=0,
            total=1250,
            importe_negativo=True,
        )

        session.add_all([
            inmueble,
            gasto,
            devolucion_gasto,
            devolucion_ingreso,
        ])
        session.commit()

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario abre el listado de apuntes contables.
    response = client.get("/contabilidad/")

    assert response.status_code == 200

    # El gasto normal sigue apareciendo positivo.
    assert "Comunidad octubre" in response.text
    assert "100,00" in response.text

    # Las devoluciones deben mostrar el signo menos.
    assert "Devolución de comunidad" in response.text
    assert "-30,25" in response.text

    assert "Regularización de ingresos" in response.text
    assert "-12,50" in response.text


def test_listado_filtra_por_inmueble_y_fecha_desde() -> None:
    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        local_1 = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial 1",
            direccion="Dirección 1",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        local_2 = Inmueble(
            referencia="LOCAL-2",
            tipo="L",
            codigo_facturacion="A2",
            descripcion="Local comercial 2",
            direccion="Dirección 2",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        antiguo = ApunteContable(
            inmueble=local_1,
            fecha=date(2026, 6, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            subcategoria=None,
            concepto="Comunidad antigua",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
        )

        incluido = ApunteContable(
            inmueble=local_1,
            fecha=date(2026, 10, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            subcategoria=None,
            concepto="Comunidad incluida",
            base=11000,
            iva_importe=0,
            retencion_importe=0,
            total=11000,
        )

        otro_inmueble = ApunteContable(
            inmueble=local_2,
            fecha=date(2026, 10, 20),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            subcategoria=None,
            concepto="Comunidad otro inmueble",
            base=12000,
            iva_importe=0,
            retencion_importe=0,
            total=12000,
        )

        session.add_all([
            local_1,
            local_2,
            antiguo,
            incluido,
            otro_inmueble,
        ])
        session.commit()

        local_1_id = local_1.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.get(
        "/contabilidad/",
        query_string={
            "inmueble_id": local_1_id,
            "fecha_desde": "01/10/2026",
        },
    )

    assert response.status_code == 200
    assert "Comunidad incluida" in response.text
    assert "Comunidad antigua" not in response.text
    assert "Comunidad otro inmueble" not in response.text

    assert 'value="01/10/2026"' in response.text
    assert "LOCAL-1" in response.text
    assert "LOCAL-2" in response.text


def test_listado_rechaza_fecha_desde_invalida() -> None:
    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/contabilidad/",
        query_string={
            "fecha_desde": "31/02/2026",
        },
    )

    assert response.status_code == 400
    assert (
        "La fecha indicada no es válida"
        in response.text
    )


def test_formulario_nuevo_apunte_responde(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
ING_ALQUILERES = INGRESO | Alquileres
GAS_TRIBUTOS = GASTO | Tributos

[subcategorias_contables]
GAS_TRIBUTOS.IBI = Impuesto sobre Bienes Inmuebles
GAS_TRIBUTOS.TRU = Tasa de Residuos Urbanos
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get("/contabilidad/nuevo")

    assert response.status_code == 200
    assert "Nuevo apunte contable" in response.text
    assert "Alquileres" in response.text
    assert "Impuesto sobre Bienes Inmuebles" in response.text
    assert "Tasa de Residuos Urbanos" in response.text



def test_formulario_apunte_solo_ofrece_dos_criterios_periodo(
    tmp_path,
    monkeypatch,
) -> None:
    """El formulario permite incluir o excluir sólo la fecha final."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CONTAB_CONFIG", str(ruta))

    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    # El usuario abre el formulario de un apunte nuevo.
    response = client.get("/contabilidad/nuevo")

    assert response.status_code == 200

    # Se extraen exactamente los valores del selector de criterios.
    selector = re.search(
        r'<select\b[^>]*id="criterio_periodo"[^>]*>'
        r'(.*?)</select>',
        response.text,
        re.DOTALL,
    )

    assert selector is not None

    opciones = re.findall(
        r'<option\b[^>]*value="([^"]*)"',
        selector.group(1),
    )

    assert set(opciones) == {
        "",
        "INCLUIR_AMBOS",
        "EXCLUIR_HASTA",
    }

    assert len(opciones) == 3

    # Las etiquetas explican qué ocurre con la fecha final.
    assert "Incluir fecha final" in selector.group(1)
    assert "Excluir fecha final" in selector.group(1)



def test_formulario_apunte_muestra_indicadores_dias_periodo(
    tmp_path,
    monkeypatch,
) -> None:
    """Ofrece los días de ambos criterios para comparar con el recibo."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CONTAB_CONFIG", str(ruta))

    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    # El usuario abre el formulario antes de introducir las fechas.
    response = client.get("/contabilidad/nuevo")

    assert response.status_code == 200

    html = response.text

    # El formulario ofrece un resultado independiente por criterio.
    assert 'id="dias_incluir_hasta"' in html
    assert 'id="dias_excluir_hasta"' in html

    # Los campos de fechas están disponibles para actualizarlo.
    assert 'id="periodo_desde"' in html
    assert 'id="periodo_hasta"' in html

    # El criterio seleccionable sigue identificado inequívocamente.
    assert 'id="criterio_periodo"' in html


def test_crear_apunte_desde_formulario(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_TRIBUTOS = GASTO | Tributos

[subcategorias_contables]
GAS_TRIBUTOS.TRU = Tasa de Residuos Urbanos
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_TRIBUTOS.TRU",
        "concepto": "",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "100,00",
        "iva_importe": "21,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "Ayuntamiento",
        "tercero_nif": "",
        "referencia_documento": "TRU-2026",
        "accion": "validar",
        "crear_movimiento": "on",
        "fecha_prevista_desde": "20/09/2026",
        "fecha_prevista_hasta": "25/09/2026",
    }

    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 200
    assert "121,00" in response.text

    concepto = _valor_input(
        response,
        "concepto",
    )
    concepto_automatico = _valor_input(
        response,
        "concepto_automatico",
    )
    nombre_documento = _valor_input(
        response,
        "nombre_documento",
    )
    nombre_automatico = _valor_input(
        response,
        "nombre_documento_automatico",
    )

    assert concepto == "Tasa de Residuos Urbanos"
    assert concepto_automatico == concepto
    assert nombre_documento == ("LOCAL-1-Tasa de Residuos Urbanos.pdf")
    assert nombre_automatico == nombre_documento

    firma_validacion = _valor_input(
        response,
        "firma_validacion",
    )

    assert firma_validacion
    assert "121,00" in response.text

    # simulamos que el usuario añade un período y vuelve a validar
    datos["concepto"] = concepto
    datos["concepto_automatico"] = concepto_automatico
    datos["nombre_documento"] = nombre_documento
    datos["nombre_documento_automatico"] = (
        nombre_automatico
    )
    datos["periodo_desde"] = "09/2026"

    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 200

    concepto = _valor_input(
        response,
        "concepto",
    )
    concepto_automatico = _valor_input(
        response,
        "concepto_automatico",
    )

    assert concepto == (
        "Tasa de Residuos Urbanos 09/2026"
    )
    assert concepto_automatico == concepto

    nombre_documento = _valor_input(
        response,
        "nombre_documento",
    )
    nombre_automatico = _valor_input(
        response,
        "nombre_documento_automatico",
    )
    firma_validacion = _valor_input(
        response,
        "firma_validacion",
    )

    assert nombre_documento == (
        "LOCAL-1-Tasa de Residuos Urbanos 2026-09.pdf"
    )
    assert nombre_automatico == nombre_documento
    assert firma_validacion

    # preparar el guardado
    datos["concepto"] = concepto
    datos["concepto_automatico"] = (concepto_automatico)
    datos["nombre_documento"] = nombre_documento
    datos["nombre_documento_automatico"] = (nombre_automatico)
    datos["firma_validacion"] = firma_validacion
    datos["accion"] = "guardar"
    datos_modificados = datos.copy()
    datos_modificados["base"] = "125,00"

    response = client.post(
        "/contabilidad/nuevo",
        data=datos_modificados,
    )

    assert response.status_code == 400
    assert "han cambiado" in response.text

    with session_factory() as session:
        assert session.scalar(
            select(ApunteContable)
        ) is None

    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        apunte = session.scalar(
            select(ApunteContable)
        )

        assert apunte is not None
        assert apunte.inmueble_id == inmueble_id
        assert apunte.fecha == date(2026, 9, 15)
        assert apunte.naturaleza == "GASTO"
        assert apunte.categoria == "GAS_TRIBUTOS"
        assert apunte.subcategoria == "TRU"
        assert apunte.concepto == "Tasa de Residuos Urbanos 09/2026"
        assert apunte.periodo_desde == date(2026, 9, 1)
        assert apunte.periodo_hasta == date(2026, 9, 30)
        assert apunte.criterio_periodo == "INCLUIR_AMBOS"
        assert apunte.tratamiento == "CONTABILIZAR"
        assert apunte.nombre_documento == ("LOCAL-1-Tasa de Residuos Urbanos 2026-09.pdf")
        assert apunte.base == 10000
        assert apunte.iva_importe == 2100
        assert apunte.total == 12100

        movimiento = session.scalar(
            select(MovimientoPrevisto)
        )

        assert movimiento is not None
        assert movimiento.apunte_id == apunte.id
        assert movimiento.inmueble_id == inmueble_id
        assert movimiento.naturaleza == "GASTO"
        assert movimiento.concepto == (
            "Tasa de Residuos Urbanos 09/2026"
        )
        assert movimiento.importe_esperado == 12100
        assert movimiento.contraparte == "Ayuntamiento"
        assert movimiento.fecha_prevista_desde == date(
            2026, 9, 20
        )
        assert movimiento.fecha_prevista_hasta == date(
            2026, 9, 25
        )
        assert movimiento.estado == "PENDIENTE"
        assert movimiento.metodo_conciliacion is None


def test_crear_apunte_negativo_desde_formulario(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CONTAB_CONFIG", str(ruta))

    app = crear_app_test()
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

        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "26/10/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Devolución de comunidad",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "-30,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "Comunidad de propietarios",
        "tercero_nif": "",
        "referencia_documento": "",
        "accion": "validar",
    }

    # El usuario introduce una base negativa y pulsa Validar.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 200

    # El total calculado debe mostrarse con signo negativo.
    assert _valor_input(
        response,
        "importe_a_pagar",
    ) == "-30,00"

    nombre_documento = _valor_input(
        response,
        "nombre_documento",
    )
    firma_validacion = _valor_input(
        response,
        "firma_validacion",
    )

    assert nombre_documento
    assert firma_validacion

    # El usuario guarda el apunte después de validarlo.
    datos["nombre_documento"] = nombre_documento
    datos["firma_validacion"] = firma_validacion
    datos["accion"] = "guardar"

    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    # La base de datos conserva importes positivos y el signo aparte.
    with session_factory() as session:
        apunte = session.scalar(
            select(ApunteContable).where(
                ApunteContable.concepto
                == "Devolución de comunidad"
            )
        )

        assert apunte is not None
        assert apunte.naturaleza == "GASTO"
        assert apunte.tratamiento == "CONTABILIZAR"
        assert apunte.importe_negativo is True
        assert apunte.base == 3000
        assert apunte.total == 3000


def test_crear_apunte_repercutir_crea_movimiento_previsto(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
    [categorias_contables]
    GAS_COMUNIDAD = GASTO | Comunidad

    [subcategorias_contables]
    """.strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="EDIFICIO-COMUN",
            tipo="T",
            codigo_facturacion="EC",
            descripcion="Elementos comunes",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=10000,
        )

        local_a = Inmueble(
            referencia="LOCAL-A",
            tipo="L",
            codigo_facturacion="LA",
            descripcion="Local A",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=6000,
            inmueble_padre=inmueble,
        )

        local_b = Inmueble(
            referencia="LOCAL-B",
            tipo="L",
            codigo_facturacion="LB",
            descripcion="Local B",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=4000,
            inmueble_padre=inmueble,
        )

        session.add_all([
            inmueble,
            local_a,
            local_b,
        ])
        session.commit()

        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "08/10/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Comunidad",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "REPERCUTIR",
        "base": "100,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "comunidad.pdf",
        "tercero_nombre": "Comunidad",
        "tercero_nif": "",
        "referencia_documento": "OCT-2026",
        "crear_movimiento": "on",
        "fecha_prevista_desde": "10/10/2026",
        "fecha_prevista_hasta": "",
        "accion": "validar",
    }

    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 200

    datos["firma_validacion"] = _valor_input(
        response,
        "firma_validacion",
    )
    datos["accion"] = "guardar"

    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        apunte = session.scalar(select(ApunteContable))
        movimiento = session.scalar(select(MovimientoPrevisto))

        assert apunte is not None
        assert apunte.tratamiento == "REPERCUTIR"


        assert movimiento is not None
        assert movimiento.apunte_id == apunte.id
        assert movimiento.naturaleza == "GASTO"
        assert movimiento.importe_esperado == apunte.total
        assert movimiento.estado == "PENDIENTE"


def test_crear_apunte_sin_movimiento_previsto(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Cuota de comunidad",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "100,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "Comunidad López",
        "tercero_nif": "",
        "referencia_documento": "",
        "accion": "validar",
    }

    # El usuario valida el apunte con la generación
    # de movimiento previsto desactivada.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 200

    datos["concepto"] = _valor_input(
        response,
        "concepto",
    )
    datos["nombre_documento"] = _valor_input(
        response,
        "nombre_documento",
    )
    datos["firma_validacion"] = _valor_input(
        response,
        "firma_validacion",
    )
    datos["accion"] = "guardar"

    # El usuario guarda el apunte ya validado.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        apunte = session.scalar(
            select(ApunteContable)
        )
        movimiento = session.scalar(
            select(MovimientoPrevisto)
        )

        assert apunte is not None
        assert movimiento is None


def test_nuevo_apunte_rechaza_fechas_previstas_invertidas(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.post(
        "/contabilidad/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            "fecha": "15/09/2026",
            "clasificacion": "GAS_COMUNIDAD",
            "concepto": "Cuota de comunidad",
            "periodo_desde": "",
            "periodo_hasta": "",
            "tratamiento": "CONTABILIZAR",
            "base": "100,00",
            "iva_importe": "0,00",
            "retencion_importe": "0,00",
            "nombre_documento": "",
            "tercero_nombre": "Comunidad López",
            "tercero_nif": "",
            "referencia_documento": "",
            "crear_movimiento": "on",
            "fecha_prevista_desde": "20/09/2026",
            "fecha_prevista_hasta": "19/09/2026",
            "accion": "validar",
        },
    )

    assert response.status_code == 400
    assert (
        "La fecha prevista final no puede ser anterior"
        in response.text
    )


def test_nuevo_apunte_ignora_fechas_previstas_si_no_crea_movimiento(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.post(
        "/contabilidad/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            "fecha": "15/09/2026",
            "clasificacion": "GAS_COMUNIDAD",
            "concepto": "Cuota de comunidad",
            "periodo_desde": "",
            "periodo_hasta": "",
            "tratamiento": "CONTABILIZAR",
            "base": "100,00",
            "iva_importe": "0,00",
            "retencion_importe": "0,00",
            "nombre_documento": "",
            "tercero_nombre": "Comunidad López",
            "tercero_nif": "",
            "referencia_documento": "",
            "fecha_prevista_desde": "fecha incorrecta",
            "fecha_prevista_hasta": "otra fecha incorrecta",
            "accion": "validar",
        },
    )

    assert response.status_code == 200
    assert _valor_input(
        response,
        "firma_validacion",
    )


def test_nuevo_apunte_exige_revalidar_si_cambian_fechas_previstas(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Cuota de comunidad",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "100,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "Comunidad López",
        "tercero_nif": "",
        "referencia_documento": "",
        "crear_movimiento": "on",
        "fecha_prevista_desde": "20/09/2026",
        "fecha_prevista_hasta": "",
        "accion": "validar",
    }

    # El usuario valida el formulario.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 200

    datos["nombre_documento"] = _valor_input(
        response,
        "nombre_documento",
    )
    datos["firma_validacion"] = _valor_input(
        response,
        "firma_validacion",
    )

    # Cambia la fecha prevista después de validar.
    datos["fecha_prevista_desde"] = "21/09/2026"
    datos["accion"] = "guardar"

    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 400
    assert "han cambiado" in response.text

    with session_factory() as session:
        assert session.scalar(
            select(ApunteContable)
        ) is None


def test_crear_apunte_invalido_no_guarda_datos(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.post(
        "/contabilidad/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            "fecha": "fecha incorrecta",
            "clasificacion": "GAS_COMUNIDAD",
            "concepto": "Cuota de comunidad",
            "base": "100,00",
            "iva_importe": "0,00",
            "retencion_importe": "0,00",
            "tercero_nombre": "",
            "tercero_nif": "",
            "referencia_documento": "",
            "ruta_documento": "",
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert "La fecha indicada no es válida" in response.text
    assert "Cuota de comunidad" in response.text

    with session_factory() as session:
        assert session.scalar(
            select(ApunteContable)
        ) is None


def test_formulario_editar_apunte_muestra_datos(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_TRIBUTOS = GASTO | Tributos

[subcategorias_contables]
GAS_TRIBUTOS.TRU = Tasa de Residuos Urbanos
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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

        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 9, 15),
            naturaleza="GASTO",
            categoria="GAS_TRIBUTOS",
            subcategoria="TRU",
            concepto="Tasa de residuos",
            base=10000,
            iva_importe=2100,
            retencion_importe=0,
            total=12100,
        )

        session.add_all([inmueble, apunte])
        session.commit()
        apunte_id = apunte.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.get(
        f"/contabilidad/{apunte_id}/editar"
    )

    assert response.status_code == 200
    assert "Editar apunte contable" in response.text
    assert 'value="15/09/2026"' in response.text
    assert 'value="Tasa de residuos"' in response.text
    assert 'value="100,00"' in response.text
    assert 'value="21,00"' in response.text
    assert 'value="GAS_TRIBUTOS.TRU"' in response.text
    assert "selected" in response.text


def test_editar_apunte_guarda_cambios(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad
GAS_TRIBUTOS = GASTO | Tributos

[subcategorias_contables]
GAS_TRIBUTOS.IBI = Impuesto sobre Bienes Inmuebles
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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

        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 9, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            subcategoria=None,
            concepto="Cuota provisional",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
        )

        session.add_all([inmueble, apunte])
        session.commit()

        apunte_id = apunte.id
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "30/09/2026",
        "clasificacion": "GAS_TRIBUTOS.IBI",
        "concepto": "IBI 2026",
        "periodo_desde": "09/2026",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "200,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "Ayuntamiento",
        "tercero_nif": "",
        "referencia_documento": "IBI-2026",
        "accion": "validar",
    }

    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos,
    )

    assert response.status_code == 200

    nombre_documento = _valor_input(
        response,
        "nombre_documento",
    )
    firma_validacion = _valor_input(
        response,
        "firma_validacion",
    )

    assert nombre_documento == (
        "LOCAL-1-IBI 2026 2026-09.pdf"
    )
    assert firma_validacion

    datos["nombre_documento"] = nombre_documento
    datos["firma_validacion"] = firma_validacion
    datos["accion"] = "guardar"

    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        apunte = session.get(
            ApunteContable,
            apunte_id,
        )

        assert apunte is not None
        assert apunte.fecha == date(2026, 9, 30)
        assert apunte.categoria == "GAS_TRIBUTOS"
        assert apunte.subcategoria == "IBI"
        assert apunte.concepto == "IBI 2026"
        assert apunte.periodo_desde == date(2026, 9, 1)
        assert apunte.periodo_hasta == date(2026, 9, 30)
        assert apunte.tratamiento == "CONTABILIZAR"
        assert apunte.nombre_documento == (
            "LOCAL-1-IBI 2026 2026-09.pdf"
        )
        assert apunte.base == 20000
        assert apunte.iva_importe == 0
        assert apunte.total == 20000
        assert apunte.tercero_nombre == "Ayuntamiento"


def test_editar_apunte_negativo_muestra_importes_con_signo(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CONTAB_CONFIG", str(ruta))

    app = crear_app_test()
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

        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 10, 26),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Devolución de comunidad",
            base=3000,
            iva_importe=0,
            retencion_importe=0,
            total=3000,
            importe_negativo=True,
        )

        session.add_all([inmueble, apunte])
        session.commit()
        apunte_id = apunte.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # El usuario abre la edición de un apunte negativo.
    response = client.get(
        f"/contabilidad/{apunte_id}/editar"
    )

    assert response.status_code == 200

    # La base y el total se presentan con signo negativo.
    assert _valor_input(
        response,
        "base",
    ) == "-30,00"

    assert _valor_input(
        response,
        "importe_a_pagar",
    ) == "-30,00"

    # Consultar el formulario no altera los valores almacenados.
    with session_factory() as session:
        apunte = session.get(
            ApunteContable,
            apunte_id,
        )

        assert apunte.importe_negativo is True
        assert apunte.base == 3000
        assert apunte.total == 3000


@pytest.mark.parametrize(
    ("negativo_inicial", "base_formulario"),
    [
        (False, "-30,00"),
        (True, "-30,00"),
    ],
)
def test_editar_apunte_guarda_signo_y_actualiza_previsto(
    tmp_path,
    monkeypatch,
    negativo_inicial: bool,
    base_formulario: str,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("CONTAB_CONFIG", str(ruta))

    app = crear_app_test()
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

        # Existe un apunte con un movimiento previsto pendiente.
        apunte = crear_apunte_contable(
            inmueble=inmueble,
            categorias={
                "GAS_COMUNIDAD": CategoriaContable(
                    codigo="GAS_COMUNIDAD",
                    naturaleza="GASTO",
                    nombre="Comunidad",
                    activa=True,
                    subcategorias=(),
                ),
            },
            fecha=date(2026, 10, 26),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Cuota de comunidad",
            base=3000,
            importe_negativo=negativo_inicial,
        )

        movimiento = crear_movimiento_desde_apunte(
            apunte=apunte,
        )

        session.add_all([apunte, movimiento])
        session.commit()

        apunte_id = apunte.id
        movimiento_id = movimiento.id
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # El usuario abre la edición del apunte.
    response = client.get(
        f"/contabilidad/{apunte_id}/editar"
    )

    assert response.status_code == 200

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "26/10/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Devolución de comunidad",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": base_formulario,
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "",
        "tercero_nif": "",
        "referencia_documento": "",
        "accion": "validar",
    }

    # El usuario valida los datos negativos.
    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos,
    )

    assert response.status_code == 200
    assert _valor_input(
        response,
        "importe_a_pagar",
    ) == "-30,00"

    nombre_documento = _valor_input(
        response,
        "nombre_documento",
    )
    firma_validacion = _valor_input(
        response,
        "firma_validacion",
    )

    assert nombre_documento
    assert firma_validacion

    # El usuario guarda los datos validados.
    datos["nombre_documento"] = nombre_documento
    datos["firma_validacion"] = firma_validacion
    datos["accion"] = "guardar"

    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos,
    )

    assert response.status_code == 302

    # El apunte conserva los importes positivos y el signo aparte.
    with session_factory() as session:
        apunte = session.get(ApunteContable, apunte_id)
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        assert apunte is not None
        assert apunte.importe_negativo is True
        assert apunte.base == 3000
        assert apunte.total == 3000
        assert apunte.concepto == "Devolución de comunidad"

        # El movimiento previsto se sincroniza sin duplicarse.
        assert movimiento is not None
        assert movimiento.naturaleza == "INGRESO"
        assert movimiento.importe_esperado == 3000
        assert movimiento.estado == "PENDIENTE"

        movimientos = session.scalars(
            select(MovimientoPrevisto).where(
                MovimientoPrevisto.apunte_id == apunte_id
            )
        ).all()

        assert len(movimientos) == 1
        assert movimientos[0].id == movimiento_id


def test_eliminar_apunte_con_movimiento_conciliado_falla(
    session,
    inmueble,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
    )

    movimiento = crear_movimiento_desde_apunte(
        apunte=apunte,
        fecha_prevista_desde=date(2026, 9, 5),
    )
    movimiento.estado = "CONCILIADO"

    session.add_all([apunte, movimiento])
    session.commit()

    apunte_id = apunte.id
    movimiento_id = movimiento.id

    with pytest.raises(
        ContabilidadError,
        match="movimientos conciliados",
    ):
        eliminar_apunte_contable(
            session,
            apunte,
        )

    session.rollback()

    assert session.get(
        ApunteContable,
        apunte_id,
    ) is not None

    assert session.get(
        MovimientoPrevisto,
        movimiento_id,
    ) is not None


def test_eliminar_apunte_contable(
    session,
    inmueble,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
    )

    session.add(apunte)
    session.commit()
    apunte_id = apunte.id

    eliminar_apunte_contable(
        session,
        apunte,
    )
    session.commit()

    assert session.get(
        ApunteContable,
        apunte_id,
    ) is None


def test_eliminar_apunte_con_movimiento_parcial_falla(
    session,
    inmueble,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
    )

    movimiento = crear_movimiento_desde_apunte(
        apunte=apunte,
        fecha_prevista_desde=date(2026, 9, 5),
    )
    movimiento.estado = "PARCIAL"

    session.add_all([apunte, movimiento])
    session.commit()

    apunte_id = apunte.id
    movimiento_id = movimiento.id

    with pytest.raises(
        ContabilidadError,
        match="conciliados",
    ):
        eliminar_apunte_contable(
            session,
            apunte,
        )

    session.rollback()

    assert session.get(
        ApunteContable,
        apunte_id,
    ) is not None

    assert session.get(
        MovimientoPrevisto,
        movimiento_id,
    ) is not None


def test_eliminar_apunte_desde_interfaz() -> None:
    app = crear_app_test()

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

        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 9, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            subcategoria=None,
            concepto="Cuota de comunidad",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
        )

        session.add_all([inmueble, apunte])
        session.commit()
        apunte_id = apunte.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.get(
        f"/contabilidad/{apunte_id}/eliminar"
    )

    assert response.status_code == 200
    assert "Eliminar apunte contable" in response.text
    assert "Cuota de comunidad" in response.text

    response = client.post(
        f"/contabilidad/{apunte_id}/eliminar"
    )

    assert response.status_code == 302

    with session_factory() as session:
        assert session.get(
            ApunteContable,
            apunte_id,
        ) is None


def test_eliminar_apunte_elimina_movimiento_pendiente(
    session,
    inmueble,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
    )

    movimiento = crear_movimiento_desde_apunte(
        apunte=apunte,
        fecha_prevista_desde=date(2026, 9, 5),
    )

    session.add_all([apunte, movimiento])
    session.commit()

    apunte_id = apunte.id
    movimiento_id = movimiento.id

    eliminar_apunte_contable(
        session,
        apunte,
    )
    session.commit()

    assert session.get(
        ApunteContable,
        apunte_id,
    ) is None

    assert session.get(
        MovimientoPrevisto,
        movimiento_id,
    ) is None


def test_documento_duplicado_en_mismo_inmueble_bloquea(
    session,
    inmueble,
) -> None:
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
        tercero_nombre="Comunidad López",
        tercero_nif="H12345678",
        referencia_documento="F-125",
    )

    session.add(apunte)
    session.commit()

    with pytest.raises(
        ContabilidadError,
        match="Ya existe",
    ):
        _comprobar_documento_duplicado(
            session,
            inmueble=inmueble,
            valores={
                "tercero_nombre": "Comunidad López",
                "tercero_nif": "H12345678",
                "referencia_documento": "F-125",
            },
        )


def test_documento_duplicado_en_otro_inmueble_avisa(
    session,
    inmueble,
) -> None:
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
        tercero_nombre="Comunidad López",
        tercero_nif="H12345678",
        referencia_documento="F-125",
    )

    otro_inmueble = Inmueble(
        referencia="LOCAL-2",
        tipo="L",
        codigo_facturacion="A2",
        descripcion="Segundo local",
        direccion="Dirección 2",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    session.add_all([
        apunte,
        otro_inmueble,
    ])
    session.commit()

    aviso = _comprobar_documento_duplicado(
        session,
        inmueble=otro_inmueble,
        valores={
            "tercero_nombre": "Comunidad López",
            "tercero_nif": "H12345678",
            "referencia_documento": "F-125",
        },
    )

    assert aviso is not None
    assert inmueble.referencia in aviso
    assert "Puede guardarlo" in aviso


def test_eliminar_apunte_conciliado_desde_interfaz_muestra_error() -> None:
    """Vuelve a mostrar la confirmación si el apunte no puede eliminarse."""
    app = crear_app_test()
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    # Preparamos un apunte con un movimiento ya conciliado.
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
        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 9, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            subcategoria=None,
            concepto="Cuota de comunidad",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
            tercero_nombre="",
        )
        movimiento = crear_movimiento_desde_apunte(
            apunte=apunte,
            fecha_prevista_desde=date(2026, 9, 20),
        )
        movimiento.estado = "CONCILIADO"

        session.add_all(
            [inmueble, apunte, movimiento]
        )
        session.commit()

        apunte_id = apunte.id

    client = app.test_client()
    client.post(
        "/",
        data={"database": "test"},
    )

    # Intentamos eliminarlo desde la interfaz.
    response = client.post(
        f"/contabilidad/{apunte_id}/eliminar"
    )

    assert response.status_code == 400
    assert "movimientos conciliados" in response.text
    assert "Cuota de comunidad" in response.text
    assert 'method="post"' in response.text

    # El apunte debe continuar en la base de datos.
    with session_factory() as session:
        assert session.get(
            ApunteContable,
            apunte_id,
        ) is not None


def test_crear_movimiento_previsto_sin_fechas_no_usa_fecha_apunte(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Cuota de comunidad",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "100,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "Comunidad López",
        "tercero_nif": "",
        "referencia_documento": "",
        "crear_movimiento": "on",
        "fecha_prevista_desde": "",
        "fecha_prevista_hasta": "",
        "accion": "validar",
    }

    # El usuario valida el apunte sin indicar
    # ninguna fecha prevista de pago.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 200

    datos["concepto"] = _valor_input(
        response,
        "concepto",
    )
    datos["nombre_documento"] = _valor_input(
        response,
        "nombre_documento",
    )
    datos["firma_validacion"] = _valor_input(
        response,
        "firma_validacion",
    )
    datos["accion"] = "guardar"

    # El usuario guarda el apunte ya validado.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        movimiento = session.scalar(
            select(MovimientoPrevisto)
        )

        assert movimiento is not None
        assert movimiento.fecha_prevista_desde is None
        assert movimiento.fecha_prevista_hasta is None


def test_crear_movimiento_previsto_con_solo_fecha_desde(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Cuota de comunidad",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "100,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "Comunidad López",
        "tercero_nif": "",
        "referencia_documento": "",
        "crear_movimiento": "on",
        "fecha_prevista_desde": "20/09/2026",
        "fecha_prevista_hasta": "",
        "accion": "validar",
    }

    # El usuario valida el apunte sin indicar
    # ninguna fecha prevista de pago.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 200

    datos["concepto"] = _valor_input(
        response,
        "concepto",
    )
    datos["nombre_documento"] = _valor_input(
        response,
        "nombre_documento",
    )
    datos["firma_validacion"] = _valor_input(
        response,
        "firma_validacion",
    )
    datos["accion"] = "guardar"

    # El usuario guarda el apunte ya validado.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        movimiento = session.scalar(
            select(MovimientoPrevisto)
        )

        assert movimiento is not None
        assert movimiento.fecha_prevista_desde == date(2026, 9, 20)
        assert movimiento.fecha_prevista_hasta is None


def test_nuevo_apunte_rechaza_fecha_prevista_hasta_sin_desde(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    response = client.post(
        "/contabilidad/nuevo",
        data={
            "inmueble_id": str(inmueble_id),
            "fecha": "15/09/2026",
            "clasificacion": "GAS_COMUNIDAD",
            "concepto": "Cuota de comunidad",
            "periodo_desde": "",
            "periodo_hasta": "",
            "tratamiento": "CONTABILIZAR",
            "base": "100,00",
            "iva_importe": "0,00",
            "retencion_importe": "0,00",
            "nombre_documento": "",
            "tercero_nombre": "Comunidad López",
            "tercero_nif": "",
            "referencia_documento": "",
            "crear_movimiento": "on",
            "fecha_prevista_desde": "",
            "fecha_prevista_hasta": "25/09/2026",
            "accion": "validar",
        },
    )

    assert response.status_code == 400
    assert (
        "La fecha prevista final requiere una fecha inicial."
        in response.text
    )

    with session_factory() as session:
        assert session.scalar(
            select(ApunteContable)
        ) is None

        assert session.scalar(
            select(MovimientoPrevisto)
        ) is None


def test_nuevo_apunte_exige_revalidar_si_se_desactiva_movimiento(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Cuota de comunidad",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "100,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "Comunidad López",
        "tercero_nif": "",
        "referencia_documento": "",
        "crear_movimiento": "on",
        "fecha_prevista_desde": "20/09/2026",
        "fecha_prevista_hasta": "",
        "accion": "validar",
    }

    # El usuario valida el apunte sin indicar
    # ninguna fecha prevista de pago.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 200

    datos["concepto"] = _valor_input(
        response,
        "concepto",
    )
    datos["nombre_documento"] = _valor_input(
        response,
        "nombre_documento",
    )
    datos["firma_validacion"] = _valor_input(
        response,
        "firma_validacion",
    )

    # Después de validar, el usuario desmarca
    # la generación del movimiento previsto.
    datos.pop("crear_movimiento")
    datos["accion"] = "guardar"

    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 400
    assert "han cambiado" in response.text

    with session_factory() as session:
        assert session.scalar(
            select(ApunteContable)
        ) is None

        assert session.scalar(
            select(MovimientoPrevisto)
        ) is None


def test_modificar_apunte_sincroniza_movimiento_pendiente(
    session,
    inmueble,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota antigua",
        base=10000,
        tercero_nombre="Comunidad antigua",
    )

    movimiento = crear_movimiento_desde_apunte(
        apunte=apunte,
        fecha_prevista_desde=date(2026, 9, 5),
        fecha_prevista_hasta=date(2026, 9, 10),
        notas="Nota existente",
    )

    session.add_all([apunte, movimiento])
    session.commit()

    modificar_apunte_contable(
        session,
        apunte=apunte,
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 2),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota corregida",
        base=12000,
        tercero_nombre="Comunidad corregida",
    )

    assert movimiento.inmueble is inmueble
    assert movimiento.naturaleza == "GASTO"
    assert movimiento.concepto == "Cuota corregida"
    assert movimiento.importe_esperado == 12000
    assert movimiento.contraparte == "Comunidad corregida"

    assert movimiento.fecha_prevista_desde == date(
        2026, 9, 5
    )
    assert movimiento.fecha_prevista_hasta == date(
        2026, 9, 10
    )
    assert movimiento.estado == "PENDIENTE"
    assert movimiento.metodo_conciliacion is None
    assert movimiento.notas == "Nota existente"


def test_modificar_apunte_sincroniza_movimiento_cancelado(
    session,
    inmueble,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota antigua",
        base=10000,
    )

    movimiento = crear_movimiento_desde_apunte(
        apunte=apunte,
        fecha_prevista_desde=date(2026, 9, 5),
    )
    movimiento.estado = "CANCELADO"

    session.add_all([apunte, movimiento])
    session.commit()

    modificar_apunte_contable(
        session,
        apunte=apunte,
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota corregida",
        base=12000,
        tercero_nombre="Comunidad López",
    )

    assert movimiento.concepto == "Cuota corregida"
    assert movimiento.importe_esperado == 12000
    assert movimiento.contraparte == "Comunidad López"
    assert movimiento.estado == "CANCELADO"
    assert movimiento.fecha_prevista_desde == date(
        2026, 9, 5
    )


def test_modificar_apunte_conciliado_permite_datos_descriptivos(
    session,
    inmueble,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota antigua",
        base=10000,
        tercero_nombre="Comunidad antigua",
    )

    movimiento = crear_movimiento_desde_apunte(
        apunte=apunte,
        fecha_prevista_desde=date(2026, 9, 5),
    )
    movimiento.estado = "CONCILIADO"
    movimiento.metodo_conciliacion = "MANUAL"
    movimiento.notas = "Pagado en efectivo"

    session.add_all([apunte, movimiento])
    session.commit()

    modificar_apunte_contable(
        session,
        apunte=apunte,
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 2),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota corregida",
        base=10000,
        tercero_nombre="Comunidad corregida",
    )

    assert movimiento.concepto == "Cuota corregida"
    assert movimiento.contraparte == "Comunidad corregida"

    assert movimiento.estado == "CONCILIADO"
    assert movimiento.metodo_conciliacion == "MANUAL"
    assert movimiento.notas == "Pagado en efectivo"
    assert movimiento.fecha_prevista_desde == date(
        2026, 9, 5
    )


@pytest.mark.parametrize(
    "cambio",
    [
        "importe",
        "inmueble",
        "naturaleza",
    ],
)
def test_modificar_apunte_conciliado_rechaza_cambios_economicos(
    session,
    inmueble,
    cambio,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
        "ING_OTROS": CategoriaContable(
            codigo="ING_OTROS",
            naturaleza="INGRESO",
            nombre="Otros ingresos",
            activa=True,
            subcategorias=(),
        ),
    }

    otro_inmueble = Inmueble(
        referencia="LOCAL-2",
        tipo="L",
        codigo_facturacion="A2",
        descripcion="Segundo local",
        direccion="Dirección 2",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )
    session.add(otro_inmueble)

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
    )

    movimiento = crear_movimiento_desde_apunte(
        apunte=apunte,
        fecha_prevista_desde=date(2026, 9, 5),
    )
    movimiento.estado = "CONCILIADO"
    movimiento.metodo_conciliacion = "MANUAL"
    movimiento.notas = "Pagado en efectivo"

    session.add_all([apunte, movimiento])
    session.commit()

    inmueble_nuevo = inmueble
    naturaleza = "GASTO"
    categoria = "GAS_COMUNIDAD"
    base = 10000

    if cambio == "importe":
        base = 12000

    elif cambio == "inmueble":
        inmueble_nuevo = otro_inmueble

    elif cambio == "naturaleza":
        naturaleza = "INGRESO"
        categoria = "ING_OTROS"

    with pytest.raises(
        ContabilidadError,
        match="conciliado",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            inmueble=inmueble_nuevo,
            categorias=categorias,
            fecha=date(2026, 9, 1),
            naturaleza=naturaleza,
            categoria=categoria,
            concepto="Cuota de comunidad",
            base=base,
        )


def test_modificar_apunte_parcial_rechaza_cambio_importe(
    session,
    inmueble,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
    )

    movimiento = crear_movimiento_desde_apunte(
        apunte=apunte,
        fecha_prevista_desde=date(2026, 9, 5),
    )
    movimiento.estado = "PARCIAL"

    session.add_all([apunte, movimiento])
    session.commit()

    with pytest.raises(
        ContabilidadError,
        match="conciliado",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            inmueble=inmueble,
            categorias=categorias,
            fecha=date(2026, 9, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Cuota de comunidad",
            base=12000,
        )


def test_editar_apunte_conciliado_sincroniza_datos_descriptivos(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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

        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 9, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            subcategoria=None,
            concepto="Cuota antigua",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
            tercero_nombre="Comunidad antigua",
        )

        movimiento = crear_movimiento_desde_apunte(
            apunte=apunte,
            fecha_prevista_desde=date(2026, 9, 20),
            fecha_prevista_hasta=date(2026, 9, 25),
        )
        movimiento.estado = "CONCILIADO"
        movimiento.metodo_conciliacion = "MANUAL"
        movimiento.notas = "Pagado en efectivo"

        session.add_all([
            inmueble,
            apunte,
            movimiento,
        ])
        session.commit()

        apunte_id = apunte.id
        movimiento_id = movimiento.id
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Cuota corregida",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "100,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "Comunidad corregida",
        "tercero_nif": "",
        "referencia_documento": "",
        "accion": "validar",
    }

    # El usuario valida los cambios descriptivos.
    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos,
    )

    assert response.status_code == 200

    datos["concepto"] = _valor_input(
        response,
        "concepto",
    )
    datos["nombre_documento"] = _valor_input(
        response,
        "nombre_documento",
    )
    datos["firma_validacion"] = _valor_input(
        response,
        "firma_validacion",
    )
    datos["accion"] = "guardar"

    # El usuario guarda el apunte ya validado.
    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        apunte = session.get(
            ApunteContable,
            apunte_id,
        )
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        assert apunte is not None
        assert movimiento is not None

        assert apunte.concepto == "Cuota corregida"
        assert apunte.tercero_nombre == (
            "Comunidad corregida"
        )

        assert movimiento.concepto == "Cuota corregida"
        assert movimiento.contraparte == (
            "Comunidad corregida"
        )

        assert movimiento.importe_esperado == 10000
        assert movimiento.estado == "CONCILIADO"
        assert movimiento.metodo_conciliacion == "MANUAL"
        assert movimiento.notas == "Pagado en efectivo"
        assert movimiento.fecha_prevista_desde == date(
            2026, 9, 20
        )
        assert movimiento.fecha_prevista_hasta == date(
            2026, 9, 25
        )


def test_editar_apunte_conciliado_rechaza_cambio_importe(
    tmp_path,
    monkeypatch,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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

        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 9, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            subcategoria=None,
            concepto="Cuota de comunidad",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
            tercero_nombre="Comunidad López",
        )

        movimiento = crear_movimiento_desde_apunte(
            apunte=apunte,
            fecha_prevista_desde=date(2026, 9, 20),
        )
        movimiento.estado = "CONCILIADO"
        movimiento.metodo_conciliacion = "MANUAL"
        movimiento.notas = "Pagado en efectivo"

        session.add_all([
            inmueble,
            apunte,
            movimiento,
        ])
        session.commit()

        inmueble_id = inmueble.id
        apunte_id = apunte.id
        movimiento_id = movimiento.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Cuota de comunidad",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "120,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "Comunidad López",
        "tercero_nif": "",
        "referencia_documento": "",
        "accion": "validar",
    }

    # El usuario intenta validar un cambio que altera
    # el importe ya conciliado.
    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos,
    )

    assert response.status_code == 400
    assert (
        "No puede cambiarse el inmueble, la naturaleza "
        "o el importe"
        in response.text
    )

    assert 'name="firma_validacion"' not in response.text
    assert 'value="guardar"' not in response.text

    # Ni el apunte ni su movimiento deben haber cambiado.
    with session_factory() as session:
        apunte = session.get(
            ApunteContable,
            apunte_id,
        )
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        assert apunte is not None
        assert movimiento is not None

        assert apunte.total == 10000
        assert movimiento.importe_esperado == 10000

        assert movimiento.estado == "CONCILIADO"
        assert movimiento.metodo_conciliacion == "MANUAL"
        assert movimiento.notas == "Pagado en efectivo"


def test_flujo_apunte_conciliacion_automatica_protege_importe(
    tmp_path,
    monkeypatch,
) -> None:
    # Test de integración. Comprueba una ruta completa y cada paso es una acción
    # del usuario: alta contable → generación del previsto → propuesta automática →
    # confirmación → conciliación persistente → protección posterior del apunte.
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

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
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Comunidad septiembre",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "100,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "C.P. Local Prueba",
        "tercero_nif": "",
        "referencia_documento": "",
        "crear_movimiento": "on",
        "fecha_prevista_desde": "20/09/2026",
        "fecha_prevista_hasta": "25/09/2026",
        "accion": "validar",
    }

    # El usuario valida el apunte y su movimiento previsto.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 200

    datos["concepto"] = _valor_input(
        response,
        "concepto",
    )
    datos["nombre_documento"] = _valor_input(
        response,
        "nombre_documento",
    )
    datos["firma_validacion"] = _valor_input(
        response,
        "firma_validacion",
    )
    datos["accion"] = "guardar"

    # El usuario guarda el apunte ya validado.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        apunte = session.scalar(
            select(ApunteContable)
        )
        movimiento_previsto = session.scalar(
            select(MovimientoPrevisto)
        )

        assert apunte is not None
        assert movimiento_previsto is not None
        assert movimiento_previsto.apunte_id == apunte.id
        assert movimiento_previsto.estado == "PENDIENTE"

        apunte_id = apunte.id
        movimiento_previsto_id = movimiento_previsto.id

        movimiento_bancario = MovimientoBancario(
            fecha=date(2026, 9, 22),
            naturaleza="GASTO",
            importe=10000,
            tipo_original="RECIBO",
            descripcion_original="C.P. LOCAL PRUEBA",
            referencia_bancaria="",
            huella_importacion="a" * 64,
            estado="PENDIENTE",
        )

        session.add(movimiento_bancario)
        session.commit()

        movimiento_bancario_id = movimiento_bancario.id

    # El usuario revisa las propuestas automáticas.
    response = client.get(
        "/conciliacion/revisar"
    )

    assert response.status_code == 200
    assert "Comunidad septiembre" in response.text
    assert "C.P. LOCAL PRUEBA" in response.text


    # El usuario acepta individualmente la propuesta exacta.
    response = client.post(
        (
            "/conciliacion/revisar/"
            f"{movimiento_bancario_id}/aceptar"
        ),
        data={
            "previsto_id": movimiento_previsto_id,
        },
    )

    assert response.status_code == 302
    assert response.location.endswith(
        "/conciliacion/revisar"
    )

    with session_factory() as session:
        movimiento_previsto = session.get(
            MovimientoPrevisto,
            movimiento_previsto_id,
        )
        movimiento_bancario = session.get(
            MovimientoBancario,
            movimiento_bancario_id,
        )
        conciliacion = session.scalar(
            select(Conciliacion)
        )

        assert movimiento_previsto is not None
        assert movimiento_bancario is not None
        assert conciliacion is not None

        assert movimiento_previsto.estado == "CONCILIADO"
        assert (
            movimiento_previsto.metodo_conciliacion
            == "INDIVIDUAL"
        )
        assert movimiento_bancario.estado == "CONCILIADO"

        assert (
            conciliacion.movimiento_previsto_id
            == movimiento_previsto_id
        )
        assert (
            conciliacion.movimiento_bancario_id
            == movimiento_bancario_id
        )
        assert conciliacion.importe_asociado == 10000

    datos_edicion = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Comunidad septiembre",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "120,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "C.P. Local Prueba",
        "tercero_nif": "",
        "referencia_documento": "",
        "accion": "validar",
    }

    # Tras conciliar, el usuario intenta cambiar el importe.
    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos_edicion,
    )

    assert response.status_code == 400
    assert (
        "No puede cambiarse el inmueble, la naturaleza "
        "o el importe"
        in response.text
    )
    assert 'value="guardar"' not in response.text

    # El rechazo no altera ninguna parte de la conciliación.
    with session_factory() as session:
        apunte = session.get(
            ApunteContable,
            apunte_id,
        )
        movimiento_previsto = session.get(
            MovimientoPrevisto,
            movimiento_previsto_id,
        )
        movimiento_bancario = session.get(
            MovimientoBancario,
            movimiento_bancario_id,
        )
        conciliacion = session.scalar(
            select(Conciliacion)
        )

        assert apunte is not None
        assert movimiento_previsto is not None
        assert movimiento_bancario is not None
        assert conciliacion is not None

        assert apunte.total == 10000
        assert movimiento_previsto.importe_esperado == 10000
        assert movimiento_previsto.estado == "CONCILIADO"
        assert (
            movimiento_previsto.metodo_conciliacion
            == "INDIVIDUAL"
        )
        assert movimiento_bancario.estado == "CONCILIADO"
        assert conciliacion.importe_asociado == 10000


def test_flujo_apunte_conciliacion_manual_sincroniza_descripcion(
    tmp_path,
    monkeypatch,
) -> None:
    # Test de integración. Comprueba una ruta completa y cada paso es una acción
    # del usuario: crear apunte → generar previsto → conciliar manualmente →
    # editar datos descriptivos del apunte → sincronizar previsto conservando
    # conciliación manual, notas y fechas.
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_TRIBUTOS = GASTO | Tributos

[subcategorias_contables]
GAS_TRIBUTOS.IBI = IBI
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()
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
        session.add(inmueble)
        session.commit()
        inmueble_id = inmueble.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_TRIBUTOS.IBI",
        "concepto": "IBI local",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "250,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "Ayuntamiento",
        "tercero_nif": "",
        "referencia_documento": "",
        "crear_movimiento": "on",
        "fecha_prevista_desde": "20/09/2026",
        "fecha_prevista_hasta": "30/09/2026",
        "accion": "validar",
    }

    # El usuario valida el apunte y su movimiento previsto.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 200

    datos["concepto"] = _valor_input(
        response,
        "concepto",
    )
    datos["nombre_documento"] = _valor_input(
        response,
        "nombre_documento",
    )
    datos["firma_validacion"] = _valor_input(
        response,
        "firma_validacion",
    )
    datos["accion"] = "guardar"

    # El usuario guarda el apunte.
    response = client.post(
        "/contabilidad/nuevo",
        data=datos,
    )

    assert response.status_code == 302

    with session_factory() as session:
        apunte = session.scalar(
            select(ApunteContable)
        )
        movimiento = session.scalar(
            select(MovimientoPrevisto)
        )

        assert apunte is not None
        assert movimiento is not None
        assert movimiento.apunte_id == apunte.id

        apunte_id = apunte.id
        movimiento_id = movimiento.id

    # El usuario resuelve manualmente el movimiento previsto.
    response = client.post(
        (
            f"/conciliacion/previstos/{movimiento_id}"
            "/conciliar-manualmente"
        ),
        data={
            "notas": (
                "Incluido en los cargos agrupados "
                "del Ayuntamiento."
            ),
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        assert movimiento is not None
        assert movimiento.estado == "CONCILIADO"
        assert movimiento.metodo_conciliacion == "MANUAL"
        assert movimiento.notas == (
            "Incluido en los cargos agrupados "
            "del Ayuntamiento."
        )
        assert movimiento.fecha_prevista_desde == date(
            2026, 9, 20
        )
        assert movimiento.fecha_prevista_hasta == date(
            2026, 9, 30
        )

    datos_edicion = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_TRIBUTOS.IBI",
        "concepto": "IBI local corregido",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "CONTABILIZAR",
        "base": "250,00",
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "Concello de Pontevedra",
        "tercero_nif": "",
        "referencia_documento": "",
        "accion": "validar",
    }

    # El usuario valida cambios puramente descriptivos.
    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos_edicion,
    )

    assert response.status_code == 200

    datos_edicion["concepto"] = _valor_input(
        response,
        "concepto",
    )
    datos_edicion["concepto_automatico"] = _valor_input(
        response,
        "concepto_automatico",
    )
    datos_edicion["nombre_documento"] = _valor_input(
        response,
        "nombre_documento",
    )
    datos_edicion["nombre_documento_automatico"] = _valor_input(
        response,
        "nombre_documento_automatico",
    )
    datos_edicion["firma_validacion"] = _valor_input(
        response,
        "firma_validacion",
    )
    datos_edicion["accion"] = "guardar"

    # El usuario guarda los cambios ya validados.
    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos_edicion,
    )

    assert response.status_code == 302

    # El previsto se sincroniza sin perder cómo fue resuelto.
    with session_factory() as session:
        apunte = session.get(
            ApunteContable,
            apunte_id,
        )
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        assert apunte is not None
        assert movimiento is not None

        assert apunte.concepto == "IBI local corregido"
        assert apunte.tercero_nombre == (
            "Concello de Pontevedra"
        )

        assert movimiento.concepto == (
            "IBI local corregido"
        )
        assert movimiento.contraparte == (
            "Concello de Pontevedra"
        )

        assert movimiento.estado == "CONCILIADO"
        assert movimiento.metodo_conciliacion == "MANUAL"
        assert movimiento.notas == (
            "Incluido en los cargos agrupados "
            "del Ayuntamiento."
        )
        assert movimiento.fecha_prevista_desde == date(
            2026, 9, 20
        )
        assert movimiento.fecha_prevista_hasta == date(
            2026, 9, 30
        )


@pytest.mark.parametrize(
    (
        "criterio_anterior",
        "inicio_nuevo",
        "tipo_aviso",
    ),
    [
        # Fecha hasta incluida: continuidad al día siguiente.
        ("INCLUIR_AMBOS", date(2026, 9, 1), None),
        ("INCLUIR_AMBOS", date(2026, 9, 2), "discontinuidad"),
        ("INCLUIR_AMBOS", date(2026, 8, 31), "solapamiento"),

        # Fecha hasta excluida: continuidad el mismo día.
        ("EXCLUIR_HASTA", date(2026, 8, 31), None),
        ("EXCLUIR_HASTA", date(2026, 9, 1), "discontinuidad"),
        ("EXCLUIR_HASTA", date(2026, 8, 30), "solapamiento"),
    ],
)
def test_validar_continuidad_periodo_suministro(
    session,
    inmueble,
    criterio_anterior,
    inicio_nuevo,
    tipo_aviso,
) -> None:
    """La continuidad depende de incluir el día hasta."""

    anterior = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 9, 5),
        naturaleza="GASTO",
        categoria="GAS_SERVICIOS_SUMINISTROS",
        subcategoria="AGUA",
        concepto="Agua anterior",
        periodo_desde=date(2026, 7, 1),
        periodo_hasta=date(2026, 8, 31),
        criterio_periodo=criterio_anterior,
        tratamiento="CONTABILIZAR",
        nombre_documento="agua-anterior.pdf",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
    )

    session.add(anterior)
    session.flush()

    aviso = _comprobar_continuidad_suministro(
        session,
        inmueble_id=inmueble.id,
        categoria="GAS_SERVICIOS_SUMINISTROS",
        subcategoria="AGUA",
        naturaleza="GASTO",
        periodo_desde=inicio_nuevo,
        periodo_hasta=date(2026, 10, 31),
        criterio_periodo="INCLUIR_AMBOS",
    )

    if tipo_aviso is None:
        assert aviso is None
    else:
        assert aviso is not None
        assert tipo_aviso in aviso.lower()


def test_continuidad_suministro_ignora_otros_suministros(
    session,
    inmueble,
) -> None:
    anterior = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 9, 5),
        naturaleza="GASTO",
        categoria="GAS_SERVICIOS_SUMINISTROS",
        subcategoria="GAS",
        concepto="Gas anterior",
        periodo_desde=date(2026, 7, 1),
        periodo_hasta=date(2026, 8, 31),
        criterio_periodo="INCLUIR_AMBOS",
        tratamiento="CONTABILIZAR",
        nombre_documento="gas-anterior.pdf",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
    )

    session.add(anterior)
    session.flush()

    aviso = _comprobar_continuidad_suministro(
        session,
        inmueble_id=inmueble.id,
        categoria="GAS_SERVICIOS_SUMINISTROS",
        subcategoria="AGUA",
        naturaleza="GASTO",
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 11, 30),
        criterio_periodo="INCLUIR_AMBOS",
    )

    assert aviso is None


def test_continuidad_suministro_excluye_apunte_editado(
    session,
    inmueble,
) -> None:
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 9, 5),
        naturaleza="GASTO",
        categoria="GAS_SERVICIOS_SUMINISTROS",
        subcategoria="AGUA",
        concepto="Recibo editado",
        periodo_desde=date(2026, 7, 1),
        periodo_hasta=date(2026, 8, 31),
        criterio_periodo="INCLUIR_AMBOS",
        tratamiento="CONTABILIZAR",
        nombre_documento="agua-editado.pdf",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
    )

    session.add(apunte)
    session.flush()

    aviso = _comprobar_continuidad_suministro(
        session,
        inmueble_id=inmueble.id,
        categoria="GAS_SERVICIOS_SUMINISTROS",
        subcategoria="AGUA",
        naturaleza="GASTO",
        periodo_desde=date(2026, 7, 1),
        periodo_hasta=date(2026, 8, 31),
        criterio_periodo="INCLUIR_AMBOS",
        excluir_id=apunte.id,
    )

    assert aviso is None


@pytest.mark.parametrize("editar", [False, True])
def test_validar_apunte_agua_avisa_de_discontinuidad(
    tmp_path,
    monkeypatch,
    editar,
) -> None:
    """Alta y edición avisan si falta un período de agua."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_SERVICIOS_SUMINISTROS = GASTO | Servicios y suministros

[subcategorias_contables]
GAS_SERVICIOS_SUMINISTROS.AGUA = Agua
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTAB_CONFIG", str(ruta))

    app = crear_app_test()
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

        anterior = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 9, 5),
            naturaleza="GASTO",
            categoria="GAS_SERVICIOS_SUMINISTROS",
            subcategoria="AGUA",
            concepto="Agua anterior",
            periodo_desde=date(2026, 7, 1),
            periodo_hasta=date(2026, 8, 31),
            criterio_periodo="INCLUIR_AMBOS",
            tratamiento="CONTABILIZAR",
            nombre_documento="agua-anterior.pdf",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
        )

        session.add_all([inmueble, anterior])

        if editar:
            actual = ApunteContable(
                inmueble=inmueble,
                fecha=date(2026, 10, 1),
                naturaleza="GASTO",
                categoria="GAS_SERVICIOS_SUMINISTROS",
                subcategoria="AGUA",
                concepto="Agua actual",
                periodo_desde=date(2026, 9, 15),
                periodo_hasta=date(2026, 10, 31),
                criterio_periodo="INCLUIR_AMBOS",
                tratamiento="CONTABILIZAR",
                nombre_documento="agua-actual.pdf",
                base=12000,
                iva_importe=0,
                retencion_importe=0,
                total=12000,
            )
            session.add(actual)

        session.commit()
        inmueble_id = inmueble.id
        apunte_id = actual.id if editar else None

    client = app.test_client()
    client.post("/", data={"database": "test"})

    url = (
        f"/contabilidad/{apunte_id}/editar"
        if editar
        else "/contabilidad/nuevo"
    )

    response = client.post(
        url,
        data={
            "inmueble_id": str(inmueble_id),
            "fecha": "01/10/2026",
            "clasificacion": (
                "GAS_SERVICIOS_SUMINISTROS.AGUA"
            ),
            "concepto": "Agua actual",
            "periodo_desde": "15/09/2026",
            "periodo_hasta": "31/10/2026",
            "criterio_periodo": "INCLUIR_AMBOS",
            "tratamiento": "CONTABILIZAR",
            "base": "120,00",
            "iva_importe": "0,00",
            "retencion_importe": "0,00",
            "nombre_documento": "",
            "tercero_nombre": "Empresa de aguas",
            "tercero_nif": "",
            "referencia_documento": "AGUA-2026-02",
            "accion": "validar",
        },
    )

    assert response.status_code == 200
    assert "Posible discontinuidad" in response.text
    assert "01/09/2026" in response.text
    assert "14/09/2026" in response.text
    assert 'class="warning"' in response.text
    assert _valor_input(response, "firma_validacion")


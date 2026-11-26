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
    Contrato,
    Factura,
    ImputacionContrato,
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


def _campo_bloqueado(response, nombre: str) -> bool:
    """Comprueba si un campo visible no puede editarse."""

    coincidencia = re.search(
        rf'<(?:input|select)\b'
        rf'[^>]*\bid="{re.escape(nombre)}"'
        rf'[^>]*>',
        response.text,
        re.DOTALL,
    )

    assert coincidencia is not None

    return re.search(
        r"\s(?:readonly|disabled)(?=\s|=|>)",
        coincidencia.group(0),
    ) is not None


def _opciones_selector(
    response,
    nombre: str,
) -> set[str]:
    """Obtiene los valores no vacíos de un desplegable."""

    coincidencia = re.search(
        rf'<select\b[^>]*\bid="{re.escape(nombre)}"[^>]*>'
        r'(.*?)</select>',
        response.text,
        re.DOTALL,
    )

    assert coincidencia is not None, nombre

    return {
        unescape(valor)
        for valor in re.findall(
            r'<option\b[^>]*\bvalue="([^"]*)"',
            coincidencia.group(1),
        )
        if valor
    }


def _opciones_clasificacion(response) -> set[str]:
    """Obtiene los códigos disponibles de clasificación."""

    return _opciones_selector(
        response,
        "clasificacion",
    )


def _valor_selector(
    response,
    nombre: str,
) -> str:
    """Obtiene el valor seleccionado de un desplegable."""

    coincidencia = re.search(
        rf'<select\b[^>]*\bid="{re.escape(nombre)}"[^>]*>'
        r'(.*?)</select>',
        response.text,
        re.DOTALL,
    )

    assert coincidencia is not None, nombre

    opciones = re.findall(
        r'<option\b[^>]*>',
        coincidencia.group(1),
        re.DOTALL,
    )

    assert opciones, nombre

    for opcion in opciones:
        if re.search(
            r"\sselected(?=\s|=|>)",
            opcion,
        ):
            valor = re.search(
                r'\bvalue="([^"]*)"',
                opcion,
            )

            assert valor is not None

            return unescape(valor.group(1))

    # Si ninguna opción está seleccionada expresamente,
    # el navegador selecciona la primera.
    valor = re.search(
        r'\bvalue="([^"]*)"',
        opciones[0],
    )

    assert valor is not None

    return unescape(valor.group(1))


def _tratamiento_bloqueado(response, tratamiento: str) -> bool:
    """Comprueba si una opción de tratamiento está deshabilitada."""

    coincidencia = re.search(
        r'<input\b[^>]*\bname="tratamiento"'
        rf'[^>]*\bvalue="{re.escape(tratamiento)}"'
        r'[^>]*>',
        response.text,
        re.DOTALL,
    )

    assert coincidencia is not None

    return re.search(
        r"\sdisabled(?=\s|=|>)",
        coincidencia.group(0),
    ) is not None


def _valor_campo_oculto(response, nombre: str) -> str:
    """Obtiene el valor de un campo oculto del formulario."""

    coincidencia = re.search(
        r'<input\b'
        r'[^>]*\btype="hidden"'
        rf'[^>]*\bname="{re.escape(nombre)}"'
        r'[^>]*\bvalue="([^"]*)"',
        response.text,
        re.DOTALL,
    )

    assert coincidencia is not None, nombre

    return unescape(coincidencia.group(1))


def _datos_formulario_apunte_bloqueado(response) -> dict:
    """Recoge los valores enviados por un formulario protegido."""

    campos_ocultos = (
        "inmueble_id",
        "clasificacion",
        "dia_hasta_incluido",
        "tratamiento",
        "concepto_automatico",
        "nombre_documento_automatico",
    )

    campos_texto = (
        "fecha",
        "concepto",
        "nombre_documento",
        "periodo_desde",
        "periodo_hasta",
        "base",
        "iva_importe",
        "retencion_importe",
        "tercero_nombre",
        "tercero_nif",
        "referencia_documento",
    )

    datos = {
        campo: _valor_campo_oculto(response, campo)
        for campo in campos_ocultos
    }

    datos.update({
        campo: _valor_input(response, campo)
        for campo in campos_texto
    })

    return datos


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
        inmueble = _crear_inmueble_prueba(
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

        id_antiguo = antiguo.id
        id_reciente = reciente.id

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

    for identificador in (id_antiguo, id_reciente):
        assert (
            f'href="/conciliacion/relaciones/apunte/{identificador}"'
            in response.text
        )


def test_listado_muestra_importes_negativos() -> None:
    app = crear_app_test()

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
        local_1 = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial 1",
            direccion="Dirección 1",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        local_2 = _crear_inmueble_prueba(
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



def test_formulario_apunte_solo_ofrece_dos_opciones_dia_hasta(
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
        r'<select\b[^>]*id="dia_hasta_incluido"[^>]*>'
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
        "1",
        "0",
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
    assert 'id="dia_hasta_incluido"' in html


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
        inmueble = _crear_inmueble_prueba(
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
        assert apunte.dia_hasta_incluido is True
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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
            referencia="EDIFICIO-COMUN",
            tipo="T",
            codigo_facturacion="EC",
            descripcion="Elementos comunes",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
            participacion=10000,
        )

        local_a = _crear_inmueble_prueba(
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

        local_b = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
GAS_COMUNIDAD = GASTO | Comunidad
ING_ALQUILERES = INGRESO | Alquileres
ING_OTROS = INGRESO | Otros ingresos

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
        inmueble = _crear_inmueble_prueba(
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

    # Un apunte sin dependencias conserva todas
    # las posibilidades de clasificación.
    assert _opciones_clasificacion(response) == {
        "GAS_TRIBUTOS.TRU",
        "GAS_COMUNIDAD",
        "ING_ALQUILERES",
        "ING_OTROS",
    }

    assert 'id="restricciones_edicion"' not in response.text


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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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

    otro_inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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

    otro_inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
GAS_REPARACIONES = GASTO | Reparaciones
ING_ALQUILERES = INGRESO | Alquileres
ING_OTROS = INGRESO | Otros ingresos

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
        inmueble = _crear_inmueble_prueba(
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

    # El usuario abre un apunte cuyo pago está conciliado.
    response = client.get(
        f"/contabilidad/{apunte_id}/editar"
    )

    assert response.status_code == 200

    # No puede cambiar el inmueble.
    assert _campo_bloqueado(response, "inmueble_id")

    # Puede corregir otros datos siempre que conserve
    # el importe total, su signo y la naturaleza.
    campos_editables = (
        "fecha",
        "clasificacion",
        "concepto",
        "periodo_desde",
        "periodo_hasta",
        "dia_hasta_incluido",
        "base",
        "iva_importe",
        "retencion_importe",
        "tercero_nombre",
        "tercero_nif",
        "referencia_documento",
    )

    for campo in campos_editables:
        assert not _campo_bloqueado(response, campo), campo

    # La conciliación protege la naturaleza del apunte,
    # pero no su clasificación dentro de los gastos.
    assert _opciones_clasificacion(response) == {
        "GAS_COMUNIDAD",
        "GAS_REPARACIONES",
    }

    assert (
        "No pueden modificarse el inmueble, la naturaleza, "
        "el importe total ni su signo."
        in response.text
    )

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

    # La base sigue siendo editable porque puede corregirse
    # junto con el IVA y la retención, manteniendo el total.
    assert not _campo_bloqueado(response, "base")

    assert _valor_input(
        response,
        "base",
    ) == "120,00"

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
        inmueble = _crear_inmueble_prueba(
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
        inmueble = _crear_inmueble_prueba(
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
        "dia_hasta_incluido_anterior",
        "inicio_nuevo",
        "tipo_aviso",
    ),
    [
        # Fecha final incluida: continuidad al día siguiente.
        (True, date(2026, 9, 1), None),
        (True, date(2026, 9, 2), "discontinuidad"),
        (True, date(2026, 8, 31), "solapamiento"),

        # Fecha final excluida: continuidad el mismo día.
        (False, date(2026, 8, 31), None),
        (False, date(2026, 9, 1), "discontinuidad"),
        (False, date(2026, 8, 30), "solapamiento"),
    ],
)
def test_validar_continuidad_periodo_suministro(
    session,
    inmueble,
    dia_hasta_incluido_anterior,
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
        dia_hasta_incluido=dia_hasta_incluido_anterior,
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
        dia_hasta_incluido=True,
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
        dia_hasta_incluido=True,
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
        dia_hasta_incluido=True,
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
        dia_hasta_incluido=True,
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
        dia_hasta_incluido=True,
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
        inmueble = _crear_inmueble_prueba(
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
            dia_hasta_incluido=True,
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
                dia_hasta_incluido=True,
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
            "dia_hasta_incluido": "1",
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


@pytest.mark.parametrize(
    "base_nueva, modificacion_permitida",
    [
        ("120,00", False),
        ("100,00", True),
    ],
)
def test_editar_apunte_con_imputacion_persistida(
    tmp_path,
    monkeypatch,
    base_nueva,
    modificacion_permitida,
) -> None:
    """Validar y Guardar respetan las imputaciones persistidas."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad
GAS_REPARACIONES = GASTO | Reparaciones
ING_ALQUILERES = INGRESO | Alquileres
ING_OTROS = INGRESO | Otros ingresos

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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        contrato = Contrato(
            inmueble=inmueble,
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2035, 12, 31),
            fecha_fin=None,
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=0,
            direccion_facturacion="Dirección",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
        )

        # El usuario ha contabilizado un gasto de 100 euros.
        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 9, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Cuota de comunidad",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
            tratamiento="REPERCUTIR",
        )

        # El gasto tiene una imputación contractual persistida.
        imputacion = ImputacionContrato(
            apunte=apunte,
            contrato=contrato,
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            importe=10000,
        )

        session.add_all([
            inmueble,
            contrato,
            apunte,
            imputacion,
        ])
        session.commit()

        inmueble_id = inmueble.id
        apunte_id = apunte.id
        imputacion_id = imputacion.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # El usuario abre un apunte con imputaciones persistidas.
    response = client.get(
        f"/contabilidad/{apunte_id}/editar"
    )

    assert response.status_code == 200

    campos_protegidos = (
        "inmueble_id",
        "fecha",
        "periodo_desde",
        "periodo_hasta",
        "dia_hasta_incluido",
        "base",
        "iva_importe",
        "retencion_importe",
    )

    for campo in campos_protegidos:
        assert _campo_bloqueado(response, campo), campo

    # El tratamiento está protegido por las dependencias
    # del apunte, independientemente de su naturaleza.
    for tratamiento in (
        "CONTABILIZAR",
        "REPERCUTIR",
        "FACTURAR",
    ):
        assert _tratamiento_bloqueado(
            response,
            tratamiento,
        )

    # Puede corregirse la clasificación dentro de los gastos
    # y también la información descriptiva del apunte.
    campos_editables = (
        "clasificacion",
        "concepto",
        "nombre_documento",
        "tercero_nombre",
        "tercero_nif",
        "referencia_documento",
    )

    for campo in campos_editables:
        assert not _campo_bloqueado(response, campo), campo

    # Puede corregirse la categoría de gasto, pero no convertir el apunte en un ingreso.
    assert _opciones_clasificacion(response) == {
        "GAS_COMUNIDAD",
        "GAS_REPARACIONES",
    }

    assert (
        "No pueden modificarse los datos que afectan "
        "al reparto ya realizado."
        in response.text
    )

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "15/09/2026",
        "clasificacion": "GAS_COMUNIDAD",
        "concepto": "Cuota de comunidad corregida",
        "periodo_desde": "",
        "periodo_hasta": "",
        "tratamiento": "REPERCUTIR",
        "base": base_nueva,
        "iva_importe": "0,00",
        "retencion_importe": "0,00",
        "nombre_documento": "",
        "tercero_nombre": "",
        "tercero_nif": "",
        "referencia_documento": "",
        "accion": "validar",
    }

    base_original = _valor_input(response, "base")

    # El usuario intenta validar la modificación del apunte.
    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos,
    )

    if modificacion_permitida:
        assert response.status_code == 200

        datos["nombre_documento"] = _valor_input(
            response,
            "nombre_documento",
        )

        datos["firma_validacion"] = _valor_input(
            response,
            "firma_validacion",
        )

        assert datos["firma_validacion"]

        # El usuario guarda la corrección descriptiva.
        datos["accion"] = "guardar"

        response = client.post(
            f"/contabilidad/{apunte_id}/editar",
            data=datos,
        )

        assert response.status_code == 302

    else:
        assert response.status_code == 400

        # El importe rechazado no debe permanecer en
        # un campo que el usuario no puede modificar.
        assert _valor_input(
            response,
            "base",
        ) == base_original

        assert _campo_bloqueado(response, "base")

        assert (
            'name="firma_validacion"'
            not in response.text
        )

        assert 'value="guardar"' not in response.text

        assert (
            "No pueden modificarse los datos que afectan al reparto"
            in response.text
        )

        assert 'name="firma_validacion"' not in response.text
        assert 'value="guardar"' not in response.text

    # Comprobar los datos realmente almacenados.
    with session_factory() as session:
        apunte = session.get(
            ApunteContable,
            apunte_id,
        )

        imputacion = session.get(
            ImputacionContrato,
            imputacion_id,
        )

        assert apunte is not None
        assert imputacion is not None

        assert apunte.base == 10000
        assert apunte.total == 10000

        assert imputacion.base == 10000
        assert imputacion.importe == 10000
        assert imputacion.apunte_id == apunte_id

        if modificacion_permitida:
            assert apunte.concepto == (
                "Cuota de comunidad corregida"
            )
        else:
            assert apunte.concepto == "Cuota de comunidad"


def test_editar_apunte_con_factura_rechaza_cambio_importe(
    tmp_path,
    monkeypatch,
) -> None:
    """El formulario impide modificar los importes de una factura."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
ING_ALQUILERES = INGRESO | Alquileres
ING_OTROS = INGRESO | Otros ingresos
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        contrato = Contrato(
            inmueble=inmueble,
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2035, 12, 31),
            fecha_fin=None,
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=0,
            direccion_facturacion="Dirección",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
        )

        # El usuario tiene contabilizada una factura de octubre.
        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 10, 1),
            naturaleza="INGRESO",
            categoria="ING_ALQUILERES",
            concepto="Alquiler. Octubre de 2026",
            base=100000,
            iva_importe=21000,
            retencion_importe=19000,
            total=102000,
            periodo_desde=date(2026, 10, 1),
            periodo_hasta=date(2026, 10, 31),
            dia_hasta_incluido=True,
            tercero_nombre="Ana Pérez",
            tercero_nif="11111111A",
            referencia_documento="01/2026A1",
        )

        factura = Factura(
            contrato=contrato,
            apunte_contable=apunte,
            numero_secuencia=1,
            anio=2026,
            numero_factura="01/2026A1",
            referencia_inmueble=inmueble.referencia,
            descripcion_inmueble=inmueble.descripcion,
            direccion_facturacion=contrato.direccion_facturacion,
            poblacion_facturacion=contrato.poblacion_facturacion,
            provincia_facturacion=contrato.provincia_facturacion,
            fecha_emision=date(2026, 10, 1),
            periodo=date(2026, 10, 1),
            base=100000,
            iva_porcentaje=2100,
            iva_importe=21000,
            retencion_porcentaje=1900,
            retencion_importe=19000,
            total=102000,
            estado="EMITIDA",
        )

        # El cobro de la factura todavía está pendiente.
        movimiento = crear_movimiento_desde_apunte(
            apunte=apunte,
            contrato=contrato,
            fecha_prevista_desde=date(2026, 10, 1),
            fecha_prevista_hasta=date(2026, 10, 31),
        )

        session.add_all([
            inmueble,
            contrato,
            apunte,
            factura,
            movimiento,
        ])
        session.commit()

        inmueble_id = inmueble.id
        apunte_id = apunte.id
        factura_id = factura.id
        movimiento_id = movimiento.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # El usuario abre el formulario de edición.
    response = client.get(
        f"/contabilidad/{apunte_id}/editar"
    )

    assert response.status_code == 200

    # Los datos procedentes de la factura no pueden editarse.
    campos_protegidos = (
        "inmueble_id",
        "fecha",
        "clasificacion",
        "periodo_desde",
        "periodo_hasta",
        "dia_hasta_incluido",
        "base",
        "iva_importe",
        "retencion_importe",
        "tercero_nombre",
        "tercero_nif",
        "referencia_documento",
    )

    for campo in campos_protegidos:
        assert _campo_bloqueado(response, campo), campo

    # Los controles deshabilitados necesitan campos ocultos
    # para conservar sus valores al enviar el formulario.
    assert _valor_campo_oculto(
        response,
        "inmueble_id",
    ) == str(inmueble_id)

    assert _valor_campo_oculto(
        response,
        "clasificacion",
    ) == "ING_ALQUILERES"

    assert _valor_campo_oculto(
        response,
        "tratamiento",
    ) == "CONTABILIZAR"

    assert _valor_campo_oculto(
        response,
        "dia_hasta_incluido",
    ) == "1"

    # El tratamiento está protegido por las dependencias
    # del apunte, independientemente de su naturaleza.
    for tratamiento in (
        "CONTABILIZAR",
        "REPERCUTIR",
        "FACTURAR",
    ):
        assert _tratamiento_bloqueado(
            response,
            tratamiento,
        )

    assert _opciones_clasificacion(response) == {
        "ING_ALQUILERES",
    }

    # Los datos descriptivos siguen siendo editables.
    assert not _campo_bloqueado(response, "concepto")
    assert not _campo_bloqueado(response, "nombre_documento")

    assert (
        "Los datos procedentes de la factura vinculada "
        "no pueden modificarse desde Contabilidad."
        in response.text
    )

    datos = {
        "inmueble_id": str(inmueble_id),
        "fecha": "01/10/2026",
        "clasificacion": "ING_ALQUILERES",
        "concepto": "Alquiler. Octubre de 2026",
        "periodo_desde": "10/2026",
        "periodo_hasta": "",
        "dia_hasta_incluido": "1",
        "tratamiento": "CONTABILIZAR",
        "base": "1200,00",
        "iva_importe": "210,00",
        "retencion_importe": "190,00",
        "nombre_documento": "",
        "tercero_nombre": "Ana Pérez",
        "tercero_nif": "11111111A",
        "referencia_documento": "01/2026A1",
        "accion": "validar",
    }

    # Guardar los valores originales mostrados por el formulario.
    base_original = _valor_input(response, "base")

    # El usuario también introduce una modificación descriptiva
    # que sí está permitida.
    concepto_modificado = "Concepto descriptivo corregido"
    datos["concepto"] = concepto_modificado

    # El usuario intenta cambiar la base del apunte
    # directamente desde Contabilidad.
    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos,
    )

    assert response.status_code == 400
    assert "factura" in response.text.lower()

    # El formulario debe recuperar el importe protegido.
    assert _valor_input(
        response,
        "base",
    ) == base_original

    assert _campo_bloqueado(response, "base")

    # La modificación descriptiva debe conservarse para
    # que el usuario no tenga que introducirla nuevamente.
    assert _valor_input(
        response,
        "concepto",
    ) == concepto_modificado

    # El formulario no puede considerarse validado.
    assert 'name="firma_validacion"' not in response.text
    assert 'value="guardar"' not in response.text

    # La factura, el apunte y el movimiento previsto
    # deben permanecer intactos.
    with session_factory() as session:
        apunte = session.get(
            ApunteContable,
            apunte_id,
        )
        factura = session.get(
            Factura,
            factura_id,
        )
        movimiento = session.get(
            MovimientoPrevisto,
            movimiento_id,
        )

        assert apunte.base == 100000
        assert apunte.iva_importe == 21000
        assert apunte.retencion_importe == 19000
        assert apunte.total == 102000

        assert factura.apunte_contable_id == apunte_id
        assert factura.base == apunte.base
        assert factura.total == apunte.total

        assert movimiento.apunte_id == apunte_id
        assert movimiento.importe_esperado == 102000
        assert movimiento.estado == "PENDIENTE"


    # El usuario vuelve a abrir el formulario después
    # del intento rechazado.
    response = client.get(
        f"/contabilidad/{apunte_id}/editar"
    )

    assert response.status_code == 200

    datos_originales = _datos_formulario_apunte_bloqueado(
        response
    )

    datos = datos_originales.copy()

    # El usuario modifica únicamente los campos permitidos.
    concepto_nuevo = "Concepto corregido de la factura"
    documento_nuevo = "Factura-documento-corregido.pdf"

    datos.update({
        "concepto": concepto_nuevo,
        "nombre_documento": documento_nuevo,
        "concepto_automatico": "",
        "nombre_documento_automatico": "",
        "accion": "validar",
    })

    # El usuario pulsa Validar.
    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos,
    )

    assert response.status_code == 200

    # El formulario validado debe conservar las restricciones
    # y proporcionar los datos necesarios para guardar.
    datos_validados = _datos_formulario_apunte_bloqueado(
        response
    )

    assert datos_validados["concepto"] == concepto_nuevo
    assert datos_validados["nombre_documento"] == documento_nuevo

    for campo in (
        "inmueble_id",
        "fecha",
        "clasificacion",
        "periodo_desde",
        "periodo_hasta",
        "dia_hasta_incluido",
        "tratamiento",
        "base",
        "iva_importe",
        "retencion_importe",
        "tercero_nombre",
        "tercero_nif",
        "referencia_documento",
    ):
        assert datos_validados[campo] == datos_originales[campo]

    firma_validacion = _valor_campo_oculto(
        response,
        "firma_validacion",
    )

    assert firma_validacion

    # El usuario pulsa Guardar utilizando los valores
    # del formulario que acaba de validar.
    datos_validados["firma_validacion"] = firma_validacion
    datos_validados["accion"] = "guardar"

    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos_validados,
    )

    assert response.status_code == 302

    # El usuario vuelve a abrir el apunte guardado.
    response = client.get(
        f"/contabilidad/{apunte_id}/editar"
    )

    assert response.status_code == 200

    datos_guardados = _datos_formulario_apunte_bloqueado(
        response
    )

    # Solo se han modificado los datos permitidos.
    assert datos_guardados["concepto"] == concepto_nuevo
    assert datos_guardados["nombre_documento"] == documento_nuevo

    for campo in (
        "inmueble_id",
        "fecha",
        "clasificacion",
        "periodo_desde",
        "periodo_hasta",
        "dia_hasta_incluido",
        "tratamiento",
        "base",
        "iva_importe",
        "retencion_importe",
        "tercero_nombre",
        "tercero_nif",
        "referencia_documento",
    ):
        assert datos_guardados[campo] == datos_originales[campo]


def test_formulario_ingreso_conciliado_limita_clasificaciones(
    tmp_path,
    monkeypatch,
) -> None:
    """Un ingreso conciliado no puede reclasificarse como alquiler."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
ING_ALQUILERES = INGRESO | Alquileres
ING_OTROS = INGRESO | Otros ingresos
ING_INTERESES = INGRESO | Intereses
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        # El usuario ha contabilizado un ingreso ordinario.
        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 10, 1),
            naturaleza="INGRESO",
            categoria="ING_OTROS",
            concepto="Ingreso de octubre",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
            tratamiento="CONTABILIZAR",
            tercero_nombre="Tercero de prueba",
        )

        # El cobro ya ha sido conciliado manualmente.
        movimiento = crear_movimiento_desde_apunte(
            apunte=apunte,
        )

        movimiento.estado = "CONCILIADO"
        movimiento.metodo_conciliacion = "MANUAL"
        movimiento.notas = "Cobrado en efectivo"

        session.add_all([
            inmueble,
            apunte,
            movimiento,
        ])
        session.commit()

        apunte_id = apunte.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # El usuario abre el formulario para corregir
    # la clasificación del ingreso.
    response = client.get(
        f"/contabilidad/{apunte_id}/editar"
    )

    assert response.status_code == 200

    assert not _campo_bloqueado(
        response,
        "clasificacion",
    )

    # Puede seleccionar otras categorías de ingreso,
    # excepto la de alquileres.
    assert _opciones_clasificacion(response) == {
        "ING_OTROS",
        "ING_INTERESES",
    }


@pytest.mark.parametrize(
    "naturaleza, categoria, bloqueados",
    [
        (
            "INGRESO",
            "ING_OTROS",
            {"REPERCUTIR", "FACTURAR"},
        ),
        (
            "GASTO",
            "GAS_COMUNIDAD",
            set(),
        ),
    ],
)
def test_formulario_limita_tratamientos_segun_naturaleza(
    tmp_path,
    monkeypatch,
    naturaleza,
    categoria,
    bloqueados,
) -> None:
    """El formulario ofrece únicamente tratamientos compatibles."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
ING_OTROS = INGRESO | Otros ingresos
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        # El usuario registra un apunte sin dependencias
        # que puedan proteger su tratamiento.
        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 10, 1),
            naturaleza=naturaleza,
            categoria=categoria,
            concepto="Apunte de octubre",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
            tratamiento="CONTABILIZAR",
        )

        session.add_all([inmueble, apunte])
        session.commit()

        apunte_id = apunte.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # El usuario abre el formulario de edición.
    response = client.get(
        f"/contabilidad/{apunte_id}/editar"
    )

    assert response.status_code == 200

    # Comprobar individualmente las opciones disponibles.
    for tratamiento in (
        "CONTABILIZAR",
        "REPERCUTIR",
        "FACTURAR",
    ):
        assert _tratamiento_bloqueado(
            response,
            tratamiento,
        ) == (tratamiento in bloqueados)


@pytest.mark.parametrize(
    "categoria, subcategoria, clasificaciones_esperadas",
    [
        (
            "GAS_ANTIGUA",
            None,
            {
                "GAS_ANTIGUA",
                "GAS_COMUNIDAD",
                "GAS_TRIBUTOS.IBI",
            },
        ),
        (
            "GAS_TRIBUTOS",
            "ANTIGUA",
            {
                "GAS_COMUNIDAD",
                "GAS_TRIBUTOS.IBI",
                "GAS_TRIBUTOS.ANTIGUA",
            },
        ),
    ],
)
def test_editar_apunte_con_elementos_inactivos(
    tmp_path,
    monkeypatch,
    categoria,
    subcategoria,
    clasificaciones_esperadas,
) -> None:
    """Permite editar un apunte conservando sus elementos históricos."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
GAS_COMUNIDAD = GASTO | Comunidad
GAS_ANTIGUA = GASTO | Categoría antigua | inactiva
GAS_OTRA = GASTO | Otra categoría antigua | inactiva
GAS_TRIBUTOS = GASTO | Tributos

[subcategorias_contables]
GAS_TRIBUTOS.IBI = IBI
GAS_TRIBUTOS.ANTIGUA = Tasa antigua | inactiva
GAS_TRIBUTOS.OTRA = Otra tasa antigua | inactiva
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
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local histórico",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        inmueble_activo = _crear_inmueble_prueba(
            referencia="LOCAL-2",
            tipo="L",
            codigo_facturacion="A2",
            descripcion="Local activo",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        otro_inmueble_inactivo = _crear_inmueble_prueba(
            referencia="LOCAL-3",
            tipo="L",
            codigo_facturacion="A3",
            descripcion="Otro local histórico",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        # El apunte se registró cuando su inmueble
        # y su clasificación todavía estaban activos.
        apunte = ApunteContable(
            inmueble=inmueble,
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria=categoria,
            subcategoria=subcategoria,
            concepto="Concepto original",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
            tratamiento="CONTABILIZAR",
        )

        inmueble.activo = False
        inmueble_activo.activo = True
        otro_inmueble_inactivo.activo = False

        session.add_all([
            inmueble,
            inmueble_activo,
            otro_inmueble_inactivo,
            apunte,
        ])

        session.commit()

        inmueble_id = inmueble.id
        inmueble_activo_id = inmueble_activo.id
        apunte_id = apunte.id

    client = app.test_client()
    client.post("/", data={"database": "test"})

    # El usuario abre el formulario de edición
    # de un apunte histórico.
    response = client.get(
        f"/contabilidad/{apunte_id}/editar"
    )

    assert response.status_code == 200

    # Solo se ofrecen los inmuebles activos y el
    # inmueble histórico asociado al propio apunte.
    assert _opciones_selector(
        response,
        "inmueble_id",
    ) == {
        str(inmueble_id),
        str(inmueble_activo_id),
    }

    # Solo se ofrecen las clasificaciones activas
    # y la clasificación histórica del apunte.
    assert _opciones_clasificacion(
        response
    ) == clasificaciones_esperadas

    clasificacion = categoria

    if subcategoria:
        clasificacion += f".{subcategoria}"

    assert _valor_selector(
        response,
        "inmueble_id",
    ) == str(inmueble_id)

    assert _valor_selector(
        response,
        "clasificacion",
    ) == clasificacion

    # El usuario corrige únicamente el concepto,
    # conservando el inmueble y la clasificación.
    datos = {
        "inmueble_id": _valor_selector(
            response,
            "inmueble_id",
        ),
        "clasificacion": _valor_selector(
            response,
            "clasificacion",
        ),
        "dia_hasta_incluido": _valor_selector(
            response,
            "dia_hasta_incluido",
        ),
        "tratamiento": "CONTABILIZAR",
        "concepto_automatico": "",
        "nombre_documento_automatico": "",
        "accion": "validar",
    }

    for campo in (
        "fecha",
        "concepto",
        "nombre_documento",
        "periodo_desde",
        "periodo_hasta",
        "base",
        "iva_importe",
        "retencion_importe",
        "tercero_nombre",
        "tercero_nif",
        "referencia_documento",
    ):
        datos[campo] = _valor_input(response, campo)

    datos["concepto"] = "Concepto corregido"

    # El usuario pulsa Validar.
    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos,
    )

    assert response.status_code == 200

    assert _valor_selector(
        response,
        "inmueble_id",
    ) == str(inmueble_id)

    assert _valor_selector(
        response,
        "clasificacion",
    ) == clasificacion

    # Validar no debe modificar el apunte persistido.
    with session_factory() as session:
        apunte = session.get(
            ApunteContable,
            apunte_id,
        )

        assert apunte.concepto == "Concepto original"

    datos["nombre_documento"] = _valor_input(
        response,
        "nombre_documento",
    )

    datos["concepto_automatico"] = _valor_campo_oculto(
        response,
        "concepto_automatico",
    )

    datos["nombre_documento_automatico"] = (
        _valor_campo_oculto(
            response,
            "nombre_documento_automatico",
        )
    )

    datos["firma_validacion"] = _valor_campo_oculto(
        response,
        "firma_validacion",
    )

    datos["accion"] = "guardar"

    # El usuario pulsa Guardar.
    response = client.post(
        f"/contabilidad/{apunte_id}/editar",
        data=datos,
    )

    assert response.status_code == 302

    # Se conserva la información histórica del apunte.
    with session_factory() as session:
        apunte = session.get(
            ApunteContable,
            apunte_id,
        )

        assert apunte.concepto == "Concepto corregido"
        assert apunte.inmueble_id == inmueble_id
        assert apunte.inmueble.activo is False
        assert apunte.categoria == categoria
        assert apunte.subcategoria == subcategoria
        assert apunte.total == 10000


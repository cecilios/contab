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
)
from contab.conciliacion.services import (
    ConciliacionError,
    crear_movimiento_desde_apunte,
)
from contab.models import (
    ApunteContable,
    Inmueble,
    MovimientoPrevisto,
)
from contab.config import (
    CategoriaContable,
)


def _valor_input(response, nombre: str) -> str:
    """Extrae el valor de un input de la respuesta HTML."""

    coincidencia = re.search(
        rf'name="{re.escape(nombre)}"'
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
    assert "125,00 €" in response.text

    posicion_reciente = response.text.index(
        "Tasa de residuos"
    )
    posicion_antiguo = response.text.index(
        "Cuota de agosto"
    )

    assert posicion_reciente < posicion_antiguo


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
        assert apunte.tratamiento == "CONTABILIZAR"
        assert apunte.nombre_documento == ("LOCAL-1-Tasa de Residuos Urbanos 2026-09.pdf")
        assert apunte.base == 10000
        assert apunte.iva_importe == 2100
        assert apunte.total == 12100


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
        fecha_prevista=date(2026, 9, 5),
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
        fecha_prevista=date(2026, 9, 5),
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



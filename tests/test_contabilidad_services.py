"""Pruebas de la lógica de negocio contable."""

import pytest

from datetime import date
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from contab.facturacion.services import (
    FacturacionError,
    contabilizar_ingreso_sin_factura,
    emitir_factura,
)
from contab.config import (
    ApunteAutomatico,
    CategoriaContable,
    SubcategoriaContable,
)
from contab.contabilidad.services import (
    ContabilidadError,
    buscar_documentos_duplicados,
    buscar_gastos_repercutibles_pendientes,
    calcular_reparto_contratos_detallado,
    calcular_reparto_contratos,
    crear_apunte_contable,
    eliminar_apunte_contable,
    modificar_apunte_contable,
    preparar_apuntes_automaticos,
    preparar_imputaciones_contrato,
    preparar_registro_contable,
    proponer_nombre_documento,
)
from contab.models import (
    ApunteContable,
    Contrato,
    DistribucionApunte,
    Factura,
    ImputacionContrato,
    Inmueble,
    MovimientoPrevisto,
)




CASOS_NATURALEZA_SIGNO_TRATAMIENTO = [
    ("INGRESO", False, "CONTABILIZAR", True),
    ("INGRESO", False, "REPERCUTIR", False),
    ("INGRESO", False, "FACTURAR", False),
    ("INGRESO", True, "CONTABILIZAR", True),
    ("INGRESO", True, "REPERCUTIR", False),
    ("INGRESO", True, "FACTURAR", False),
    ("GASTO", False, "CONTABILIZAR", True),
    ("GASTO", False, "REPERCUTIR", True),
    ("GASTO", False, "FACTURAR", True),
    ("GASTO", True, "CONTABILIZAR", True),
    ("GASTO", True, "REPERCUTIR", True),
    ("GASTO", True, "FACTURAR", True),
]


def _inmueble_subdividido_para_distribuir():
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

    return inmueble, local_a, local_b


def _categorias_gastos_comunes():
    return {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }


def _contrato_para_imputacion(
    inmueble: Inmueble,
    *,
    fecha_inicio: date,
    fecha_fin: date | None,
) -> Contrato:
    return Contrato(
        inmueble=inmueble,
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=(
            fecha_fin
            if fecha_fin is not None
            else date(2035, 12, 31)
        ),
        fecha_fin=fecha_fin,
        genera_factura=True,
        fecha_inicio_facturacion=fecha_inicio,
        fianza=0,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )


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


@pytest.fixture
def apunte_con_factura(session, contrato):
    """Prepara una factura emitida cuyo cobro sigue pendiente."""

    categorias = {
        "ING_ALQUILERES": CategoriaContable(
            codigo="ING_ALQUILERES",
            naturaleza="INGRESO",
            nombre="Alquileres",
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
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    from contab.models import (
        ContratoInquilino,
        Inquilino,
        RentaContrato,
    )

    contrato.genera_factura = True
    contrato.iva_porcentaje = 2100
    contrato.retencion_porcentaje = 1900

    contrato.titulares.append(
        ContratoInquilino(
            orden=1,
            inquilino=Inquilino(
                nombre="Ana Pérez",
                nif="11111111A",
            ),
        )
    )

    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    session.commit()

    # El usuario emite y contabiliza la factura de octubre.
    factura, apunte, movimiento = emitir_factura(
        contrato=contrato,
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
        categorias=categorias,
    )

    session.add_all([
        factura,
        apunte,
        movimiento,
    ])
    session.commit()

    assert movimiento.estado == "PENDIENTE"
    assert factura.apunte_contable is apunte

    return factura, apunte, movimiento, categorias


def _datos_edicion_apunte(apunte):
    """Obtiene los valores actuales de un apunte para editarlo."""

    return {
        "inmueble": apunte.inmueble,
        "fecha": apunte.fecha,
        "naturaleza": apunte.naturaleza,
        "categoria": apunte.categoria,
        "subcategoria": apunte.subcategoria or "",
        "concepto": apunte.concepto,
        "base": apunte.base,
        "iva_importe": apunte.iva_importe,
        "retencion_importe": apunte.retencion_importe,
        "importe_negativo": apunte.importe_negativo,
        "tercero_nombre": apunte.tercero_nombre,
        "tercero_nif": apunte.tercero_nif,
        "referencia_documento": apunte.referencia_documento,
        "ruta_documento": apunte.ruta_documento,
        "nombre_documento": apunte.nombre_documento,
        "notas": apunte.notas or "",
        "periodo_desde": apunte.periodo_desde,
        "periodo_hasta": apunte.periodo_hasta,
        "dia_hasta_incluido": apunte.dia_hasta_incluido,
        "tratamiento": apunte.tratamiento,
    }


@pytest.fixture
def apunte_alquiler_sin_factura(session, contrato):
    """Prepara un alquiler contabilizado sin factura."""

    from contab.models import (
        ContratoInquilino,
        Inquilino,
        RentaContrato,
    )

    categorias = {
        "ING_ALQUILERES": CategoriaContable(
            codigo="ING_ALQUILERES",
            naturaleza="INGRESO",
            nombre="Alquileres",
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
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    contrato.genera_factura = False
    contrato.iva_porcentaje = 0
    contrato.retencion_porcentaje = 0

    contrato.titulares.append(
        ContratoInquilino(
            orden=1,
            inquilino=Inquilino(
                nombre="Ana Pérez",
                nif="11111111A",
            ),
        )
    )

    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=80000,
        )
    )

    session.commit()

    # El usuario contabiliza el alquiler de octubre.
    apunte, movimiento = contabilizar_ingreso_sin_factura(
        contrato=contrato,
        periodo=date(2026, 10, 1),
        fecha=date(2026, 10, 1),
        categorias=categorias,
    )

    session.add_all([
        apunte,
        movimiento,
    ])
    session.commit()

    assert movimiento.estado == "PENDIENTE"
    assert movimiento.contrato is contrato
    assert movimiento.apunte is apunte

    return apunte, movimiento, categorias


@pytest.fixture
def ingreso_para_reclasificar(session, contrato, categorias):
    """Prepara un ingreso ordinario con un movimiento previsto."""

    categorias = categorias.copy()

    categorias["ING_OTROS"] = CategoriaContable(
        codigo="ING_OTROS",
        naturaleza="INGRESO",
        nombre="Otros ingresos",
        activa=True,
        subcategorias=(),
    )

    contrato.genera_factura = False

    # El usuario registra un ingreso ordinario
    # sin identificarlo inicialmente como alquiler.
    registro = preparar_registro_contable(
        inmueble=contrato.inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 1),
        naturaleza="INGRESO",
        categoria="ING_OTROS",
        concepto="Ingreso de octubre",
        base=80000,
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 10, 31),
        dia_hasta_incluido=True,
    )

    apunte = registro.apunte
    movimiento = registro.movimiento_previsto

    session.add_all([apunte, movimiento])
    session.commit()

    assert movimiento.contrato is None
    assert movimiento.estado == "PENDIENTE"

    return apunte, movimiento, categorias


@pytest.fixture
def categorias_ingreso_gasto():
    """Proporciona categorías para probar ambos tipos de apunte."""

    categorias = _categorias_gastos_comunes()

    categorias["ING_OTROS"] = CategoriaContable(
        codigo="ING_OTROS",
        naturaleza="INGRESO",
        nombre="Otros ingresos",
        activa=True,
        subcategorias=(),
    )

    return categorias


@pytest.fixture
def categorias_con_inactivas():
    """Proporciona clasificaciones activas e históricas."""

    return {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
        "GAS_ANTIGUA": CategoriaContable(
            codigo="GAS_ANTIGUA",
            naturaleza="GASTO",
            nombre="Categoría antigua",
            activa=False,
            subcategorias=(),
        ),
        "GAS_TRIBUTOS": CategoriaContable(
            codigo="GAS_TRIBUTOS",
            naturaleza="GASTO",
            nombre="Tributos",
            activa=True,
            subcategorias=(
                SubcategoriaContable(
                    codigo="IBI",
                    nombre="IBI",
                    activa=True,
                ),
                SubcategoriaContable(
                    codigo="ANTIGUA",
                    nombre="Tasa antigua",
                    activa=False,
                ),
            ),
        ),
    }




def test_crear_apunte_contable(contrato) -> None:
    categorias = {
        "ING_OTRAS_RENTAS": CategoriaContable(
            codigo="ING_OTRAS_RENTAS",
            naturaleza="INGRESO",
            nombre="Otras rentas",
            activa=True,
            subcategorias=(
                SubcategoriaContable(
                    codigo="ANTENA_TELEFONIA",
                    nombre="Antena de telefonía",
                ),
            ),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=contrato.inmueble,
        categorias=categorias,
        fecha=date(2026, 8, 31),
        naturaleza="ingreso",
        categoria="ing_otras_rentas",
        subcategoria="antena_telefonia",
        concepto="  Alquiler de antena  ",
        base=100000,
        iva_importe=21000,
        retencion_importe=19000,
        tercero_nombre="  Comunidad de propietarios  ",
        tercero_nif=" h12345678 ",
        referencia_documento="  Liquidación agosto  ",
        periodo_desde=date(2026, 7, 1),
        periodo_hasta=date(2026, 7, 31),
        dia_hasta_incluido=False,
        tratamiento=" contabilizar ",
        nombre_documento="  antena-julio-2026.pdf  ",
    )

    assert apunte.inmueble is contrato.inmueble
    assert apunte.fecha == date(2026, 8, 31)
    assert apunte.naturaleza == "INGRESO"
    assert apunte.categoria == "ING_OTRAS_RENTAS"
    assert apunte.subcategoria == "ANTENA_TELEFONIA"
    assert apunte.concepto == "Alquiler de antena"
    assert apunte.base == 100000
    assert apunte.iva_importe == 21000
    assert apunte.retencion_importe == 19000
    assert apunte.total == 102000
    assert apunte.tercero_nombre == "Comunidad de propietarios"
    assert apunte.tercero_nif == "H12345678"
    assert apunte.referencia_documento == "Liquidación agosto"
    assert apunte.ruta_documento == ""
    assert apunte.notas is None
    assert apunte.periodo_desde == date(2026, 7, 1)
    assert apunte.periodo_hasta == date(2026, 7, 31)
    assert apunte.dia_hasta_incluido is False
    assert apunte.tratamiento == "CONTABILIZAR"
    assert apunte.nombre_documento == "antena-julio-2026.pdf"


def test_crear_apunte_rechaza_concepto_vacio(inmueble) -> None:
    categorias = {
        "ING_ALQUILERES": CategoriaContable(
            codigo="ING_ALQUILERES",
            naturaleza="INGRESO",
            nombre="Alquileres",
            activa=True,
            subcategorias=(),
        ),
    }

    with pytest.raises(
        ContabilidadError,
        match="concepto",
    ):
        crear_apunte_contable(
            inmueble=inmueble,
            categorias=categorias,
            fecha=date(2026, 8, 31),
            naturaleza="INGRESO",
            categoria="ING_ALQUILERES",
            concepto="",
            base=100000,
        )


@pytest.mark.parametrize(
    ("base", "iva_importe", "retencion_importe", "mensaje"),
    [
        (-1, 0, 0, "base"),
        (10000, -1, 0, "IVA"),
        (10000, 0, -1, "retención"),
        (10000, 0, 10001, "total"),
    ],
)
def test_crear_apunte_rechaza_importes_invalidos(
    inmueble,
    base: int,
    iva_importe: int,
    retencion_importe: int,
    mensaje: str,
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

    with pytest.raises(
        ContabilidadError,
        match=mensaje,
    ):
        crear_apunte_contable(
            inmueble=inmueble,
            categorias=categorias,
            fecha=date(2026, 8, 31),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Cuota de comunidad",
            base=base,
            iva_importe=iva_importe,
            retencion_importe=retencion_importe,
        )


def test_crear_apunte_rechaza_clasificacion_invalida(
    inmueble,
) -> None:
    categorias = {
        "GAS_TRIBUTOS": CategoriaContable(
            codigo="GAS_TRIBUTOS",
            naturaleza="GASTO",
            nombre="Tributos",
            activa=True,
            subcategorias=(
                SubcategoriaContable(
                    codigo="IBI",
                    nombre="IBI",
                ),
            ),
        ),
    }

    with pytest.raises(
        ContabilidadError,
        match="exige una subcategoría",
    ):
        crear_apunte_contable(
            inmueble=inmueble,
            categorias=categorias,
            fecha=date(2026, 8, 31),
            naturaleza="GASTO",
            categoria="GAS_TRIBUTOS",
            concepto="Tributo",
            base=10000,
        )


def test_modificar_apunte_contable(
    session,
    contrato,
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
        inmueble=contrato.inmueble,
        categorias=categorias,
        fecha=date(2026, 8, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota provisional",
        base=10000,
    )

    resultado = modificar_apunte_contable(
        session,
        apunte=apunte,
        inmueble=contrato.inmueble,
        categorias=categorias,
        fecha=date(2026, 8, 31),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota definitiva",
        base=12000,
        iva_importe=1000,
        notas="Corregido",
        periodo_desde=date(2026, 8, 1),
        periodo_hasta=date(2026, 8, 31),
        dia_hasta_incluido=True,
        tratamiento="FACTURAR",
        nombre_documento="comunidad-agosto.pdf",
    )

    assert resultado is apunte
    assert apunte.fecha == date(2026, 8, 31)
    assert apunte.concepto == "Cuota definitiva"
    assert apunte.base == 12000
    assert apunte.iva_importe == 1000
    assert apunte.total == 13000
    assert apunte.notas == "Corregido"
    assert apunte.periodo_desde == date(2026, 8, 1)
    assert apunte.periodo_hasta == date(2026, 8, 31)
    assert apunte.dia_hasta_incluido is True
    assert apunte.tratamiento == "FACTURAR"
    assert apunte.nombre_documento == "comunidad-agosto.pdf"


def test_modificar_apunte_invalido_no_cambia_el_original(
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
        fecha=date(2026, 8, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota original",
        base=10000,
        notas="Nota original",
    )

    with pytest.raises(
        ContabilidadError,
        match="base",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            inmueble=inmueble,
            categorias=categorias,
            fecha=date(2026, 9, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Concepto incorrecto",
            base=-1,
            notas="Nota incorrecta",
        )

    assert apunte.fecha == date(2026, 8, 1)
    assert apunte.concepto == "Cuota original"
    assert apunte.base == 10000
    assert apunte.total == 10000
    assert apunte.notas == "Nota original"


def test_apunte_creado_puede_persistirse(
    session,
    inmueble,
) -> None:
    categorias = {
        "GAS_TRIBUTOS": CategoriaContable(
            codigo="GAS_TRIBUTOS",
            naturaleza="GASTO",
            nombre="Tributos",
            activa=True,
            subcategorias=(
                SubcategoriaContable(
                    codigo="TRU",
                    nombre="Tasa de Residuos Urbanos",
                ),
            ),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 15),
        naturaleza="GASTO",
        categoria="GAS_TRIBUTOS",
        subcategoria="TRU",
        concepto="Tasa de residuos 2026",
        base=8750,
        referencia_documento="Recibo TRU 2026",
    )

    session.add(apunte)
    session.commit()

    apunte_id = apunte.id

    session.expire_all()

    guardado = session.get(
        ApunteContable,
        apunte_id,
    )

    assert guardado is not None
    assert guardado.inmueble_id == inmueble.id
    assert guardado.categoria == "GAS_TRIBUTOS"
    assert guardado.subcategoria == "TRU"
    assert guardado.base == 8750
    assert guardado.total == 8750
    assert guardado.referencia_documento == "Recibo TRU 2026"


def test_crear_apunte_contable_de_ingreso(
    session,
    inmueble,
) -> None:
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 9, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler de septiembre de 2026",
        base=100000,
        iva_importe=21000,
        retencion_importe=19000,
        total=102000,
        tercero_nombre="Empresa inquilina",
        tercero_nif="B12345678",
        referencia_documento="Factura 01/2026A1",
    )

    session.add(apunte)
    session.commit()

    assert apunte.id is not None
    assert apunte.inmueble is inmueble
    assert apunte.subcategoria is None
    assert apunte.ruta_documento == ""
    assert apunte.periodo_desde is None
    assert apunte.periodo_hasta is None
    assert apunte.tratamiento == "CONTABILIZAR"
    assert apunte.nombre_documento == ""


def test_crear_apunte_contable_con_subcategoria(
    session,
    inmueble,
) -> None:
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 9, 15),
        naturaleza="GASTO",
        categoria="GAS_REPARACIONES",
        subcategoria="FONTANERIA",
        concepto="Reparación de una tubería",
        base=10000,
        iva_importe=2100,
        total=12100,
    )

    session.add(apunte)
    session.commit()

    assert apunte.subcategoria == "FONTANERIA"
    assert apunte.retencion_importe == 0
    assert apunte.tercero_nombre == ""
    assert apunte.tercero_nif == ""


def test_apunte_contable_rechaza_naturaleza_desconocida(
    session,
    inmueble,
) -> None:
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 9, 1),
        naturaleza="DESCONOCIDA",
        categoria="ING_ALQUILERES",
        concepto="Concepto",
        base=10000,
        total=10000,
    )

    session.add(apunte)

    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    "campo",
    [
        "base",
        "iva_importe",
        "retencion_importe",
        "total",
    ],
)
def test_apunte_contable_rechaza_importes_negativos(
    session,
    inmueble,
    campo,
) -> None:
    datos = {
        "inmueble": inmueble,
        "fecha": date(2026, 9, 1),
        "naturaleza": "GASTO",
        "categoria": "GAS_OTROS",
        "concepto": "Concepto",
        "base": 10000,
        "iva_importe": 0,
        "retencion_importe": 0,
        "total": 10000,
    }

    datos[campo] = -1

    session.add(
        ApunteContable(**datos)
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_apunte_contable_admite_periodo(
    session,
    inmueble,
) -> None:
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 5, 20),
        naturaleza="GASTO",
        categoria="GAS_SERVICIOS_SUMINISTROS",
        subcategoria="AGUA",
        concepto="Suministro de agua",
        periodo_desde=date(2026, 3, 17),
        periodo_hasta=date(2026, 5, 14),
        dia_hasta_incluido=True,
        tratamiento="REPERCUTIR",
        nombre_documento=(
            "PISO-1-agua 2026-03-17 a 2026-05-14.pdf"
        ),
        base=10000,
        iva_importe=1000,
        retencion_importe=0,
        total=11000,
        tercero_nombre="Empresa de aguas",
        tercero_nif="A12345678",
        referencia_documento="F-2026-125",
        ruta_documento="",
        notas=None,
    )

    session.add(apunte)
    session.commit()

    assert apunte.periodo_desde == date(2026, 3, 17)
    assert apunte.periodo_hasta == date(2026, 5, 14)
    assert apunte.dia_hasta_incluido is True
    assert apunte.tratamiento == "REPERCUTIR"
    assert apunte.nombre_documento == (
        "PISO-1-agua 2026-03-17 a 2026-05-14.pdf"
    )


@pytest.mark.parametrize(
    (
        "periodo_desde",
        "periodo_hasta",
        "tratamiento",
    ),
    [
        (
            date(2026, 3, 17),
            None,
            "CONTABILIZAR",
        ),
        (
            None,
            date(2026, 5, 14),
            "CONTABILIZAR",
        ),
        (
            date(2026, 5, 14),
            date(2026, 3, 17),
            "CONTABILIZAR",
        ),
        (
            None,
            None,
            "DESCONOCIDO",
        ),
    ],
)
def test_apunte_contable_rechaza_periodo_o_tratamiento_invalido(
    session,
    inmueble,
    periodo_desde,
    periodo_hasta,
    tratamiento,
) -> None:
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 5, 20),
        naturaleza="GASTO",
        categoria="GAS_SERVICIOS_SUMINISTROS",
        subcategoria="AGUA",
        concepto="Suministro de agua",
        periodo_desde=periodo_desde,
        periodo_hasta=periodo_hasta,
        tratamiento=tratamiento,
        nombre_documento="agua.pdf",
        base=10000,
        iva_importe=1000,
        retencion_importe=0,
        total=11000,
        tercero_nombre="Empresa de aguas",
        tercero_nif="A12345678",
        referencia_documento="F-2026-125",
        ruta_documento="",
        notas=None,
    )

    session.add(apunte)

    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()


@pytest.mark.parametrize(
    (
        "periodo_desde",
        "periodo_hasta",
        "tratamiento",
        "mensaje",
    ),
    [
        (
            date(2026, 7, 1),
            None,
            "CONTABILIZAR",
            "dos fechas",
        ),
        (
            None,
            date(2026, 7, 31),
            "CONTABILIZAR",
            "dos fechas",
        ),
        (
            date(2026, 7, 31),
            date(2026, 7, 1),
            "CONTABILIZAR",
            "anterior",
        ),
        (
            None,
            None,
            "DESCONOCIDO",
            "tratamiento",
        ),
    ],
)


def test_crear_apunte_rechaza_periodo_o_tratamiento_invalido(
    inmueble,
    periodo_desde: date | None,
    periodo_hasta: date | None,
    tratamiento: str,
    mensaje: str,
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

    with pytest.raises(
        ContabilidadError,
        match=mensaje,
    ):
        crear_apunte_contable(
            inmueble=inmueble,
            categorias=categorias,
            fecha=date(2026, 8, 31),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Cuota de comunidad",
            periodo_desde=periodo_desde,
            periodo_hasta=periodo_hasta,
            tratamiento=tratamiento,
            base=10000,
        )


@pytest.mark.parametrize(
    "tratamiento",
    [
        "REPERCUTIR",
        "FACTURAR",
    ],
)
def test_apunte_admite_trasladar_o_facturar_sin_contrato(
    inmueble,
    tratamiento: str,
) -> None:
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 8, 31),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        tratamiento=tratamiento,
        base=10000,
    )

    assert apunte.tratamiento == tratamiento


def test_inmueble_subdividido_admite_facturar() -> None:
    inmueble, _, _ = (
        _inmueble_subdividido_para_distribuir()
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 8, 31),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        tratamiento="FACTURAR",
        base=10000,
    )

    assert apunte.tratamiento == "FACTURAR"
    assert len(apunte.distribuciones) == 2


def test_proponer_nombre_documento_sin_periodo(
    inmueble,
) -> None:
    nombre = proponer_nombre_documento(
        inmueble=inmueble,
        concepto="Impuesto IBI 2026",
    )

    assert nombre == (
        f"{inmueble.referencia}-Impuesto IBI 2026.pdf"
    )


def test_proponer_nombre_documento_para_mes(
    inmueble,
) -> None:
    nombre = proponer_nombre_documento(
        inmueble=inmueble,
        concepto="Agua",
        periodo_desde=date(2026, 3, 1),
        periodo_hasta=date(2026, 3, 31),
    )

    assert nombre == (
        f"{inmueble.referencia}-Agua 2026-03.pdf"
    )


def test_proponer_nombre_documento_para_intervalo(
    inmueble,
) -> None:
    nombre = proponer_nombre_documento(
        inmueble=inmueble,
        concepto="Agua",
        periodo_desde=date(2026, 3, 17),
        periodo_hasta=date(2026, 5, 14),
    )

    assert nombre == (
        f"{inmueble.referencia}-Agua "
        "2026-03-17 a 2026-05-14.pdf"
    )


def test_proponer_nombre_documento_elimina_separadores(
    inmueble,
) -> None:
    nombre = proponer_nombre_documento(
        inmueble=inmueble,
        concepto="Agua 03/2026",
    )

    assert "/" not in nombre
    assert "\\" not in nombre


def test_buscar_documentos_duplicados(
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
        concepto="Comunidad septiembre",
        base=10000,
        tercero_nombre="  Comunidad López  ",
        tercero_nif=" H12345678 ",
        referencia_documento=" FACTURA-125 ",
    )

    session.add(apunte)
    session.commit()

    duplicados = buscar_documentos_duplicados(
        session,
        tercero_nombre="Comunidad López",
        tercero_nif="h12345678",
        referencia_documento="factura-125",
    )

    assert duplicados == [apunte]

    duplicados = buscar_documentos_duplicados(
        session,
        tercero_nombre="Comunidad López",
        tercero_nif="H12345678",
        referencia_documento="factura-125",
        excluir_id=apunte.id,
    )

    assert duplicados == []


@pytest.mark.parametrize(
    "dia_hasta_incluido",
    [False, True],
)
def test_apunte_contable_admite_dia_hasta_incluido(
    session,
    inmueble,
    dia_hasta_incluido: bool,
) -> None:
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 5, 20),
        naturaleza="GASTO",
        categoria="GAS_SERVICIOS_SUMINISTROS",
        subcategoria="AGUA",
        concepto="Suministro de agua",
        periodo_desde=date(2026, 3, 17),
        periodo_hasta=date(2026, 5, 14),
        dia_hasta_incluido=dia_hasta_incluido,
        tratamiento="CONTABILIZAR",
        nombre_documento="agua.pdf",
        base=10000,
        iva_importe=1000,
        retencion_importe=0,
        total=11000,
        tercero_nombre="Empresa de aguas",
        tercero_nif="A12345678",
        referencia_documento="F-2026-125",
        ruta_documento="",
        notas=None,
    )

    session.add(apunte)
    session.commit()

    assert apunte.dia_hasta_incluido is dia_hasta_incluido


@pytest.mark.parametrize(
    (
        "periodo_desde",
        "periodo_hasta",
        "dia_hasta_incluido",
    ),
    [
        (None, None, True),
        (None, None, False),
        (
            date(2026, 3, 17),
            date(2026, 5, 14),
            None,
        ),
    ],
)
def test_apunte_contable_rechaza_dia_hasta_incluido_invalido(
    session,
    inmueble,
    periodo_desde,
    periodo_hasta,
    dia_hasta_incluido,
) -> None:
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 5, 20),
        naturaleza="GASTO",
        categoria="GAS_SERVICIOS_SUMINISTROS",
        subcategoria="AGUA",
        concepto="Suministro de agua",
        periodo_desde=periodo_desde,
        periodo_hasta=periodo_hasta,
        dia_hasta_incluido=dia_hasta_incluido,
        tratamiento="CONTABILIZAR",
        nombre_documento="agua.pdf",
        base=10000,
        iva_importe=1000,
        retencion_importe=0,
        total=11000,
        tercero_nombre="Empresa de aguas",
        tercero_nif="A12345678",
        referencia_documento="F-2026-125",
        ruta_documento="",
        notas=None,
    )

    session.add(apunte)

    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()


@pytest.mark.parametrize(
    "dia_hasta_incluido",
    [False, True],
)
def test_crear_apunte_admite_dia_hasta_incluido(
    inmueble,
    dia_hasta_incluido: bool,
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
        fecha=date(2026, 8, 31),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        periodo_desde=date(2026, 7, 1),
        periodo_hasta=date(2026, 7, 31),
        dia_hasta_incluido=dia_hasta_incluido,
        base=10000,
    )

    assert apunte.dia_hasta_incluido is dia_hasta_incluido


@pytest.mark.parametrize(
    (
        "periodo_desde",
        "periodo_hasta",
        "dia_hasta_incluido",
    ),
    [
        (None, None, True),
        (None, None, False),
        (
            date(2026, 7, 1),
            date(2026, 7, 31),
            None,
        ),
        (
            date(2026, 7, 1),
            date(2026, 7, 31),
            "SI",
        ),
        (
            date(2026, 7, 1),
            date(2026, 7, 31),
            1,
        ),
        (
            date(2026, 7, 1),
            date(2026, 7, 31),
            0,
        ),
    ],
)
def test_crear_apunte_rechaza_dia_hasta_incluido_invalido(
    inmueble,
    periodo_desde,
    periodo_hasta,
    dia_hasta_incluido,
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

    with pytest.raises(ContabilidadError):
        crear_apunte_contable(
            inmueble=inmueble,
            categorias=categorias,
            fecha=date(2026, 8, 31),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Cuota de comunidad",
            periodo_desde=periodo_desde,
            periodo_hasta=periodo_hasta,
            dia_hasta_incluido=dia_hasta_incluido,
            base=10000,
        )


def test_crear_apunte_rechaza_excluir_unico_dia() -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    categorias = _categorias_gastos_comunes()

    with pytest.raises(
        ContabilidadError,
        match="no contiene días efectivos",
    ):
        crear_apunte_contable(
            inmueble=inmueble,
            categorias=categorias,
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad",
            base=10000,
            periodo_desde=date(2026, 10, 1),
            periodo_hasta=date(2026, 10, 1),
            dia_hasta_incluido=False,
        )


def test_crear_apunte_subdividido_prepara_distribuciones() -> None:
    inmueble, local_a, local_b = (
        _inmueble_subdividido_para_distribuir()
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        iva_importe=2100,
        retencion_importe=1000,
    )

    assert len(apunte.distribuciones) == 2

    distribuciones = {
        distribucion.inmueble.referencia: distribucion
        for distribucion in apunte.distribuciones
    }

    assert set(distribuciones) == {
        "LOCAL-A",
        "LOCAL-B",
    }

    assert distribuciones["LOCAL-A"].inmueble is local_a
    assert distribuciones["LOCAL-B"].inmueble is local_b

    assert distribuciones["LOCAL-A"].participacion == 6000
    assert distribuciones["LOCAL-B"].participacion == 4000

    assert distribuciones["LOCAL-A"].base == 6000
    assert distribuciones["LOCAL-A"].iva_importe == 1260
    assert distribuciones["LOCAL-A"].retencion_importe == 600
    assert distribuciones["LOCAL-A"].total == 6660

    assert distribuciones["LOCAL-B"].base == 4000
    assert distribuciones["LOCAL-B"].iva_importe == 840
    assert distribuciones["LOCAL-B"].retencion_importe == 400
    assert distribuciones["LOCAL-B"].total == 4440


def test_distribucion_asigna_residuos_de_forma_determinista() -> None:
    inmueble, _, _ = (
        _inmueble_subdividido_para_distribuir()
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10001,
        iva_importe=2001,
        retencion_importe=1001,
    )

    distribuciones = sorted(
        apunte.distribuciones,
        key=lambda distribucion: distribucion.inmueble.referencia,
    )

    primera, ultima = distribuciones

    assert primera.base == 6001
    assert ultima.base == 4000

    assert primera.iva_importe == 1201
    assert ultima.iva_importe == 800

    assert primera.retencion_importe == 601
    assert ultima.retencion_importe == 400

    assert primera.total == 6601
    assert ultima.total == 4400

    assert sum(
        distribucion.base
        for distribucion in distribuciones
    ) == apunte.base

    assert sum(
        distribucion.iva_importe
        for distribucion in distribuciones
    ) == apunte.iva_importe

    assert sum(
        distribucion.retencion_importe
        for distribucion in distribuciones
    ) == apunte.retencion_importe

    assert sum(
        distribucion.total
        for distribucion in distribuciones
    ) == apunte.total


def test_distribucion_exige_participaciones_que_sumen_cien_por_cien() -> None:
    inmueble, _, local_b = (
        _inmueble_subdividido_para_distribuir()
    )

    local_b.participacion = 5000

    with pytest.raises(
        ContabilidadError,
        match="participaciones",
    ):
        crear_apunte_contable(
            inmueble=inmueble,
            categorias=_categorias_gastos_comunes(),
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad",
            base=10000,
        )


def test_crear_apunte_normal_no_prepara_distribuciones(
    inmueble,
) -> None:
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
    )

    assert apunte.distribuciones == []


def test_distribuciones_de_apunte_pueden_persistirse(
    session,
) -> None:
    inmueble, local_a, local_b = (
        _inmueble_subdividido_para_distribuir()
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        iva_importe=2100,
        retencion_importe=1000,
    )

    session.add(apunte)
    session.commit()

    distribuciones = session.scalars(
        select(DistribucionApunte)
    ).all()

    assert len(distribuciones) == 2

    por_referencia = {
        distribucion.inmueble.referencia: distribucion
        for distribucion in distribuciones
    }

    assert por_referencia["LOCAL-A"].apunte is apunte
    assert por_referencia["LOCAL-B"].apunte is apunte

    assert por_referencia["LOCAL-A"].inmueble is local_a
    assert por_referencia["LOCAL-B"].inmueble is local_b

    assert {
        distribucion.id
        for distribucion in apunte.distribuciones
    } == {
        distribucion.id
        for distribucion in distribuciones
    }


def test_distribucion_apunte_no_admite_local_duplicado(
    session,
) -> None:
    inmueble, _, _ = (
        _inmueble_subdividido_para_distribuir()
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
    )

    session.add(apunte)
    session.commit()

    original = apunte.distribuciones[0]

    duplicada = DistribucionApunte(
        apunte=apunte,
        inmueble=original.inmueble,
        participacion=original.participacion,
        base=original.base,
        iva_importe=original.iva_importe,
        retencion_importe=original.retencion_importe,
        total=original.total,
    )

    session.add(duplicada)

    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("participacion", 0),
        ("participacion", 10001),
        ("base", -1),
        ("iva_importe", -1),
        ("retencion_importe", -1),
        ("total", -1),
    ],
)
def test_distribucion_apunte_rechaza_importes_invalidos(
    session,
    campo: str,
    valor: int,
) -> None:
    inmueble, _, _ = (
        _inmueble_subdividido_para_distribuir()
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
    )

    distribucion = apunte.distribuciones[0]

    setattr(
        distribucion,
        campo,
        valor,
    )

    session.add(apunte)

    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()


def test_distribucion_apunte_exige_total_coherente(
    session,
) -> None:
    inmueble, _, _ = (
        _inmueble_subdividido_para_distribuir()
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        iva_importe=2100,
        retencion_importe=1000,
    )

    distribucion = apunte.distribuciones[0]

    distribucion.total += 1

    session.add(apunte)

    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()


def test_modificar_apunte_subdividido_recalcula_distribuciones(
    session,
) -> None:
    inmueble, _, _ = (
        _inmueble_subdividido_para_distribuir()
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        iva_importe=2100,
        retencion_importe=1000,
    )

    session.add(apunte)
    session.commit()

    modificar_apunte_contable(
        session,
        apunte=apunte,
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad corregida",
        base=20001,
        iva_importe=4001,
        retencion_importe=2001,
    )

    session.flush()

    distribuciones = sorted(
        apunte.distribuciones,
        key=lambda distribucion: distribucion.inmueble.referencia,
    )

    assert len(distribuciones) == 2

    primera, ultima = distribuciones

    assert primera.base == 12001
    assert primera.iva_importe == 2401
    assert primera.retencion_importe == 1201
    assert primera.total == 13201

    assert ultima.base == 8000
    assert ultima.iva_importe == 1600
    assert ultima.retencion_importe == 800
    assert ultima.total == 8800


def test_modificar_apunte_de_subdividido_a_normal_elimina_distribuciones(
    session,
    inmueble,
) -> None:
    subdividido, _, _ = (
        _inmueble_subdividido_para_distribuir()
    )

    apunte = crear_apunte_contable(
        inmueble=subdividido,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
    )

    session.add(apunte)
    session.commit()

    assert len(apunte.distribuciones) == 2

    modificar_apunte_contable(
        session,
        apunte=apunte,
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
    )

    session.flush()

    assert apunte.distribuciones == []


def test_eliminar_apunte_elimina_sus_distribuciones(
    session,
) -> None:
    inmueble, _, _ = (
        _inmueble_subdividido_para_distribuir()
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
    )

    session.add(apunte)
    session.commit()

    apunte_id = apunte.id

    assert session.scalar(
        select(DistribucionApunte)
        .where(
            DistribucionApunte.apunte_id
            == apunte_id
        )
    ) is not None

    eliminar_apunte_contable(
        session,
        apunte,
    )
    session.flush()

    assert session.get(
        ApunteContable,
        apunte_id,
    ) is None

    assert session.scalar(
        select(DistribucionApunte)
        .where(
            DistribucionApunte.apunte_id
            == apunte_id
        )
    ) is None


def test_reparto_contratos_sin_periodo_usa_contrato_vigente() -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    reparto, propietario = calcular_reparto_contratos(
        inmueble=inmueble,
        importe=10000,
        fecha=date(2026, 10, 1),
        periodo_desde=None,
        periodo_hasta=None,
        dia_hasta_incluido=None,
    )

    assert reparto == [
        (contrato, 10000),
    ]
    assert propietario == 0


def test_reparto_contratos_sin_periodo_sin_contrato_es_propietario() -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    reparto, propietario = calcular_reparto_contratos(
        inmueble=inmueble,
        importe=10000,
        fecha=date(2026, 10, 1),
        periodo_desde=None,
        periodo_hasta=None,
        dia_hasta_incluido=None,
    )

    assert reparto == []
    assert propietario == 10000


def test_reparto_contratos_prorratea_periodo_entre_dos_contratos() -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato_1 = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 10, 1),
        fecha_fin=date(2026, 10, 4),
    )

    contrato_2 = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 10, 5),
        fecha_fin=None,
    )

    reparto, propietario = calcular_reparto_contratos(
        inmueble=inmueble,
        importe=10001,
        fecha=date(2026, 10, 10),
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 10, 10),
        dia_hasta_incluido=True,
    )

    assert reparto == [
        (contrato_1, 4000),
        (contrato_2, 6001),
    ]
    assert propietario == 0


def test_reparto_contratos_deja_dias_sin_contrato_al_propietario() -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 10, 4),
        fecha_fin=date(2026, 10, 8),
    )

    reparto, propietario = calcular_reparto_contratos(
        inmueble=inmueble,
        importe=10000,
        fecha=date(2026, 10, 10),
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 10, 10),
        dia_hasta_incluido=True,
    )

    assert reparto == [
        (contrato, 5000),
    ]
    assert propietario == 5000


@pytest.mark.parametrize(
    (
        "dia_hasta_incluido",
        "esperado",
    ),
    [
        (
            True,
            [
                ("contrato_1", 900),
                ("contrato_2", 8100),
            ],
        ),
        (
            False,
            [
                ("contrato_1", 1000),
                ("contrato_2", 8000),
            ],
        ),
    ],
)
def test_reparto_contratos_respeta_dia_hasta_incluido(
    dia_hasta_incluido: bool,
    esperado,
) -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato_1 = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 10, 1),
        fecha_fin=date(2026, 10, 1),
    )

    contrato_2 = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 10, 2),
        fecha_fin=None,
    )

    reparto, propietario = calcular_reparto_contratos(
        inmueble=inmueble,
        importe=9000,
        fecha=date(2026, 10, 10),
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 10, 10),
        dia_hasta_incluido=dia_hasta_incluido,
    )

    contratos = {
        "contrato_1": contrato_1,
        "contrato_2": contrato_2,
    }

    assert reparto == [
        (contratos[nombre], importe)
        for nombre, importe in esperado
    ]
    assert propietario == 0


def test_reparto_contratos_rechaza_periodo_sin_dias_efectivos() -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    with pytest.raises(
        ContabilidadError,
        match="días efectivos",
    ):
        calcular_reparto_contratos(
            inmueble=inmueble,
            importe=10000,
            fecha=date(2026, 10, 1),
            periodo_desde=date(2026, 10, 1),
            periodo_hasta=date(2026, 10, 1),
            dia_hasta_incluido=False,
        )


def test_imputacion_contrato_persiste_origen_apunte(
    session,
    contrato,
) -> None:
    apunte = crear_apunte_contable(
        inmueble=contrato.inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    imputacion = ImputacionContrato(
        apunte=apunte,
        contrato=contrato,
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        importe=10000,
    )

    session.add(imputacion)
    session.commit()

    assert imputacion.id is not None
    assert imputacion.apunte is apunte
    assert imputacion.distribucion_apunte is None
    assert imputacion.contrato is contrato
    assert imputacion.importe == 10000


def test_imputacion_contrato_persiste_origen_distribucion(
    session,
) -> None:
    inmueble, local_a, _ = (
        _inmueble_subdividido_para_distribuir()
    )

    contrato = _contrato_para_imputacion(
        local_a,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    distribucion = next(
        distribucion
        for distribucion in apunte.distribuciones
        if distribucion.inmueble is local_a
    )

    imputacion = ImputacionContrato(
        distribucion_apunte=distribucion,
        contrato=contrato,
        base=distribucion.base,
        iva_importe=distribucion.iva_importe,
        retencion_importe=distribucion.retencion_importe,
        importe=distribucion.total,
    )

    session.add(imputacion)
    session.commit()

    assert imputacion.id is not None
    assert imputacion.apunte is None
    assert imputacion.distribucion_apunte is distribucion
    assert imputacion.contrato is contrato


@pytest.mark.parametrize(
    "usar_ambos_origenes",
    [
        False,
        True,
    ],
)
def test_imputacion_contrato_exige_un_unico_origen(
    session,
    contrato,
    usar_ambos_origenes: bool,
) -> None:
    apunte = None
    distribucion = None

    if usar_ambos_origenes:
        inmueble, local_a, _ = (
            _inmueble_subdividido_para_distribuir()
        )

        apunte_distribuido = crear_apunte_contable(
            inmueble=inmueble,
            categorias=_categorias_gastos_comunes(),
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad",
            base=10000,
        )

        distribucion = next(
            distribucion
            for distribucion
            in apunte_distribuido.distribuciones
            if distribucion.inmueble is local_a
        )

        apunte = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=_categorias_gastos_comunes(),
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad",
            base=10000,
        )

    imputacion = ImputacionContrato(
        apunte=apunte,
        distribucion_apunte=distribucion,
        contrato=contrato,
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        importe=10000,
    )

    session.add(imputacion)

    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()


@pytest.mark.parametrize(
    (
        "importe",
        "base",
        "retencion_importe",
    ),
    [
        (0, 0, 0),
        (-1, 0, 1),
    ],
)
def test_imputacion_contrato_exige_importe_positivo(
    session,
    contrato,
    importe: int,
    base: int,
    retencion_importe: int,
) -> None:
    apunte = crear_apunte_contable(
        inmueble=contrato.inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
    )

    imputacion = ImputacionContrato(
        apunte=apunte,
        contrato=contrato,
        base=base,
        iva_importe=0,
        retencion_importe=retencion_importe,
        importe=importe,
    )

    session.add(imputacion)

    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()


def test_imputacion_contrato_no_duplica_contrato_en_apunte(
    session,
    contrato,
) -> None:
    apunte = crear_apunte_contable(
        inmueble=contrato.inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
    )

    session.add_all([
        ImputacionContrato(
            apunte=apunte,
            contrato=contrato,
            base=5000,
            iva_importe=0,
            retencion_importe=0,
            importe=5000,
        ),
        ImputacionContrato(
            apunte=apunte,
            contrato=contrato,
            base=5000,
            iva_importe=0,
            retencion_importe=0,
            importe=5000,
        ),
    ])

    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()


def test_imputacion_contrato_no_duplica_contrato_en_distribucion(
    session,
) -> None:
    inmueble, local_a, _ = (
        _inmueble_subdividido_para_distribuir()
    )

    contrato = _contrato_para_imputacion(
        local_a,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
    )

    distribucion = next(
        distribucion
        for distribucion in apunte.distribuciones
        if distribucion.inmueble is local_a
    )

    session.add_all([
        ImputacionContrato(
            distribucion_apunte=distribucion,
            contrato=contrato,
            base=3000,
            iva_importe=0,
            retencion_importe=0,
            importe=3000,
        ),
        ImputacionContrato(
            distribucion_apunte=distribucion,
            contrato=contrato,
            base=3000,
            iva_importe=0,
            retencion_importe=0,
            importe=3000,
        ),
    ])

    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()


def test_preparar_imputaciones_apunte_normal_contrato_completo() -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
    )

    imputaciones, propietario = preparar_imputaciones_contrato(
        apunte=apunte,
    )

    assert propietario == 0
    assert len(imputaciones) == 1

    imputacion = imputaciones[0]

    assert imputacion.apunte is apunte
    assert imputacion.distribucion_apunte is None
    assert imputacion.contrato is contrato
    assert imputacion.importe == 10000


def test_preparar_imputaciones_apunte_normal_deja_resto_propietario() -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 10, 4),
        fecha_fin=date(2026, 10, 8),
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10001,
        iva_importe=2101,
        retencion_importe=1901,
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 10, 10),
        dia_hasta_incluido=True,
    )

    imputaciones, propietario = preparar_imputaciones_contrato(
        apunte=apunte,
    )

    assert propietario == 5100
    assert len(imputaciones) == 1

    imputacion = imputaciones[0]

    assert imputacion.apunte is apunte
    assert imputacion.distribucion_apunte is None
    assert imputacion.contrato is contrato

    assert imputacion.base == 5001
    assert imputacion.iva_importe == 1051
    assert imputacion.retencion_importe == 951
    assert imputacion.importe == 5101

    assert (
        imputacion.base
        + imputacion.iva_importe
        - imputacion.retencion_importe
        == imputacion.importe
    )


def test_preparar_imputaciones_apunte_subdividido_usa_distribuciones() -> None:
    inmueble, local_a, local_b = (
        _inmueble_subdividido_para_distribuir()
    )

    contrato_a = _contrato_para_imputacion(
        local_a,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    contrato_b = _contrato_para_imputacion(
        local_b,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10001,
        iva_importe=2101,
        retencion_importe=1901,
    )

    imputaciones, propietario = preparar_imputaciones_contrato(
        apunte=apunte,
    )

    assert propietario == 0
    assert len(imputaciones) == 2

    por_contrato = {
        imputacion.contrato: imputacion
        for imputacion in imputaciones
    }

    imputacion_a = por_contrato[contrato_a]
    imputacion_b = por_contrato[contrato_b]

    assert imputacion_a.apunte is None
    assert imputacion_b.apunte is None

    assert (
        imputacion_a.distribucion_apunte.inmueble
        is local_a
    )
    assert (
        imputacion_b.distribucion_apunte.inmueble
        is local_b
    )

    assert imputacion_a.base == 6001
    assert imputacion_a.iva_importe == 1261
    assert imputacion_a.retencion_importe == 1141
    assert imputacion_a.importe == 6121

    assert imputacion_b.base == 4000
    assert imputacion_b.iva_importe == 840
    assert imputacion_b.retencion_importe == 760
    assert imputacion_b.importe == 4080


def test_preparar_imputaciones_subdividido_sin_contrato_deja_parte_propietario() -> None:
    inmueble, local_a, local_b = (
        _inmueble_subdividido_para_distribuir()
    )

    contrato_a = _contrato_para_imputacion(
        local_a,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
    )

    imputaciones, propietario = preparar_imputaciones_contrato(
        apunte=apunte,
    )

    assert propietario == 4000
    assert len(imputaciones) == 1

    imputacion = imputaciones[0]

    assert imputacion.contrato is contrato_a
    assert imputacion.apunte is None
    assert (
        imputacion.distribucion_apunte.inmueble
        is local_a
    )
    assert imputacion.importe == 6000

    assert all(
        imputacion.distribucion_apunte.inmueble
        is not local_b
        for imputacion in imputaciones
    )


def test_buscar_gastos_repercutibles_pendientes_apunte_normal(
    session,
) -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    session.add_all([
        inmueble,
        contrato,
        apunte,
    ])
    session.commit()

    pendientes = (
        buscar_gastos_repercutibles_pendientes(
            session,
            contrato=contrato,
        )
    )

    assert len(pendientes) == 1

    pendiente = pendientes[0]

    assert pendiente.apunte is apunte
    assert pendiente.imputacion.apunte is apunte
    assert (
        pendiente.imputacion.distribucion_apunte
        is None
    )
    assert pendiente.imputacion.contrato is contrato
    assert pendiente.imputacion.importe == 10000


def test_buscar_gastos_repercutibles_pendientes_ignora_otros_tratamientos(
    session,
) -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    for tratamiento in (
        "CONTABILIZAR",
        "FACTURAR",
    ):
        apunte = crear_apunte_contable(
            inmueble=inmueble,
            categorias=_categorias_gastos_comunes(),
            fecha=date(2026, 10, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto=tratamiento,
            base=10000,
            tratamiento=tratamiento,
        )

        session.add(apunte)

    session.add_all([
        inmueble,
        contrato,
    ])
    session.commit()

    pendientes = (
        buscar_gastos_repercutibles_pendientes(
            session,
            contrato=contrato,
        )
    )

    assert pendientes == []


def test_buscar_gastos_repercutibles_pendientes_subdividido_muestra_apunte_original(
    session,
) -> None:
    inmueble, local_a, _ = (
        _inmueble_subdividido_para_distribuir()
    )

    contrato = _contrato_para_imputacion(
        local_a,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad edificio",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    session.add_all([
        inmueble,
        contrato,
        apunte,
    ])
    session.commit()

    pendientes = (
        buscar_gastos_repercutibles_pendientes(
            session,
            contrato=contrato,
        )
    )

    assert len(pendientes) == 1

    pendiente = pendientes[0]

    assert pendiente.apunte is apunte
    assert pendiente.imputacion.apunte is None
    assert (
        pendiente.imputacion
        .distribucion_apunte
        .apunte
        is apunte
    )
    assert (
        pendiente.imputacion
        .distribucion_apunte
        .inmueble
        is local_a
    )
    assert pendiente.imputacion.importe == 6000


def test_gasto_repercutible_puede_estar_gestionado_para_un_contrato_y_pendiente_para_otro(
    session,
) -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato_1 = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 10, 1),
        fecha_fin=date(2026, 10, 4),
    )

    contrato_2 = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 10, 5),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 10, 10),
        dia_hasta_incluido=True,
        tratamiento="REPERCUTIR",
    )

    session.add_all([
        inmueble,
        contrato_1,
        contrato_2,
        apunte,
    ])
    session.commit()

    session.add(
        ImputacionContrato(
            apunte=apunte,
            contrato=contrato_1,
            base=4000,
            iva_importe=0,
            retencion_importe=0,
            importe=4000,
        )
    )
    session.commit()

    pendientes_1 = (
        buscar_gastos_repercutibles_pendientes(
            session,
            contrato=contrato_1,
        )
    )

    pendientes_2 = (
        buscar_gastos_repercutibles_pendientes(
            session,
            contrato=contrato_2,
        )
    )

    assert pendientes_1 == []

    assert len(pendientes_2) == 1
    assert pendientes_2[0].apunte is apunte
    assert (
        pendientes_2[0].imputacion.contrato
        is contrato_2
    )
    assert pendientes_2[0].imputacion.importe == 6000


def test_reparto_detallado_conserva_dias_del_prorrateo() -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 7, 1),
        fecha_fin=None,
    )

    reparto, propietario, dias_totales = (
        calcular_reparto_contratos_detallado(
            inmueble=inmueble,
            importe=2839,
            fecha=date(2026, 8, 13),
            periodo_desde=date(2026, 6, 1),
            periodo_hasta=date(2026, 8, 1),
            dia_hasta_incluido=False,
        )
    )

    assert dias_totales == 61
    assert propietario == 1396

    assert len(reparto) == 1

    parte = reparto[0]

    assert parte.contrato is contrato
    assert parte.dias == 31
    assert parte.importe == 1443


def test_reparto_detallado_sin_periodo_no_tiene_dias() -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    reparto, propietario, dias_totales = (
        calcular_reparto_contratos_detallado(
            inmueble=inmueble,
            importe=10000,
            fecha=date(2026, 10, 1),
            periodo_desde=None,
            periodo_hasta=None,
            dia_hasta_incluido=None,
        )
    )

    assert propietario == 0
    assert dias_totales is None
    assert len(reparto) == 1
    assert reparto[0].contrato is contrato
    assert reparto[0].importe == 10000
    assert reparto[0].dias is None


def test_modificar_apunte_con_imputacion_persistida_rechaza_cambio_economico(
    session,
) -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
    )

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

    with pytest.raises(
        ContabilidadError,
        match="imputaciones",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            inmueble=inmueble,
            categorias=_categorias_gastos_comunes(),
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad",
            base=12000,
            tratamiento="REPERCUTIR",
        )

    assert apunte.base == 10000
    assert apunte.total == 10000


@pytest.mark.parametrize(
    "cambios",
    [
        {
            "fecha": date(2026, 10, 2),
        },
        {
            "base": 12000,
        },
        {
            "iva_importe": 2100,
        },
        {
            "retencion_importe": 1000,
        },
        {
            "periodo_desde": date(2026, 9, 1),
            "periodo_hasta": date(2026, 9, 30),
            "dia_hasta_incluido": True,
        },
        {
            "dia_hasta_incluido": False,
        },
        {
            "tratamiento": "FACTURAR",
        },
    ],
)
def test_modificar_apunte_con_imputacion_persistida_rechaza_cambios_de_reparto(
    session,
    cambios,
) -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 10, 31),
        dia_hasta_incluido=True,
    )

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

    datos = {
        "fecha": apunte.fecha,
        "base": apunte.base,
        "iva_importe": apunte.iva_importe,
        "retencion_importe": apunte.retencion_importe,
        "periodo_desde": apunte.periodo_desde,
        "periodo_hasta": apunte.periodo_hasta,
        "dia_hasta_incluido": apunte.dia_hasta_incluido,
        "tratamiento": apunte.tratamiento,
    }

    datos.update(cambios)

    with pytest.raises(
        ContabilidadError,
        match="imputaciones",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            inmueble=inmueble,
            categorias=_categorias_gastos_comunes(),
            fecha=datos["fecha"],
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad",
            base=datos["base"],
            iva_importe=datos["iva_importe"],
            retencion_importe=datos["retencion_importe"],
            periodo_desde=datos["periodo_desde"],
            periodo_hasta=datos["periodo_hasta"],
            dia_hasta_incluido=datos["dia_hasta_incluido"],
            tratamiento=datos["tratamiento"],
        )


def test_modificar_apunte_con_imputacion_persistida_permite_cambiar_notas(
    session,
) -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
        notas="Nota original",
    )

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

    modificar_apunte_contable(
        session,
        apunte=apunte,
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=apunte.fecha,
        naturaleza=apunte.naturaleza,
        categoria=apunte.categoria,
        concepto=apunte.concepto,
        base=apunte.base,
        iva_importe=apunte.iva_importe,
        retencion_importe=apunte.retencion_importe,
        periodo_desde=apunte.periodo_desde,
        periodo_hasta=apunte.periodo_hasta,
        dia_hasta_incluido=apunte.dia_hasta_incluido,
        tratamiento=apunte.tratamiento,
        notas="Nota corregida",
    )

    assert apunte.notas == "Nota corregida"


def test_modificar_apunte_subdividido_con_imputacion_persistida_rechaza_cambio_economico(
    session,
) -> None:
    inmueble, local_a, _ = (
        _inmueble_subdividido_para_distribuir()
    )

    contrato = _contrato_para_imputacion(
        local_a,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    distribucion = next(
        distribucion
        for distribucion in apunte.distribuciones
        if distribucion.inmueble is local_a
    )

    imputacion = ImputacionContrato(
        distribucion_apunte=distribucion,
        contrato=contrato,
        base=distribucion.base,
        iva_importe=distribucion.iva_importe,
        retencion_importe=distribucion.retencion_importe,
        importe=distribucion.total,
    )

    session.add_all([
        inmueble,
        contrato,
        apunte,
        imputacion,
    ])
    session.commit()

    with pytest.raises(
        ContabilidadError,
        match="imputaciones",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            inmueble=inmueble,
            categorias=_categorias_gastos_comunes(),
            fecha=apunte.fecha,
            naturaleza=apunte.naturaleza,
            categoria=apunte.categoria,
            concepto=apunte.concepto,
            base=12000,
            iva_importe=apunte.iva_importe,
            retencion_importe=apunte.retencion_importe,
            periodo_desde=apunte.periodo_desde,
            periodo_hasta=apunte.periodo_hasta,
            dia_hasta_incluido=apunte.dia_hasta_incluido,
            tratamiento=apunte.tratamiento,
        )

    assert apunte.base == 10000


def test_eliminar_apunte_con_imputacion_persistida_se_rechaza(
    session,
) -> None:
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
    )

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

    with pytest.raises(
        ContabilidadError,
        match="imputaciones",
    ):
        eliminar_apunte_contable(
            session,
            apunte,
        )

    assert session.get(
        ApunteContable,
        apunte.id,
    ) is apunte


def test_preparar_apuntes_automaticos_crea_apunte_y_previsto(
    session,
    inmueble,
) -> None:
    categorias = _categorias_gastos_comunes()

    configurados = [
        ApunteAutomatico(
            inmueble_referencia="LOCAL-1",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad",
            base=8735,
        ),
    ]

    # El usuario prepara noviembre desde Facturación.
    preparados = preparar_apuntes_automaticos(
        session,
        configurados=configurados,
        categorias=categorias,
        periodo=date(2026, 11, 1),
    )

    assert len(preparados) == 1

    apunte = preparados[0].apunte
    previsto = preparados[0].movimiento_previsto

    # El apunte corresponde al mes de noviembre.
    assert apunte.inmueble is inmueble
    assert apunte.fecha == date(2026, 11, 1)
    assert apunte.periodo_desde == date(2026, 11, 1)
    assert apunte.periodo_hasta == date(2026, 11, 30)
    assert apunte.dia_hasta_incluido is True

    assert apunte.naturaleza == "GASTO"
    assert apunte.categoria == "GAS_COMUNIDAD"
    assert apunte.concepto == "Comunidad 11/2026"
    assert apunte.tratamiento == "CONTABILIZAR"

    assert apunte.base == 8735
    assert apunte.iva_importe == 0
    assert apunte.retencion_importe == 0
    assert apunte.total == 8735

    # El previsto conserva un margen amplio de conciliación.
    assert previsto.apunte is apunte
    assert previsto.inmueble is inmueble
    assert previsto.naturaleza == "GASTO"
    assert previsto.concepto == "Comunidad 11/2026"
    assert previsto.importe_esperado == 8735

    assert previsto.fecha_prevista_desde == date(2026, 10, 20)
    assert previsto.fecha_prevista_hasta == date(2026, 11, 30)
    assert previsto.estado == "PENDIENTE"


def test_preparar_apuntes_automaticos_rechaza_duplicado_sin_comparar_importe(
    session,
    inmueble,
) -> None:
    categorias = _categorias_gastos_comunes()

    # Ya existe un apunte de comunidad de noviembre.
    existente = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 11, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad 11/2026",
        base=8735,
        periodo_desde=date(2026, 11, 1),
        periodo_hasta=date(2026, 11, 30),
        dia_hasta_incluido=True,
    )

    session.add(existente)
    session.commit()

    # El archivo contiene el mismo gasto, pero con otro importe.
    configurados = [
        ApunteAutomatico(
            inmueble_referencia="LOCAL-1",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad",
            base=9000,
        ),
    ]

    # El usuario intenta generar noviembre otra vez.
    with pytest.raises(
        ContabilidadError,
        match="existe",
    ):
        preparar_apuntes_automaticos(
            session,
            configurados=configurados,
            categorias=categorias,
            periodo=date(2026, 11, 1),
        )

    # El apunte original permanece sin modificaciones.
    apuntes = session.scalars(
        select(ApunteContable)
    ).all()

    assert len(apuntes) == 1
    assert apuntes[0].id == existente.id
    assert apuntes[0].base == 8735


@pytest.mark.parametrize(
    ("referencia", "categoria", "mensaje"),
    [
        (
            "LOCAL-INEXISTENTE",
            "GAS_COMUNIDAD",
            "inmueble",
        ),
        (
            "LOCAL-1",
            "GAS_INEXISTENTE",
            "categoría",
        ),
    ],
)
def test_preparar_apuntes_automaticos_rechaza_configuracion_invalida(
    session,
    inmueble,
    referencia: str,
    categoria: str,
    mensaje: str,
) -> None:
    categorias = _categorias_gastos_comunes()

    configurados = [
        ApunteAutomatico(
            inmueble_referencia=referencia,
            categoria=categoria,
            concepto="Comunidad",
            base=8735,
        ),
    ]

    # El usuario intenta generar apuntes con datos incorrectos.
    with pytest.raises(
        ContabilidadError,
        match=mensaje,
    ):
        preparar_apuntes_automaticos(
            session,
            configurados=configurados,
            categorias=categorias,
            periodo=date(2026, 11, 1),
        )

    # No debe haberse creado ningún apunte.
    apuntes = session.scalars(
        select(ApunteContable)
    ).all()

    assert apuntes == []


def test_preparar_apuntes_automaticos_rechaza_todo_si_hay_duplicado(
    session,
    inmueble,
) -> None:
    categorias = _categorias_gastos_comunes()

    # El usuario ya contabilizó Comunidad de noviembre.
    existente = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 11, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad 11/2026",
        base=8735,
        periodo_desde=date(2026, 11, 1),
        periodo_hasta=date(2026, 11, 30),
        dia_hasta_incluido=True,
    )

    session.add(existente)
    session.commit()

    # El usuario intenta generar dos apuntes del mes.
    # El primero es nuevo, pero el segundo ya existe.
    configurados = [
        ApunteAutomatico(
            inmueble_referencia="LOCAL-1",
            categoria="GAS_COMUNIDAD",
            concepto="Limpieza",
            base=2500,
        ),
        ApunteAutomatico(
            inmueble_referencia="LOCAL-1",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad",
            base=9000,
        ),
    ]

    with pytest.raises(
        ContabilidadError,
        match="existe",
    ):
        preparar_apuntes_automaticos(
            session,
            configurados=configurados,
            categorias=categorias,
            periodo=date(2026, 11, 1),
        )

    # La preparación fallida no deja objetos pendientes
    # de insertar en la sesión.
    assert not session.new

    # El único apunte registrado sigue siendo el original.
    apuntes = session.scalars(
        select(ApunteContable)
    ).all()

    assert len(apuntes) == 1
    assert apuntes[0].id == existente.id
    assert apuntes[0].base == 8735


def test_apunte_contable_persiste_importe_negativo(
    session,
    inmueble,
) -> None:
    """Conserva el signo sin almacenar importes negativos."""

    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 26),
        naturaleza="GASTO",
        categoria="GAS_SERVICIOS_SUMINISTROS",
        subcategoria="GAS",
        concepto="Devolución de recibos de gas",
        tratamiento="CONTABILIZAR",
        base=3000,
        iva_importe=0,
        retencion_importe=0,
        total=3000,
        importe_negativo=True,
    )

    session.add(apunte)
    session.commit()

    apunte_id = apunte.id

    # Se vuelve a leer el apunte desde SQLite.
    session.expire_all()

    guardado = session.get(
        ApunteContable,
        apunte_id,
    )

    assert guardado is not None
    assert guardado.importe_negativo is True

    # Los componentes económicos siguen siendo positivos.
    assert guardado.base == 3000
    assert guardado.iva_importe == 0
    assert guardado.retencion_importe == 0
    assert guardado.total == 3000

    assert guardado.naturaleza == "GASTO"
    assert guardado.tratamiento == "CONTABILIZAR"


def test_apunte_contable_es_positivo_por_defecto(
    session,
    inmueble,
) -> None:
    """Los apuntes sin signo explícito conservan el comportamiento anterior."""

    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 26),
        naturaleza="GASTO",
        categoria="GAS_SERVICIOS_SUMINISTROS",
        subcategoria="GAS",
        concepto="Recibo ordinario de gas",
        tratamiento="CONTABILIZAR",
        base=8500,
        iva_importe=0,
        retencion_importe=0,
        total=8500,
    )

    session.add(apunte)
    session.commit()

    apunte_id = apunte.id

    # Se recupera el apunte sin depender del objeto original.
    session.expire_all()

    guardado = session.get(
        ApunteContable,
        apunte_id,
    )

    assert guardado is not None
    assert guardado.importe_negativo is False

    assert guardado.base == 8500
    assert guardado.total == 8500


@pytest.mark.parametrize(
    "tratamiento",
    ["CONTABILIZAR", "REPERCUTIR"],
)
def test_crear_apunte_contable_negativo(
    inmueble,
    tratamiento: str,
) -> None:
    categorias = _categorias_gastos_comunes()

    # El usuario registra un abono de un gasto anterior.
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 26),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Devolución de cuota",
        base=3000,
        iva_importe=630,
        retencion_importe=0,
        tratamiento=tratamiento,
        importe_negativo=True,
    )

    # El signo se guarda aparte; los importes siguen positivos.
    assert apunte.importe_negativo is True
    assert apunte.base == 3000
    assert apunte.iva_importe == 630
    assert apunte.retencion_importe == 0
    assert apunte.total == 3630
    assert apunte.tratamiento == tratamiento


def test_modificar_signo_apunte_contable(
    session,
    inmueble,
) -> None:
    categorias = _categorias_gastos_comunes()

    # El usuario crea inicialmente un gasto positivo.
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 26),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
        tratamiento="CONTABILIZAR",
    )

    assert apunte.importe_negativo is False

    # El usuario edita el apunte para convertirlo en un abono.
    resultado = modificar_apunte_contable(
        session,
        apunte=apunte,
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 26),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Devolución de cuota",
        base=10000,
        tratamiento="CONTABILIZAR",
        importe_negativo=True,
    )

    assert resultado is apunte
    assert apunte.importe_negativo is True
    assert apunte.base == 10000
    assert apunte.total == 10000

    # El usuario vuelve a editarlo para dejarlo positivo.
    modificar_apunte_contable(
        session,
        apunte=apunte,
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 26),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
        tratamiento="CONTABILIZAR",
        importe_negativo=False,
    )

    assert apunte.importe_negativo is False
    assert apunte.base == 10000
    assert apunte.total == 10000


@pytest.mark.parametrize(
    "estado",
    ["CONCILIADO", "PARCIAL"],
)
def test_modificar_signo_apunte_con_movimiento_conciliado_se_rechaza(
    session,
    inmueble,
    estado: str,
) -> None:
    categorias = _categorias_gastos_comunes()

    # El usuario registra un gasto y su movimiento previsto.
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
        tratamiento="CONTABILIZAR",
    )

    movimiento = MovimientoPrevisto(
        inmueble=inmueble,
        apunte=apunte,
        naturaleza="GASTO",
        concepto="Cuota de comunidad",
        importe_esperado=10000,
        estado=estado,
    )

    session.add_all([apunte, movimiento])
    session.commit()

    # El usuario intenta invertir el signo de un apunte
    # cuyo movimiento ya está conciliado o parcialmente conciliado.
    with pytest.raises(
        ContabilidadError,
        match="conciliado",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            inmueble=inmueble,
            categorias=categorias,
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Cuota de comunidad",
            base=10000,
            tratamiento="CONTABILIZAR",
            importe_negativo=True,
        )

    # El intento rechazado no debe alterar los datos.
    assert apunte.importe_negativo is False
    assert apunte.base == 10000
    assert apunte.total == 10000
    assert movimiento.naturaleza == "GASTO"
    assert movimiento.importe_esperado == 10000


def test_modificar_signo_apunte_con_imputacion_persistida_se_rechaza(
    session,
    contrato,
) -> None:
    inmueble = contrato.inmueble
    categorias = _categorias_gastos_comunes()

    # El usuario registra un gasto que se repercute al inquilino.
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    # La repercusión se registra y queda persistida.
    imputacion = ImputacionContrato(
        apunte=apunte,
        contrato=contrato,
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        importe=10000,
    )

    session.add_all([apunte, imputacion])
    session.commit()

    # El usuario intenta convertir el gasto en un abono
    # después de haber registrado su repercusión.
    with pytest.raises(
        ContabilidadError,
        match="imputaciones",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            inmueble=inmueble,
            categorias=categorias,
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Cuota de comunidad",
            base=10000,
            tratamiento="REPERCUTIR",
            importe_negativo=True,
        )

    # El intento rechazado no modifica el apunte ni la imputación.
    assert apunte.importe_negativo is False
    assert apunte.base == 10000
    assert apunte.total == 10000
    assert imputacion.importe == 10000


@pytest.mark.parametrize(
    (
        "signo_inicial",
        "signo_final",
        "naturaleza_inicial",
        "naturaleza_final",
    ),
    [
        (False, True, "GASTO", "INGRESO"),
        (True, False, "INGRESO", "GASTO"),
    ],
)
def test_modificar_signo_apunte_actualiza_movimiento_pendiente(
    session,
    inmueble,
    signo_inicial: bool,
    signo_final: bool,
    naturaleza_inicial: str,
    naturaleza_final: str,
) -> None:
    categorias = _categorias_gastos_comunes()

    # El usuario crea un apunte y su movimiento previsto.
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 26),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Regularización de comunidad",
        base=10000,
        tratamiento="CONTABILIZAR",
        importe_negativo=signo_inicial,
    )

    movimiento = MovimientoPrevisto(
        inmueble=inmueble,
        apunte=apunte,
        naturaleza=naturaleza_inicial,
        concepto=apunte.concepto,
        importe_esperado=10000,
        estado="PENDIENTE",
    )

    session.add_all([apunte, movimiento])
    session.commit()

    movimiento_id = movimiento.id

    # El usuario modifica el signo del apunte.
    modificar_apunte_contable(
        session,
        apunte=apunte,
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 26),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Regularización de comunidad",
        base=10000,
        tratamiento="CONTABILIZAR",
        importe_negativo=signo_final,
    )

    session.commit()

    # El movimiento previsto existente cambia de sentido.
    assert apunte.importe_negativo is signo_final
    assert apunte.base == 10000
    assert apunte.total == 10000

    assert movimiento.id == movimiento_id
    assert movimiento.naturaleza == naturaleza_final
    assert movimiento.importe_esperado == 10000
    assert movimiento.estado == "PENDIENTE"

    # No se ha creado ningún movimiento adicional.
    movimientos = session.scalars(
        select(MovimientoPrevisto).where(
            MovimientoPrevisto.apunte_id == apunte.id
        )
    ).all()

    assert len(movimientos) == 1
    assert movimientos[0].id == movimiento_id


def test_preparar_registro_contable_alquiler(
    contrato, categorias,
):
    registro = preparar_registro_contable(
        inmueble=contrato.inmueble,
        categorias=categorias,
        fecha=date(2026, 6, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler junio",
        base=85000,
    )

    assert registro.apunte.categoria == "ING_ALQUILERES"

    movimiento = registro.movimiento_previsto

    assert movimiento is not None
    assert movimiento.apunte is registro.apunte
    assert movimiento.contrato is contrato
    assert movimiento.importe_esperado == 85000


def test_preparar_registro_contable_distribuye_inmueble_t():
    inmueble, local_a, local_b = (
        _inmueble_subdividido_para_distribuir()
    )

    registro = preparar_registro_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 6, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad junio",
        base=10000,
    )

    distribuciones = {
        distribucion.inmueble.referencia:
        distribucion.base
        for distribucion in registro.apunte.distribuciones
    }

    assert distribuciones == {
        local_a.referencia: 6000,
        local_b.referencia: 4000,
    }

    assert registro.movimiento_previsto is not None
    assert registro.movimiento_previsto.apunte is registro.apunte
    assert registro.movimiento_previsto.importe_esperado == 10000


def test_preparar_registro_contable_sin_movimiento(
    inmueble, categorias,
):
    registro = preparar_registro_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 6, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler junio",
        base=85000,
        crear_movimiento=False,
    )

    assert registro.apunte.total == 85000
    assert registro.movimiento_previsto is None


def test_registro_calcula_reparto_contrato_y_propietario():
    inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato_para_imputacion(
        inmueble,
        fecha_inicio=date(2026, 10, 4),
        fecha_fin=date(2026, 10, 8),
    )

    registro = preparar_registro_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 10, 10),
        dia_hasta_incluido=True,
        tratamiento="REPERCUTIR",
        calcular_imputaciones=True,
    )

    assert len(registro.imputaciones_contrato) == 1

    imputacion = registro.imputaciones_contrato[0]

    assert imputacion.contrato is contrato
    assert imputacion.apunte is registro.apunte
    assert imputacion.importe == 5000
    assert registro.importe_propietario == 5000

    assert registro.movimiento_previsto is not None
    assert registro.movimiento_previsto.importe_esperado == 10000


def test_registro_calcula_imputaciones_inmueble_t():
    inmueble, local_a, local_b = (
        _inmueble_subdividido_para_distribuir()
    )

    contrato_a = _contrato_para_imputacion(
        local_a,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    registro = preparar_registro_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
        calcular_imputaciones=True,
    )

    assert len(registro.apunte.distribuciones) == 2
    assert len(registro.imputaciones_contrato) == 1

    imputacion = registro.imputaciones_contrato[0]

    assert imputacion.contrato is contrato_a
    assert imputacion.distribucion_apunte.inmueble is local_a
    assert imputacion.importe == 6000

    assert registro.importe_propietario == 4000

    assert registro.movimiento_previsto is not None
    assert registro.movimiento_previsto.importe_esperado == 10000


def test_registro_calcula_imputaciones_sin_persistirlas(
    session, contrato,
):
    registro = preparar_registro_contable(
        inmueble=contrato.inmueble,
        categorias=_categorias_gastos_comunes(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad octubre",
        base=10000,
        tratamiento="REPERCUTIR",
        calcular_imputaciones=True,
    )

    assert len(registro.imputaciones_contrato) == 1
    assert registro.imputaciones_contrato[0].contrato is contrato
    assert registro.importe_propietario == 0

    # Se guardan únicamente el apunte y su previsto.
    session.add(registro.apunte)
    session.add(registro.movimiento_previsto)
    session.commit()

    # Calcular el reparto no debe persistir las imputaciones.
    assert session.scalars(
        select(ImputacionContrato)
    ).all() == []

    # El gasto continúa pendiente de repercutir.
    pendientes = buscar_gastos_repercutibles_pendientes(
        session,
        contrato=contrato,
    )

    assert len(pendientes) == 1
    assert pendientes[0].imputacion.importe == 10000


@pytest.mark.parametrize(
    "cambios",
    [
        {"fecha": date(2026, 10, 2)},
        {
            "naturaleza": "GASTO",
            "categoria": "GAS_COMUNIDAD",
        },
        {"categoria": "ING_OTROS"},
        {"subcategoria": "LOCAL"},
        {"periodo_desde": date(2026, 10, 2)},
        {"periodo_hasta": date(2026, 10, 30)},
        {"dia_hasta_incluido": False},
        {"base": 120000},
        {"iva_importe": 22000},
        {"retencion_importe": 20000},
        {
            "base": 101000,
            "iva_importe": 20000,
        },
        {"importe_negativo": True},
        {"tercero_nombre": "Otro destinatario"},
        {"tercero_nif": "22222222B"},
        {"referencia_documento": "OTRA-FACTURA"},
    ],
)
def test_modificar_apunte_con_factura_rechaza_campos_protegidos(
    session,
    apunte_con_factura,
    cambios,
) -> None:
    """Una factura protege los datos contables que ha generado."""

    factura, apunte, movimiento, categorias = (
        apunte_con_factura
    )

    datos_originales = _datos_edicion_apunte(apunte)
    datos = datos_originales.copy()
    datos.update(cambios)

    # Simular que se ha incorporado una subcategoría
    # a la configuración después de emitir la factura.
    if "subcategoria" in cambios:
        categorias = categorias.copy()

        categorias["ING_ALQUILERES"] = CategoriaContable(
            codigo="ING_ALQUILERES",
            naturaleza="INGRESO",
            nombre="Alquileres",
            activa=True,
            subcategorias=(
                SubcategoriaContable(
                    codigo="LOCAL",
                    nombre="Local",
                    activa=True,
                ),
            ),
        )

    # El usuario intenta modificar un dato protegido
    # del apunte generado por la factura.
    with pytest.raises(
        ContabilidadError,
        match="factura",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias,
            **datos,
        )

    # Ningún dato del apunte debe haber cambiado.
    assert _datos_edicion_apunte(apunte) == datos_originales

    assert factura.apunte_contable is apunte
    assert apunte.base == factura.base
    assert apunte.iva_importe == factura.iva_importe
    assert apunte.retencion_importe == factura.retencion_importe
    assert apunte.total == factura.total

    assert movimiento.apunte is apunte
    assert movimiento.importe_esperado == factura.total
    assert movimiento.estado == "PENDIENTE"


def test_modificar_apunte_con_factura_rechaza_cambio_inmueble(
    session,
    apunte_con_factura,
) -> None:
    """El apunte no puede trasladarse a otro inmueble."""

    factura, apunte, movimiento, categorias = (
        apunte_con_factura
    )

    inmueble_original = apunte.inmueble

    otro_inmueble = _crear_inmueble_prueba(
        referencia="OTRO-LOCAL",
        tipo="L",
        codigo_facturacion="OL",
        descripcion="Otro local",
        direccion="Otra dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    session.add(otro_inmueble)
    session.commit()

    datos = _datos_edicion_apunte(apunte)
    datos["inmueble"] = otro_inmueble

    # El usuario intenta trasladar el ingreso
    # de la factura a otro inmueble.
    with pytest.raises(
        ContabilidadError,
        match="factura",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias,
            **datos,
        )

    assert apunte.inmueble is inmueble_original
    assert movimiento.inmueble is inmueble_original
    assert factura.apunte_contable is apunte
    assert factura.contrato.inmueble is inmueble_original


def test_modificar_apunte_con_factura_permite_datos_descriptivos(
    session,
    apunte_con_factura,
) -> None:
    """Los datos descriptivos pueden corregirse sin alterar la factura."""

    factura, apunte, movimiento, categorias = (
        apunte_con_factura
    )

    datos_antes = _datos_edicion_apunte(apunte)

    lineas_antes = [
        (linea.concepto, linea.importe)
        for linea in factura.lineas
    ]

    cambios = {
        "concepto": "Alquiler de octubre corregido",
        "notas": "Nota aclaratoria",
        "nombre_documento": "Factura octubre.pdf",
        "ruta_documento": "/facturas/2026",
    }

    datos = datos_antes.copy()
    datos.update(cambios)

    # El usuario corrige exclusivamente información descriptiva.
    modificar_apunte_contable(
        session,
        apunte=apunte,
        categorias=categorias,
        **datos,
    )

    session.commit()

    assert _datos_edicion_apunte(apunte) == datos

    # El movimiento previsto conserva su coherencia
    # con el apunte contable.
    assert movimiento.concepto == cambios["concepto"]
    assert movimiento.importe_esperado == factura.total
    assert movimiento.estado == "PENDIENTE"

    # La factura emitida conserva su información histórica.
    assert factura.apunte_contable is apunte

    assert [
        (linea.concepto, linea.importe)
        for linea in factura.lineas
    ] == lineas_antes

    assert factura.base == apunte.base
    assert factura.iva_importe == apunte.iva_importe
    assert factura.retencion_importe == apunte.retencion_importe
    assert factura.total == apunte.total


@pytest.mark.parametrize(
    "cambios",
    [
        {
            "naturaleza": "GASTO",
            "categoria": "GAS_COMUNIDAD",
        },
        {"categoria": "ING_OTROS"},
        {"periodo_desde": date(2026, 10, 2)},
        {"periodo_hasta": date(2026, 10, 30)},
        {"dia_hasta_incluido": False},
        {
            "periodo_desde": date(2026, 11, 1),
            "periodo_hasta": date(2026, 11, 30),
        },
        {
            "periodo_desde": None,
            "periodo_hasta": None,
            "dia_hasta_incluido": None,
        },
        {"importe_negativo": True},
    ],
)
def test_modificar_apunte_alquiler_rechaza_cambio_identidad(
    session,
    apunte_alquiler_sin_factura,
    cambios,
) -> None:
    """Un alquiler contabilizado conserva su identidad contractual."""

    apunte, movimiento, categorias = (
        apunte_alquiler_sin_factura
    )

    contrato_original = movimiento.contrato

    datos_originales = _datos_edicion_apunte(apunte)
    datos = datos_originales.copy()
    datos.update(cambios)

    # El usuario intenta modificar la identidad
    # de un alquiler ya contabilizado.
    with pytest.raises(
        ContabilidadError,
        match="alquiler",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias,
            **datos,
        )

    assert _datos_edicion_apunte(apunte) == datos_originales

    assert movimiento.apunte is apunte
    assert movimiento.contrato is contrato_original
    assert movimiento.inmueble is apunte.inmueble
    assert movimiento.naturaleza == "INGRESO"
    assert movimiento.importe_esperado == 80000
    assert movimiento.estado == "PENDIENTE"


def test_modificar_apunte_alquiler_rechaza_cambio_inmueble(
    session,
    apunte_alquiler_sin_factura,
) -> None:
    """El alquiler no puede trasladarse a otro inmueble."""

    apunte, movimiento, categorias = (
        apunte_alquiler_sin_factura
    )

    inmueble_original = apunte.inmueble
    contrato_original = movimiento.contrato

    otro_inmueble = _crear_inmueble_prueba(
        referencia="OTRO-LOCAL",
        tipo="L",
        codigo_facturacion="OL",
        descripcion="Otro local",
        direccion="Otra dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    session.add(otro_inmueble)
    session.commit()

    datos = _datos_edicion_apunte(apunte)
    datos["inmueble"] = otro_inmueble

    # El usuario intenta asignar el alquiler
    # a un inmueble diferente del contratado.
    with pytest.raises(
        ContabilidadError,
        match="alquiler",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias,
            **datos,
        )

    assert apunte.inmueble is inmueble_original
    assert movimiento.inmueble is inmueble_original
    assert movimiento.contrato is contrato_original
    assert contrato_original.inmueble is inmueble_original


def test_modificar_apunte_alquiler_rechaza_fecha_fuera_contrato(
    session,
    apunte_alquiler_sin_factura,
) -> None:
    """La fecha del alquiler debe ser compatible con su contrato."""

    apunte, movimiento, categorias = (
        apunte_alquiler_sin_factura
    )

    contrato_original = movimiento.contrato

    datos = _datos_edicion_apunte(apunte)

    # El usuario intenta asignar al alquiler una fecha
    # anterior al comienzo del contrato.
    datos["fecha"] = date(2025, 12, 1)

    with pytest.raises(
        ContabilidadError,
        match="contrato",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias,
            **datos,
        )

    assert apunte.fecha == date(2026, 10, 1)
    assert movimiento.contrato is contrato_original
    assert movimiento.fecha_prevista_desde == date(2026, 10, 1)
    assert movimiento.fecha_prevista_hasta == date(2026, 10, 31)


def test_modificar_apunte_alquiler_permite_correcciones(
    session,
    apunte_alquiler_sin_factura,
) -> None:
    """Permite corregir un alquiler sin alterar su identidad."""

    apunte, movimiento, categorias = (
        apunte_alquiler_sin_factura
    )

    contrato_original = movimiento.contrato
    movimiento_id = movimiento.id

    datos = _datos_edicion_apunte(apunte)

    datos.update({
        "fecha": date(2026, 10, 3),
        "base": 85000,
        "concepto": "Alquiler de octubre corregido",
        "notas": "Corrección del importe",
    })

    # El usuario corrige el importe y la descripción
    # de un alquiler cuyo cobro sigue pendiente.
    modificar_apunte_contable(
        session,
        apunte=apunte,
        categorias=categorias,
        **datos,
    )

    session.commit()

    assert _datos_edicion_apunte(apunte) == datos

    assert apunte.total == 85000

    assert movimiento.id == movimiento_id
    assert movimiento.apunte is apunte
    assert movimiento.contrato is contrato_original

    assert movimiento.importe_esperado == 85000
    assert movimiento.concepto == apunte.concepto
    assert movimiento.estado == "PENDIENTE"

    assert movimiento.fecha_prevista_desde == date(2026, 10, 1)
    assert movimiento.fecha_prevista_hasta == date(2026, 10, 31)

    # Facturación sigue reconociendo el alquiler
    # de octubre como ya contabilizado.
    with pytest.raises(
        FacturacionError,
        match="ya está contabilizado",
    ):
        contabilizar_ingreso_sin_factura(
            contrato=contrato_original,
            periodo=date(2026, 10, 1),
            fecha=date(2026, 10, 3),
            categorias=categorias,
        )


def test_reclasificar_apunte_como_alquiler_vincula_contrato(
    session,
    contrato,
    ingreso_para_reclasificar,
) -> None:
    """Al reclasificar un ingreso se identifica su contrato."""

    apunte, movimiento, categorias = (
        ingreso_para_reclasificar
    )

    movimiento_id = movimiento.id

    datos = _datos_edicion_apunte(apunte)

    datos.update({
        "categoria": "ING_ALQUILERES",
        "concepto": "Alquiler de octubre",
    })

    # El usuario descubre que el ingreso registrado
    # corresponde realmente al alquiler del inmueble.
    modificar_apunte_contable(
        session,
        apunte=apunte,
        categorias=categorias,
        **datos,
    )

    session.commit()

    assert apunte.categoria == "ING_ALQUILERES"
    assert movimiento.contrato is contrato
    assert movimiento.apunte is apunte
    assert movimiento.inmueble is contrato.inmueble
    assert movimiento.id == movimiento_id
    assert movimiento.concepto == apunte.concepto
    assert movimiento.importe_esperado == 80000
    assert movimiento.estado == "PENDIENTE"

    # No debe haberse creado otro movimiento previsto.
    assert len(apunte.movimientos_previstos) == 1

    # Facturación reconoce el alquiler como contabilizado.
    with pytest.raises(
        FacturacionError,
        match="ya está contabilizado",
    ):
        contabilizar_ingreso_sin_factura(
            contrato=contrato,
            periodo=date(2026, 10, 1),
            fecha=date(2026, 10, 1),
            categorias=categorias,
        )


def test_reclasificar_apunte_como_alquiler_sin_contrato_vigente(
    session,
    contrato,
    ingreso_para_reclasificar,
) -> None:
    """No puede vincularse un alquiler a un contrato no vigente."""

    apunte, movimiento, categorias = (
        ingreso_para_reclasificar
    )

    contrato.fecha_fin = date(2026, 9, 30)
    session.commit()

    datos_originales = _datos_edicion_apunte(apunte)
    datos = datos_originales.copy()
    datos["categoria"] = "ING_ALQUILERES"

    # El usuario intenta reclasificar un ingreso de octubre,
    # pero el contrato terminó en septiembre.
    with pytest.raises(
        ContabilidadError,
        match="contrato",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias,
            **datos,
        )

    assert _datos_edicion_apunte(apunte) == datos_originales

    assert movimiento.contrato is None
    assert movimiento.apunte is apunte
    assert movimiento.importe_esperado == 80000
    assert movimiento.estado == "PENDIENTE"


def test_reclasificar_apunte_como_alquiler_con_varios_contratos(
    session,
    contrato,
    ingreso_para_reclasificar,
) -> None:
    """La identificación del contrato no puede ser ambigua."""

    apunte, movimiento, categorias = (
        ingreso_para_reclasificar
    )

    otro_contrato = _contrato_para_imputacion(
        contrato.inmueble,
        fecha_inicio=date(2026, 9, 1),
        fecha_fin=None,
    )

    otro_contrato.genera_factura = False

    session.add(otro_contrato)
    session.commit()

    datos_originales = _datos_edicion_apunte(apunte)
    datos = datos_originales.copy()
    datos["categoria"] = "ING_ALQUILERES"

    # Existen dos contratos vigentes para el inmueble.
    # Contab no debe elegir arbitrariamente uno de ellos.
    with pytest.raises(
        ContabilidadError,
        match="varios contratos",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias,
            **datos,
        )

    assert _datos_edicion_apunte(apunte) == datos_originales
    assert movimiento.contrato is None
    assert movimiento.estado == "PENDIENTE"


@pytest.mark.parametrize(
    "estado",
    [
        "CONCILIADO",
        "PARCIAL",
    ],
)
def test_reclasificar_apunte_como_alquiler_conciliado_se_rechaza(
    session,
    ingreso_para_reclasificar,
    estado,
) -> None:
    """No se cambia la vinculación de un cobro ya conciliado."""

    apunte, movimiento, categorias = (
        ingreso_para_reclasificar
    )

    movimiento.estado = estado
    session.commit()

    datos_originales = _datos_edicion_apunte(apunte)
    datos = datos_originales.copy()
    datos["categoria"] = "ING_ALQUILERES"

    # El usuario intenta atribuir a un contrato un ingreso
    # cuya conciliación ya está total o parcialmente realizada.
    with pytest.raises(
        ContabilidadError,
        match="conciliado",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias,
            **datos,
        )

    assert _datos_edicion_apunte(apunte) == datos_originales

    assert movimiento.contrato is None
    assert movimiento.estado == estado
    assert movimiento.importe_esperado == 80000


def test_reclasificar_apunte_como_alquiler_ya_contabilizado(
    session,
    ingreso_para_reclasificar,
    apunte_alquiler_sin_factura,
) -> None:
    """La reclasificación no puede duplicar un alquiler mensual."""

    apunte, movimiento, categorias = (
        ingreso_para_reclasificar
    )

    alquiler, cobro, _ = apunte_alquiler_sin_factura

    assert apunte.id != alquiler.id
    assert apunte.inmueble is alquiler.inmueble

    assert apunte.periodo_desde == alquiler.periodo_desde
    assert apunte.periodo_hasta == alquiler.periodo_hasta

    datos_originales = _datos_edicion_apunte(apunte)
    datos = datos_originales.copy()
    datos["categoria"] = "ING_ALQUILERES"

    # El usuario intenta reclasificar otro ingreso
    # como el alquiler de un mes ya contabilizado.
    with pytest.raises(
        ContabilidadError,
        match="ya está contabilizado",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias,
            **datos,
        )

    assert _datos_edicion_apunte(apunte) == datos_originales

    assert movimiento.contrato is None
    assert movimiento.estado == "PENDIENTE"

    # El alquiler original tampoco debe modificarse.
    assert alquiler.categoria == "ING_ALQUILERES"
    assert alquiler.total == 80000
    assert cobro.apunte is alquiler
    assert cobro.contrato is not None
    assert cobro.importe_esperado == 80000


def test_reclasificar_apunte_como_alquiler_sin_movimiento(
    session,
    ingreso_para_reclasificar,
) -> None:
    """La reclasificación no genera movimientos no solicitados."""

    apunte, movimiento, categorias = (
        ingreso_para_reclasificar
    )

    # Simular un apunte registrado sin movimiento previsto.
    apunte.movimientos_previstos.remove(movimiento)
    session.delete(movimiento)
    session.commit()

    assert not apunte.movimientos_previstos

    datos = _datos_edicion_apunte(apunte)
    datos["categoria"] = "ING_ALQUILERES"

    # El usuario corrige únicamente la clasificación contable.
    modificar_apunte_contable(
        session,
        apunte=apunte,
        categorias=categorias,
        **datos,
    )

    session.commit()

    assert apunte.categoria == "ING_ALQUILERES"
    assert apunte.total == 80000
    assert not apunte.movimientos_previstos


@pytest.fixture(params=[False, True], ids=["directa", "distribucion"])
def apunte_gasto_imputado(session, request):
    """Prepara un gasto con imputación directa o distribuida."""

    categorias = _categorias_gastos_comunes()

    categorias["ING_OTROS"] = CategoriaContable(
        codigo="ING_OTROS",
        naturaleza="INGRESO",
        nombre="Otros ingresos",
        activa=True,
        subcategorias=(),
    )

    categorias["GAS_REPARACIONES"] = CategoriaContable(
        codigo="GAS_REPARACIONES",
        naturaleza="GASTO",
        nombre="Reparaciones",
        activa=True,
        subcategorias=(),
    )

    if request.param:
        inmueble, local, _ = (
            _inmueble_subdividido_para_distribuir()
        )
    else:
        inmueble = _crear_inmueble_prueba(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="L1",
            descripcion="Local",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        local = inmueble

    contrato = _contrato_para_imputacion(
        local,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=None,
    )

    # El usuario contabiliza un gasto repercutible.
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Gasto de octubre",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    # Se persiste la imputación al contrato, directamente
    # o a través de una distribución del apunte.
    if request.param:
        distribucion = next(
            distribucion
            for distribucion in apunte.distribuciones
            if distribucion.inmueble is local
        )

        imputacion = ImputacionContrato(
            distribucion_apunte=distribucion,
            contrato=contrato,
            base=distribucion.base,
            iva_importe=distribucion.iva_importe,
            retencion_importe=distribucion.retencion_importe,
            importe=distribucion.total,
        )
    else:
        imputacion = ImputacionContrato(
            apunte=apunte,
            contrato=contrato,
            base=apunte.base,
            iva_importe=apunte.iva_importe,
            retencion_importe=apunte.retencion_importe,
            importe=apunte.total,
        )

    session.add_all([
        inmueble,
        contrato,
        apunte,
        imputacion,
    ])
    session.commit()

    return apunte, imputacion, categorias


def test_modificar_apunte_imputado_rechaza_cambio_naturaleza(
    session,
    apunte_gasto_imputado,
) -> None:
    """Un gasto ya imputado no puede convertirse en ingreso."""

    apunte, imputacion, categorias = apunte_gasto_imputado

    datos_originales = _datos_edicion_apunte(apunte)
    importe_imputado = imputacion.importe

    datos = datos_originales.copy()

    datos.update({
        "naturaleza": "INGRESO",
        "categoria": "ING_OTROS",
    })

    # El usuario intenta convertir en ingreso
    # un gasto que ya ha sido imputado a un contrato.
    with pytest.raises(
        ContabilidadError,
        match="tratamiento",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias,
            **datos,
        )

    # Ni el apunte ni la imputación deben modificarse.
    assert _datos_edicion_apunte(apunte) == datos_originales

    assert apunte.naturaleza == "GASTO"
    assert apunte.categoria == "GAS_COMUNIDAD"
    assert imputacion.importe == importe_imputado


def test_modificar_apunte_imputado_permite_cambio_categoria(
    session,
    apunte_gasto_imputado,
) -> None:
    """Permite reclasificar un gasto sin alterar su imputación."""

    apunte, imputacion, categorias = apunte_gasto_imputado

    imputacion_id = imputacion.id
    contrato_id = imputacion.contrato_id

    importes_originales = (
        imputacion.base,
        imputacion.iva_importe,
        imputacion.retencion_importe,
        imputacion.importe,
    )

    origen_original = (
        imputacion.apunte_id,
        imputacion.distribucion_apunte_id,
    )

    datos = _datos_edicion_apunte(apunte)

    datos["categoria"] = "GAS_REPARACIONES"

    # El usuario descubre que el gasto estaba clasificado
    # incorrectamente como gasto de comunidad.
    modificar_apunte_contable(
        session,
        apunte=apunte,
        categorias=categorias,
        **datos,
    )

    session.commit()

    assert _datos_edicion_apunte(apunte) == datos

    assert apunte.naturaleza == "GASTO"
    assert apunte.categoria == "GAS_REPARACIONES"

    # La imputación conserva su identidad, contrato,
    # origen e importes originales.
    assert imputacion.id == imputacion_id
    assert imputacion.contrato_id == contrato_id

    assert (
        imputacion.base,
        imputacion.iva_importe,
        imputacion.retencion_importe,
        imputacion.importe,
    ) == importes_originales

    assert (
        imputacion.apunte_id,
        imputacion.distribucion_apunte_id,
    ) == origen_original


@pytest.mark.parametrize(
    "naturaleza, importe_negativo, tratamiento, permitido",
    CASOS_NATURALEZA_SIGNO_TRATAMIENTO,
)
def test_crear_apunte_compatibilidad_tratamiento(
    inmueble,
    categorias_ingreso_gasto,
    naturaleza,
    importe_negativo,
    tratamiento,
    permitido,
) -> None:
    """Comprueba las combinaciones admitidas al crear un apunte."""

    categoria = (
        "GAS_COMUNIDAD"
        if naturaleza == "GASTO"
        else "ING_OTROS"
    )

    datos = {
        "inmueble": inmueble,
        "categorias": categorias_ingreso_gasto,
        "fecha": date(2026, 10, 1),
        "naturaleza": naturaleza,
        "categoria": categoria,
        "concepto": "Apunte de prueba",
        "base": 10000,
        "importe_negativo": importe_negativo,
        "tratamiento": tratamiento,
    }

    if permitido:
        apunte = crear_apunte_contable(**datos)

        assert apunte.naturaleza == naturaleza
        assert apunte.categoria == categoria
        assert apunte.importe_negativo is importe_negativo
        assert apunte.tratamiento == tratamiento
        assert apunte.base == 10000
        assert apunte.total == 10000
    else:
        with pytest.raises(
            ContabilidadError,
            match="tratamiento",
        ):
            crear_apunte_contable(**datos)


@pytest.mark.parametrize(
    "naturaleza, importe_negativo, tratamiento, permitido",
    CASOS_NATURALEZA_SIGNO_TRATAMIENTO,
)
def test_modificar_apunte_compatibilidad_tratamiento(
    session,
    inmueble,
    categorias_ingreso_gasto,
    naturaleza,
    importe_negativo,
    tratamiento,
    permitido,
) -> None:
    """La edición debe respetar las mismas reglas que la creación."""

    # El usuario registra inicialmente un gasto ordinario válido,
    # sin movimientos previstos ni imputaciones.
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias_ingreso_gasto,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Apunte de prueba",
        base=10000,
        tratamiento="CONTABILIZAR",
    )

    session.add(apunte)
    session.commit()

    datos_originales = _datos_edicion_apunte(apunte)

    categoria = (
        "GAS_COMUNIDAD"
        if naturaleza == "GASTO"
        else "ING_OTROS"
    )

    datos = datos_originales.copy()

    datos.update({
        "naturaleza": naturaleza,
        "categoria": categoria,
        "importe_negativo": importe_negativo,
        "tratamiento": tratamiento,
    })

    # El usuario intenta modificar la naturaleza,
    # el signo y el tratamiento del apunte.
    if permitido:
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias_ingreso_gasto,
            **datos,
        )

        session.commit()

        assert _datos_edicion_apunte(apunte) == datos

    else:
        with pytest.raises(
            ContabilidadError,
            match="tratamiento",
        ):
            modificar_apunte_contable(
                session,
                apunte=apunte,
                categorias=categorias_ingreso_gasto,
                **datos,
            )

        # El rechazo no debe modificar el apunte original.
        assert _datos_edicion_apunte(apunte) == datos_originales

        session.refresh(apunte)

        assert _datos_edicion_apunte(apunte) == datos_originales


@pytest.mark.parametrize(
    "categoria, subcategoria",
    [
        ("GAS_ANTIGUA", ""),
        ("GAS_TRIBUTOS", "ANTIGUA"),
    ],
)
def test_crear_apunte_rechaza_clasificacion_inactiva(
    inmueble,
    categorias_con_inactivas,
    categoria,
    subcategoria,
) -> None:
    """No pueden utilizarse clasificaciones inactivas en nuevos apuntes."""

    # El usuario intenta contabilizar un nuevo gasto
    # con una clasificación que ya no está activa.
    with pytest.raises(
        ContabilidadError,
        match="inactiva",
    ):
        crear_apunte_contable(
            inmueble=inmueble,
            categorias=categorias_con_inactivas,
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria=categoria,
            subcategoria=subcategoria,
            concepto="Gasto de prueba",
            base=10000,
        )


@pytest.mark.parametrize(
    "categoria, subcategoria",
    [
        ("GAS_ANTIGUA", ""),
        ("GAS_TRIBUTOS", "ANTIGUA"),
    ],
)
def test_modificar_apunte_conserva_clasificacion_inactiva(
    session,
    inmueble,
    categorias_con_inactivas,
    categoria,
    subcategoria,
) -> None:
    """Puede corregirse un apunte con una clasificación histórica."""

    # El apunte se registró cuando su clasificación
    # todavía estaba activa.
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria=categoria,
        subcategoria=subcategoria or None,
        concepto="Concepto original",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
        tratamiento="CONTABILIZAR",
    )

    session.add(apunte)
    session.commit()

    datos = _datos_edicion_apunte(apunte)

    # El usuario corrige el concepto sin cambiar
    # la clasificación histórica del apunte.
    datos["concepto"] = "Concepto corregido"

    modificar_apunte_contable(
        session,
        apunte=apunte,
        categorias=categorias_con_inactivas,
        **datos,
    )

    session.commit()
    session.refresh(apunte)

    assert apunte.concepto == "Concepto corregido"
    assert apunte.categoria == categoria
    assert apunte.subcategoria == (subcategoria or None)
    assert apunte.total == 10000


@pytest.mark.parametrize(
    "categoria, subcategoria",
    [
        ("GAS_ANTIGUA", ""),
        ("GAS_TRIBUTOS", "ANTIGUA"),
    ],
)
def test_modificar_apunte_rechaza_clasificacion_inactiva(
    session,
    inmueble,
    categorias_con_inactivas,
    categoria,
    subcategoria,
) -> None:
    """No puede asignarse una clasificación inactiva al editar."""

    # El usuario registra inicialmente un gasto
    # con una categoría activa.
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias_con_inactivas,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
    )

    session.add(apunte)
    session.commit()

    datos_originales = _datos_edicion_apunte(apunte)
    datos = datos_originales.copy()

    # El usuario intenta asignar una clasificación inactiva.
    datos.update({
        "categoria": categoria,
        "subcategoria": subcategoria,
    })

    with pytest.raises(
        ContabilidadError,
        match="inactiva",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias_con_inactivas,
            **datos,
        )

    assert _datos_edicion_apunte(apunte) == datos_originales


def test_crear_apunte_rechaza_inmueble_inactivo(
    session,
    inmueble,
) -> None:
    """No pueden registrarse nuevos apuntes en inmuebles inactivos."""

    # El propietario desactiva el inmueble.
    inmueble.activo = False
    session.commit()

    # El usuario intenta registrar un nuevo gasto.
    with pytest.raises(
        ContabilidadError,
        match="inactivo",
    ):
        crear_apunte_contable(
            inmueble=inmueble,
            categorias=_categorias_gastos_comunes(),
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Cuota de comunidad",
            base=10000,
        )


def test_modificar_apunte_conserva_inmueble_inactivo(
    session,
    inmueble,
) -> None:
    """Puede corregirse un apunte de un inmueble histórico."""

    categorias = _categorias_gastos_comunes()

    # El usuario contabiliza un gasto mientras
    # el inmueble permanece activo.
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Concepto original",
        base=10000,
    )

    session.add(apunte)
    session.commit()

    # Posteriormente se desactiva el inmueble.
    inmueble.activo = False
    session.commit()

    # El usuario corrige el concepto del apunte histórico.
    datos = _datos_edicion_apunte(apunte)
    datos["concepto"] = "Concepto corregido"

    modificar_apunte_contable(
        session,
        apunte=apunte,
        categorias=categorias,
        **datos,
    )

    session.commit()
    session.refresh(apunte)

    assert apunte.concepto == "Concepto corregido"
    assert apunte.inmueble is inmueble
    assert apunte.inmueble.activo is False
    assert apunte.total == 10000


def test_modificar_apunte_rechaza_otro_inmueble_inactivo(
    session,
    inmueble,
) -> None:
    """No puede asignarse otro inmueble inactivo al editar."""

    categorias = _categorias_gastos_comunes()

    # El usuario contabiliza un gasto en un inmueble activo.
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
    )

    session.add(apunte)
    session.commit()

    # Existe otro inmueble que ha dejado de estar activo.
    otro_inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-INACTIVO",
        tipo="L",
        codigo_facturacion="Z9",
        descripcion="Local inactivo",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    otro_inmueble.activo = False

    session.add(otro_inmueble)
    session.commit()

    datos_originales = _datos_edicion_apunte(apunte)
    datos = datos_originales.copy()

    # El usuario intenta asignar el gasto al inmueble inactivo.
    datos["inmueble"] = otro_inmueble

    with pytest.raises(
        ContabilidadError,
        match="inactivo",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            categorias=categorias,
            **datos,
        )

    assert _datos_edicion_apunte(apunte) == datos_originales

    session.refresh(apunte)

    assert apunte.inmueble is inmueble


@pytest.mark.parametrize(
    "categoria, subcategoria",
    [
        ("GAS_ANTIGUA", ""),
        ("GAS_TRIBUTOS", "ANTIGUA"),
    ],
)
def test_modificar_apunte_sustituye_clasificacion_inactiva(
    session,
    inmueble,
    categorias_con_inactivas,
    categoria,
    subcategoria,
) -> None:
    """Puede sustituirse una clasificación histórica por una activa."""

    # Existe un apunte con una clasificación que
    # posteriormente ha dejado de estar activa.
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria=categoria,
        subcategoria=subcategoria or None,
        concepto="Gasto histórico",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
        tratamiento="CONTABILIZAR",
    )

    session.add(apunte)
    session.commit()

    datos = _datos_edicion_apunte(apunte)

    # El usuario corrige la clasificación seleccionando
    # una categoría actualmente activa.
    datos.update({
        "categoria": "GAS_COMUNIDAD",
        "subcategoria": "",
    })

    modificar_apunte_contable(
        session,
        apunte=apunte,
        categorias=categorias_con_inactivas,
        **datos,
    )

    session.commit()
    session.refresh(apunte)

    assert apunte.categoria == "GAS_COMUNIDAD"
    assert apunte.subcategoria is None
    assert apunte.total == 10000


def test_modificar_apunte_sustituye_inmueble_inactivo(
    session,
    inmueble,
) -> None:
    """Puede sustituirse un inmueble histórico por uno activo."""

    categorias = _categorias_gastos_comunes()

    # El usuario registra un gasto en un inmueble activo.
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=10000,
    )

    session.add(apunte)
    session.commit()

    # Posteriormente se desactiva el inmueble original.
    inmueble.activo = False

    otro_inmueble = _crear_inmueble_prueba(
        referencia="LOCAL-ACTIVO",
        tipo="L",
        codigo_facturacion="Z9",
        descripcion="Local activo",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    otro_inmueble.activo = True

    session.add(otro_inmueble)
    session.commit()

    datos = _datos_edicion_apunte(apunte)

    # El usuario corrige la asignación del gasto,
    # seleccionando un inmueble activo.
    datos["inmueble"] = otro_inmueble

    modificar_apunte_contable(
        session,
        apunte=apunte,
        categorias=categorias,
        **datos,
    )

    session.commit()
    session.refresh(apunte)

    assert apunte.inmueble is otro_inmueble
    assert apunte.inmueble.activo is True
    assert apunte.total == 10000


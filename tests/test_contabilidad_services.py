"""Pruebas de la lógica de negocio contable."""

import pytest

from datetime import date
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

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
    proponer_nombre_documento,
)
from contab.models import (
    ApunteContable,
    Contrato,
    DistribucionApunte,
    ImputacionContrato,
    Inmueble,
    MovimientoPrevisto,
)



def _inmueble_subdividido_para_distribuir():
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
        criterio_periodo="EXCLUIR_HASTA",
        tratamiento=" repercutir ",
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
    assert apunte.criterio_periodo == "EXCLUIR_HASTA"
    assert apunte.tratamiento == "REPERCUTIR"
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
        criterio_periodo="INCLUIR_AMBOS",
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
    assert apunte.criterio_periodo == "INCLUIR_AMBOS"
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
        criterio_periodo="EXCLUIR_DESDE",
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
    assert apunte.criterio_periodo == "EXCLUIR_DESDE"
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
    "criterio_periodo",
    [
        "EXCLUIR_HASTA",
        "INCLUIR_AMBOS",
    ],
)
def test_apunte_contable_admite_criterios_periodo(
    session,
    inmueble,
    criterio_periodo: str,
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
        criterio_periodo=criterio_periodo,
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

    assert apunte.criterio_periodo == criterio_periodo



@pytest.mark.parametrize(
    "criterio_periodo",
    [
        "EXCLUIR_DESDE",
        "EXCLUIR_AMBOS",
    ],
)
def test_crear_apunte_rechaza_criterios_periodo_obsoletos(
    inmueble,
    criterio_periodo,
) -> None:
    """No permite registrar nuevos apuntes con criterios obsoletos."""

    categorias = _categorias_gastos_comunes()

    with pytest.raises(
        ContabilidadError,
        match="criterio del período no es válido",
    ):
        crear_apunte_contable(
            inmueble=inmueble,
            categorias=categorias,
            fecha=date(2026, 10, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Cuota de comunidad",
            base=10000,
            periodo_desde=date(2026, 9, 3),
            periodo_hasta=date(2026, 10, 6),
            criterio_periodo=criterio_periodo,
            tratamiento="REPERCUTIR",
        )



@pytest.mark.parametrize(
    "criterio_periodo",
    [
        "EXCLUIR_DESDE",
        "EXCLUIR_AMBOS",
    ],
)
def test_modificar_apunte_rechaza_criterios_periodo_obsoletos(
    session,
    inmueble,
    criterio_periodo,
) -> None:
    """Rechaza el criterio inválido sin alterar el apunte original."""

    categorias = _categorias_gastos_comunes()

    # El usuario tiene un apunte con un criterio válido.
    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad septiembre",
        base=10000,
        periodo_desde=date(2026, 9, 3),
        periodo_hasta=date(2026, 10, 6),
        criterio_periodo="INCLUIR_AMBOS",
        tratamiento="REPERCUTIR",
    )

    session.add(apunte)
    session.commit()

    # El usuario intenta introducir un criterio obsoleto.
    with pytest.raises(
        ContabilidadError,
        match="criterio del período no es válido",
    ):
        modificar_apunte_contable(
            session,
            apunte=apunte,
            inmueble=inmueble,
            categorias=categorias,
            fecha=date(2026, 10, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad modificada",
            base=12000,
            periodo_desde=date(2026, 9, 3),
            periodo_hasta=date(2026, 10, 6),
            criterio_periodo=criterio_periodo,
            tratamiento="REPERCUTIR",
        )

    # El intento rechazado no modifica ningún dato.
    assert apunte.concepto == "Comunidad septiembre"
    assert apunte.base == 10000
    assert apunte.criterio_periodo == "INCLUIR_AMBOS"


@pytest.mark.parametrize(
    (
        "periodo_desde",
        "periodo_hasta",
        "criterio_periodo",
    ),
    [
        (
            None,
            None,
            "INCLUIR_AMBOS",
        ),
        (
            date(2026, 3, 17),
            date(2026, 5, 14),
            None,
        ),
        (
            date(2026, 3, 17),
            date(2026, 5, 14),
            "DESCONOCIDO",
        ),
    ],
)
def test_apunte_contable_rechaza_criterio_periodo_invalido(
    session,
    inmueble,
    periodo_desde,
    periodo_hasta,
    criterio_periodo,
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
        criterio_periodo=criterio_periodo,
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
    "criterio_periodo",
    [
        "EXCLUIR_HASTA",
        "INCLUIR_AMBOS",
    ],
)
def test_crear_apunte_admite_criterios_periodo(
    inmueble,
    criterio_periodo: str,
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
        criterio_periodo=criterio_periodo,
        base=10000,
    )

    assert apunte.criterio_periodo == criterio_periodo


@pytest.mark.parametrize(
    (
        "periodo_desde",
        "periodo_hasta",
        "criterio_periodo",
    ),
    [
        (
            None,
            None,
            "INCLUIR_AMBOS",
        ),
        (
            date(2026, 7, 1),
            date(2026, 7, 31),
            None,
        ),
        (
            date(2026, 7, 1),
            date(2026, 7, 31),
            "DESCONOCIDO",
        ),
    ],
)
def test_crear_apunte_rechaza_criterio_periodo_invalido(
    inmueble,
    periodo_desde: date | None,
    periodo_hasta: date | None,
    criterio_periodo: str | None,
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
        match="criterio",
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
            criterio_periodo=criterio_periodo,
            base=10000,
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
    inmueble = Inmueble(
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
        criterio_periodo=None,
    )

    assert reparto == [
        (contrato, 10000),
    ]
    assert propietario == 0


def test_reparto_contratos_sin_periodo_sin_contrato_es_propietario() -> None:
    inmueble = Inmueble(
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
        criterio_periodo=None,
    )

    assert reparto == []
    assert propietario == 10000


def test_reparto_contratos_prorratea_periodo_entre_dos_contratos() -> None:
    inmueble = Inmueble(
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
        criterio_periodo="INCLUIR_AMBOS",
    )

    assert reparto == [
        (contrato_1, 4000),
        (contrato_2, 6001),
    ]
    assert propietario == 0


def test_reparto_contratos_deja_dias_sin_contrato_al_propietario() -> None:
    inmueble = Inmueble(
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
        criterio_periodo="INCLUIR_AMBOS",
    )

    assert reparto == [
        (contrato, 5000),
    ]
    assert propietario == 5000


@pytest.mark.parametrize(
    (
        "criterio",
        "esperado",
    ),
    [
        (
            "INCLUIR_AMBOS",
            [
                ("contrato_1", 900),
                ("contrato_2", 8100),
            ],
        ),
        (
            "EXCLUIR_DESDE",
            [
                ("contrato_2", 9000),
            ],
        ),
        (
            "EXCLUIR_HASTA",
            [
                ("contrato_1", 1000),
                ("contrato_2", 8000),
            ],
        ),
        (
            "EXCLUIR_AMBOS",
            [
                ("contrato_2", 9000),
            ],
        ),
    ],
)
def test_reparto_contratos_respeta_criterio_periodo(
    criterio: str,
    esperado,
) -> None:
    inmueble = Inmueble(
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
        criterio_periodo=criterio,
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
    inmueble = Inmueble(
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
            criterio_periodo="EXCLUIR_AMBOS",
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
    inmueble = Inmueble(
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
    inmueble = Inmueble(
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
        criterio_periodo="INCLUIR_AMBOS",
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
    inmueble = Inmueble(
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
    inmueble = Inmueble(
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
    inmueble = Inmueble(
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
        criterio_periodo="INCLUIR_AMBOS",
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
    inmueble = Inmueble(
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
            criterio_periodo="EXCLUIR_HASTA",
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
    inmueble = Inmueble(
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
            criterio_periodo=None,
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
    inmueble = Inmueble(
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
            "criterio_periodo": "INCLUIR_AMBOS",
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
    inmueble = Inmueble(
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

    datos = {
        "fecha": apunte.fecha,
        "base": apunte.base,
        "iva_importe": apunte.iva_importe,
        "retencion_importe": apunte.retencion_importe,
        "periodo_desde": apunte.periodo_desde,
        "periodo_hasta": apunte.periodo_hasta,
        "criterio_periodo": apunte.criterio_periodo,
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
            criterio_periodo=datos["criterio_periodo"],
            tratamiento=datos["tratamiento"],
        )


def test_modificar_apunte_con_imputacion_persistida_permite_cambiar_notas(
    session,
) -> None:
    inmueble = Inmueble(
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
        criterio_periodo=apunte.criterio_periodo,
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
            criterio_periodo=apunte.criterio_periodo,
            tratamiento=apunte.tratamiento,
        )

    assert apunte.base == 10000


def test_eliminar_apunte_con_imputacion_persistida_se_rechaza(
    session,
) -> None:
    inmueble = Inmueble(
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
    assert apunte.criterio_periodo == "INCLUIR_AMBOS"

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
        criterio_periodo="INCLUIR_AMBOS",
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
        criterio_periodo="INCLUIR_AMBOS",
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



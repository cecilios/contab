"""Pruebas de la lógica de negocio contable."""

import pytest

from datetime import date
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from contab.config import (
    CategoriaContable,
    SubcategoriaContable,
)
from contab.contabilidad.services import (
    ContabilidadError,
    buscar_documentos_duplicados,
    crear_apunte_contable,
    eliminar_apunte_contable,
    modificar_apunte_contable,
    proponer_nombre_documento,
)
from contab.models import (
    ApunteContable,
    DistribucionApunte,
    Inmueble,
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
        "EXCLUIR_DESDE",
        "INCLUIR_AMBOS",
        "EXCLUIR_AMBOS",
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
        "EXCLUIR_DESDE",
        "INCLUIR_AMBOS",
        "EXCLUIR_AMBOS",
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



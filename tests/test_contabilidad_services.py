"""Pruebas de la lógica de negocio contable."""

import pytest

from datetime import date

from contab.config import (
    CategoriaContable,
    SubcategoriaContable,
)
from contab.contabilidad.services import (
    ContabilidadError,
    crear_apunte_contable,
    modificar_apunte_contable,
)
from contab.models import ApunteContable


def test_crear_apunte_contable(inmueble) -> None:
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
        inmueble=inmueble,
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
    )

    assert apunte.inmueble is inmueble
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


def test_modificar_apunte_contable(inmueble) -> None:
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
        concepto="Cuota provisional",
        base=10000,
    )

    resultado = modificar_apunte_contable(
        apunte=apunte,
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 8, 31),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota definitiva",
        base=12000,
        iva_importe=1000,
        notas="Corregido",
    )

    assert resultado is apunte
    assert apunte.fecha == date(2026, 8, 31)
    assert apunte.concepto == "Cuota definitiva"
    assert apunte.base == 12000
    assert apunte.iva_importe == 1000
    assert apunte.total == 13000
    assert apunte.notas == "Corregido"


def test_modificar_apunte_invalido_no_cambia_el_original(
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



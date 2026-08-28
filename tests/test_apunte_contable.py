"""Pruebas del modelo ORM ApunteContable."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from contab.models import ApunteContable


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

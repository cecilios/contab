#!/usr/bin/env python3
"""Carga datos contables ficticios en una base demo vacía."""

import argparse
from datetime import date

from sqlalchemy import inspect, select

from contab.config import cargar_bases_datos
from contab.database import (
    create_session_factory,
    create_sqlite_engine,
)
from contab.models import ApunteContable, Inmueble


def _ingreso(
    inmueble: Inmueble,
    *,
    mes: int,
    concepto: str,
    base: int,
    iva: int,
    retencion: int,
) -> ApunteContable:
    """Crea un ingreso contable ficticio."""
    return ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, mes, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto=concepto,
        base=base,
        iva_importe=iva,
        retencion_importe=retencion,
        total=base + iva - retencion,
        tratamiento="CONTABILIZAR",
        nombre_documento=f"{concepto}.pdf",
    )


def _gasto(
    inmueble: Inmueble,
    *,
    mes: int,
    concepto: str,
    base: int,
    categoria: str,
    subcategoria: str | None = None,
) -> ApunteContable:
    """Crea un gasto contable ficticio."""
    return ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, mes, 10),
        naturaleza="GASTO",
        categoria=categoria,
        subcategoria=subcategoria,
        concepto=concepto,
        base=base,
        iva_importe=0,
        retencion_importe=0,
        total=base,
        tratamiento="CONTABILIZAR",
        nombre_documento=f"{concepto}.pdf",
    )


def _crear_inmuebles() -> tuple[
    Inmueble,
    Inmueble,
    Inmueble,
    Inmueble,
]:
    """Crea inmuebles suficientes para probar los informes."""
    local = Inmueble(
        referencia="ALOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local comercial",
        direccion="Avenida Logroño, 36",
        poblacion="Madrid",
        provincia="Madrid",
    )

    piso = Inmueble(
        referencia="PISO-1",
        tipo="P",
        codigo_facturacion="P1",
        descripcion="Piso alquilado",
        direccion="Calle Mayor, 10",
        poblacion="Madrid",
        provincia="Madrid",
    )

    inactivo = Inmueble(
        referencia="LOCAL-INACTIVO",
        tipo="L",
        codigo_facturacion="LI",
        descripcion="Local con actividad histórica",
        direccion="Calle Antigua, 5",
        poblacion="Madrid",
        provincia="Madrid",
        activo=False,
    )

    sin_apuntes = Inmueble(
        referencia="LOCAL-SIN-APUNTES",
        tipo="L",
        codigo_facturacion="LS",
        descripcion="Local sin apuntes en 2026",
        direccion="Calle Nueva, 7",
        poblacion="Madrid",
        provincia="Madrid",
    )

    return (
        local,
        piso,
        inactivo,
        sin_apuntes,
    )


def _apuntes_local(
    inmueble: Inmueble,
) -> list[ApunteContable]:
    """Reproduce los movimientos de la hoja utilizada como modelo."""
    alquileres = (
        (1, "Alquiler Enero", 105995, 22259, 20139),
        (2, "Alquiler Febrero", 113839, 23906, 21629),
        (3, "Alquiler Marzo", 109917, 23083, 20884),
        (4, "Alquiler Abril", 109917, 23083, 20884),
        (5, "Alquiler Mayo", 109917, 23083, 20884),
        (6, "Alquiler Junio", 109917, 23083, 20884),
        (7, "Alquiler Julio", 109917, 23083, 20884),
        (8, "Alquiler Agosto", 109917, 23083, 20884),
        (9, "Alquiler Septiembre", 109917, 23083, 20884),
        (10, "Alquiler Octubre", 109917, 23083, 20884),
        (11, "Alquiler Noviembre", 109917, 23083, 20884),
        (12, "Alquiler Diciembre", 109917, 23083, 20884),
    )

    comunidades = (
        (1, "Comunidad Enero", 17643),
        (2, "Comunidad Febrero", 17643),
        (3, "Comunidad Marzo", 17643),
        (4, "Comunidad Abril y derrama", 17643),
        (5, "Comunidad Mayo", 17643),
        (6, "Comunidad Junio", 15436),
        (7, "Comunidad Julio", 17643),
        (8, "Comunidad Agosto", 17643),
        (9, "Comunidad Septiembre", 15436),
        (10, "Comunidad Octubre", 17643),
        (11, "Comunidad Noviembre", 17643),
        (12, "Comunidad Diciembre", 15436),
    )

    apuntes = [
        _ingreso(
            inmueble,
            mes=mes,
            concepto=concepto,
            base=base,
            iva=iva,
            retencion=retencion,
        )
        for (
            mes,
            concepto,
            base,
            iva,
            retencion,
        ) in alquileres
    ]

    apuntes.extend(
        _gasto(
            inmueble,
            mes=mes,
            concepto=concepto,
            base=base,
            categoria="GAS_COMUNIDAD",
        )
        for mes, concepto, base in comunidades
    )

    apuntes.extend(
        [
            _gasto(
                inmueble,
                mes=6,
                concepto="IBI primer plazo",
                base=50000,
                categoria="GAS_TRIBUTOS",
                subcategoria="IBI",
            ),
            _gasto(
                inmueble,
                mes=11,
                concepto="IBI segundo plazo",
                base=43119,
                categoria="GAS_TRIBUTOS",
                subcategoria="IBI",
            ),
            _gasto(
                inmueble,
                mes=6,
                concepto="Seguro póliza 50.878",
                base=10338,
                categoria="GAS_SEGUROS",
            ),
        ]
    )

    return apuntes


def _apuntes_adicionales(
    piso: Inmueble,
    inactivo: Inmueble,
) -> list[ApunteContable]:
    """Crea casos adicionales para las pruebas visuales."""
    apuntes = [
        _ingreso(
            piso,
            mes=mes,
            concepto=f"Alquiler piso {mes:02d}/2026",
            base=80000,
            iva=0,
            retencion=0,
        )
        for mes in range(1, 13)
    ]

    apuntes.append(
        _gasto(
            inactivo,
            mes=2,
            concepto="Seguro local inactivo",
            base=12500,
            categoria="GAS_SEGUROS",
        )
    )

    return apuntes


def main() -> None:
    """Carga los datos después de comprobar que la base está vacía."""
    parser = argparse.ArgumentParser(
        description=(
            "Carga datos ficticios para probar "
            "los informes de Contab."
        )
    )
    parser.add_argument(
        "database",
        help="Nombre de la base definida en contab.ini.",
    )
    args = parser.parse_args()

    databases = cargar_bases_datos()

    if args.database not in databases:
        disponibles = ", ".join(databases)

        raise SystemExit(
            f"Base desconocida: {args.database}. "
            f"Disponibles: {disponibles}."
        )

    engine = create_sqlite_engine(
        databases[args.database]
    )

    if not inspect(engine).has_table("inmueble"):
        raise SystemExit(
            "La base no está migrada. Ejecute primero: "
            f"contab-db upgrade --database {args.database}"
        )

    session_factory = create_session_factory(engine)

    with session_factory() as session:
        if session.scalar(
            select(Inmueble.id).limit(1)
        ) is not None:
            raise SystemExit(
                "La base contiene inmuebles. "
                "No se ha modificado ningún dato."
            )

        (
            local,
            piso,
            inactivo,
            sin_apuntes,
        ) = _crear_inmuebles()

        apuntes = _apuntes_local(local)
        apuntes.extend(
            _apuntes_adicionales(
                piso,
                inactivo,
            )
        )

        session.add_all(
            [
                local,
                piso,
                inactivo,
                sin_apuntes,
                *apuntes,
            ]
        )
        session.commit()

    print(
        f"Base demo cargada: {args.database}. "
        f"{len(apuntes)} apuntes creados."
    )


if __name__ == "__main__":
    main()

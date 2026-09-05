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
from contab.models import (
    ApunteContable,
    Contrato,
    ContratoInquilino,
    Inmueble,
    Inquilino,
    RentaContrato,
    RevisionRenta,
)


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


def _crear_inmuebles() -> dict[str, Inmueble]:
    """Crea los inmuebles necesarios para probar los informes."""
    ebotin_comun = Inmueble(
        referencia="EBOTIN-COMUN",
        tipo="T",
        codigo_facturacion="EBC",
        descripcion="Inmueble subdividido",
        direccion="Calle Ebotín, 1",
        poblacion="Madrid",
        provincia="Madrid",
    )

    inmuebles = {
        "alogro": Inmueble(
            referencia="ALOGRO",
            tipo="L",
            codigo_facturacion="AL",
            descripcion="Local comercial",
            direccion="Avenida Logroño, 36",
            poblacion="Madrid",
            provincia="Madrid",
        ),
        "ebotin_comun": ebotin_comun,
        "ebotin_a": Inmueble(
            referencia="EbotinA",
            tipo="L",
            codigo_facturacion="EBA",
            descripcion="Óptica",
            direccion="Calle Ebotín, 1",
            poblacion="Madrid",
            provincia="Madrid",
            inmueble_padre=ebotin_comun,
            participacion=5000,
        ),
        "ebotin_b": Inmueble(
            referencia="EbotinB",
            tipo="L",
            codigo_facturacion="EBB",
            descripcion="Peluquería",
            direccion="Calle Ebotín, 1",
            poblacion="Madrid",
            provincia="Madrid",
            inmueble_padre=ebotin_comun,
            participacion=5000,
        ),
        "piso": Inmueble(
            referencia="PISO-1",
            tipo="P",
            codigo_facturacion="P1",
            descripcion="Piso alquilado",
            direccion="Calle Mayor, 10",
            poblacion="Madrid",
            provincia="Madrid",
        ),
        "apartamento": Inmueble(
            referencia="Apart-1",
            tipo="P",
            codigo_facturacion="AP1",
            descripcion="Apartamento alquilado",
            direccion="Calle Mayor, 20",
            poblacion="Madrid",
            provincia="Madrid",
        ),
        "garaje": Inmueble(
            referencia="Garaje-1",
            tipo="G",
            codigo_facturacion="G1",
            descripcion="Plaza de garaje",
            direccion="Calle Mayor, 20",
            poblacion="Madrid",
            provincia="Madrid",
        ),
        "inactivo": Inmueble(
            referencia="LOCAL-INACTIVO",
            tipo="L",
            codigo_facturacion="LI",
            descripcion="Local con actividad histórica",
            direccion="Calle Antigua, 5",
            poblacion="Madrid",
            provincia="Madrid",
            activo=False,
        ),
        "sin_apuntes": Inmueble(
            referencia="LOCAL-SIN-APUNTES",
            tipo="L",
            codigo_facturacion="LS",
            descripcion="Local sin apuntes en 2026",
            direccion="Calle Nueva, 7",
            poblacion="Madrid",
            provincia="Madrid",
        ),
    }

    return inmuebles


def _crear_contrato_demo(
    *,
    inmueble: Inmueble,
    nombre_inquilino: str,
    nif: str,
    renta: int,
    genera_factura: bool,
    fecha_fin: date | None = None,
) -> tuple[Inquilino, Contrato]:
    """Crea un contrato completo para las pruebas visuales."""
    inquilino = Inquilino(
        nombre=nombre_inquilino,
        nif=nif,
    )

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2025, 1, 1),
        fecha_vencimiento=date(2030, 12, 31),
        fecha_fin=fecha_fin,
        genera_factura=genera_factura,
        fecha_inicio_facturacion=date(2025, 1, 1),
        fianza=renta,
        iva_porcentaje=2100 if genera_factura else 0,
        retencion_porcentaje=(
            1900 if genera_factura else 0
        ),
        direccion_facturacion=(
            inmueble.direccion
            if genera_factura
            else ""
        ),
        poblacion_facturacion=(
            inmueble.poblacion
            if genera_factura
            else ""
        ),
        provincia_facturacion=(
            inmueble.provincia
            if genera_factura
            else ""
        ),
        concepto_factura=(
            f"Alquiler de {inmueble.referencia}"
        ),
    )

    contrato.titulares.append(
        ContratoInquilino(
            inquilino=inquilino,
            orden=1,
        )
    )
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=date(2025, 1, 1),
            importe=renta,
        )
    )
    contrato.revisiones_renta.append(
        RevisionRenta(
            fecha_prevista=date(2027, 1, 1),
            metodo="IPC_NACIONAL",
            estado="PENDIENTE",
        )
    )

    return inquilino, contrato


def _crear_contratos_demo(
    inmuebles: dict[str, Inmueble],
) -> list[object]:
    """Crea contratos para todas las unidades arrendables."""
    datos = [
        (
            "alogro",
            "Ferretería Demo, S.L.",
            "B00000001",
            109917,
            True,
            None,
        ),
        (
            "ebotin_a",
            "Óptica Demo, S.L.",
            "B00000002",
            172386,
            True,
            None,
        ),
        (
            "ebotin_b",
            "Peluquería Demo, S.L.",
            "B00000003",
            124658,
            True,
            None,
        ),
        (
            "piso",
            "Inquilino Piso",
            "00000004D",
            21667,
            False,
            None,
        ),
        (
            "apartamento",
            "Inquilino Apartamento",
            "00000005M",
            80000,
            False,
            None,
        ),
        (
            "garaje",
            "Inquilino Garaje",
            "00000006Y",
            24000,
            False,
            None,
        ),
        (
            "inactivo",
            "Antiguo Inquilino, S.L.",
            "B00000007",
            100000,
            True,
            date(2026, 3, 31),
        ),
        (
            "sin_apuntes",
            "Nuevo Inquilino, S.L.",
            "B00000008",
            100000,
            True,
            None,
        ),
    ]

    registros: list[object] = []

    for (
        clave,
        nombre,
        nif,
        renta,
        genera_factura,
        fecha_fin,
    ) in datos:
        inquilino, contrato = _crear_contrato_demo(
            inmueble=inmuebles[clave],
            nombre_inquilino=nombre,
            nif=nif,
            renta=renta,
            genera_factura=genera_factura,
            fecha_fin=fecha_fin,
        )
        registros.extend([inquilino, contrato])

    return registros


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


def _repartir_en_tres(
    importe: int,
) -> tuple[int, int, int]:
    """Reparte un total entre tres meses sin perder céntimos."""
    cociente, resto = divmod(importe, 3)

    importes = [cociente, cociente, cociente]

    for posicion in range(resto):
        importes[posicion] += 1

    return tuple(importes)


def _apuntes_trimestrales(
    *,
    inmueble: Inmueble,
    concepto: str,
    totales: tuple[
        tuple[int, int, int, int],
        ...,
    ],
) -> list[ApunteContable]:
    """Crea apuntes mensuales conservando los totales trimestrales.

    Cada elemento de totales contiene, por este orden:

    - ingresos;
    - gastos;
    - IVA;
    - retención.
    """
    apuntes: list[ApunteContable] = []

    for trimestre, (
        ingresos,
        gastos,
        iva,
        retencion,
    ) in enumerate(totales, start=1):
        primer_mes = (trimestre - 1) * 3 + 1

        ingresos_mensuales = _repartir_en_tres(
            ingresos
        )
        iva_mensual = _repartir_en_tres(iva)
        retencion_mensual = _repartir_en_tres(
            retencion
        )

        for posicion in range(3):
            mes = primer_mes + posicion

            apuntes.append(
                _ingreso(
                    inmueble,
                    mes=mes,
                    concepto=(
                        f"{concepto} {mes:02d}/2026"
                    ),
                    base=ingresos_mensuales[posicion],
                    iva=iva_mensual[posicion],
                    retencion=(
                        retencion_mensual[posicion]
                    ),
                )
            )

        if gastos:
            apuntes.append(
                _gasto(
                    inmueble,
                    mes=primer_mes + 1,
                    concepto=(
                        f"Gastos {concepto} "
                        f"{trimestre}T"
                    ),
                    base=gastos,
                    categoria="GAS_COMUNIDAD",
                )
            )

    return apuntes


def _apuntes_resumen_anual(
    inmuebles: dict[str, Inmueble],
) -> list[ApunteContable]:
    """Crea los datos del modelo usado para el resumen anual."""
    apuntes: list[ApunteContable] = []

    apuntes.extend(
        _apuntes_trimestrales(
            inmueble=inmuebles["ebotin_a"],
            concepto="Alquiler EbotinA",
            totales=(
                (517158, 64010, 108603, 124119),
                (517158, 64010, 108603, 124119),
                (517158, 64010, 108603, 124119),
                (517158, 64010, 108603, 124119),
            ),
        )
    )

    apuntes.extend(
        _apuntes_trimestrales(
            inmueble=inmuebles["ebotin_b"],
            concepto="Alquiler EbotinB",
            totales=(
                (373975, 10338, 78535, 89754),
                (373975, 15667, 78535, 89754),
                (373975, 10338, 78535, 89754),
                (373975, 10338, 78535, 89754),
            ),
        )
    )

    apuntes.extend(
        _apuntes_trimestrales(
            inmueble=inmuebles["piso"],
            concepto="Alquiler Piso-1",
            totales=(
                (65000, 30721, 0, 0),
                (65000, 30721, 0, 0),
                (65000, 30721, 0, 0),
                (65000, 30721, 0, 0),
            ),
        )
    )

    apuntes.extend(
        _apuntes_trimestrales(
            inmueble=inmuebles["apartamento"],
            concepto="Alquiler Apart-1",
            totales=(
                (240000, 65106, 0, 0),
                (240000, 54027, 0, 0),
                (240000, 65106, 0, 0),
                (260000, 65106, 0, 0),
            ),
        )
    )

    apuntes.extend(
        _apuntes_trimestrales(
            inmueble=inmuebles["garaje"],
            concepto="Alquiler Garaje-1",
            totales=(
                (72000, 15000, 0, 0),
                (72000, 15000, 0, 0),
                (72000, 15000, 0, 0),
                (72000, 15000, 0, 0),
            ),
        )
    )

    apuntes.append(
        _gasto(
            inmuebles["inactivo"],
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

        inmuebles = _crear_inmuebles()

        contratos = _crear_contratos_demo(
            inmuebles
        )

        apuntes = _apuntes_local(
            inmuebles["alogro"]
        )
        apuntes.extend(
            _apuntes_resumen_anual(inmuebles)
        )

        session.add_all(
            [
                *inmuebles.values(),
                *contratos,
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

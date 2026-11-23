#!/usr/bin/env python3
"""Diagnostica alquileres históricos sin contrato, sin modificar la BD.

Uso desde la raíz del proyecto:
    python scripts/diagnosticar-contratos-historicos.py NOMBRE_BASE

Consulta solo movimientos previstos de la carga histórica (enero-septiembre
2026) que corresponden a apuntes de alquiler y carecen de contrato_id.
"""

import argparse
from collections import Counter
from datetime import date

from sqlalchemy import select

from contab.config import cargar_bases_datos
from contab.database import create_session_factory, create_sqlite_engine
from contab.models import ApunteContable, Contrato, MovimientoPrevisto

NOTA_HISTORICA = "Conciliado manualmente por carga histórica de datos"
INICIO = date(2026, 1, 1)
FIN = date(2026, 9, 30)


def intervalo_contrato(contrato: Contrato) -> str:
    fin = contrato.fecha_fin.isoformat() if contrato.fecha_fin else "abierto"
    return f"{contrato.fecha_inicio.isoformat()} a {fin}"


def contiene_periodo(contrato: Contrato, desde: date, hasta: date) -> bool:
    """Usa fecha_fin efectiva, no fecha_vencimiento (prórrogas)."""
    return (
        contrato.fecha_inicio <= desde
        and (contrato.fecha_fin is None or contrato.fecha_fin >= hasta)
    )


def diagnosticar(session) -> None:
    consulta = (
        select(MovimientoPrevisto, ApunteContable)
        .join(ApunteContable, MovimientoPrevisto.apunte_id == ApunteContable.id)
        .where(
            MovimientoPrevisto.contrato_id.is_(None),
            MovimientoPrevisto.metodo_conciliacion == "MANUAL",
            MovimientoPrevisto.notas == NOTA_HISTORICA,
            ApunteContable.fecha >= INICIO,
            ApunteContable.fecha <= FIN,
            ApunteContable.naturaleza == "INGRESO",
            ApunteContable.categoria == "ING_ALQUILERES",
        )
        .order_by(ApunteContable.fecha, ApunteContable.id)
    )
    pendientes = session.execute(consulta).all()
    contratos_por_inmueble: dict[int, list[Contrato]] = {}
    for contrato in session.scalars(select(Contrato).order_by(Contrato.fecha_inicio, Contrato.id)):
        contratos_por_inmueble.setdefault(contrato.inmueble_id, []).append(contrato)

    conteos = Counter()
    print("DIAGNÓSTICO DE ALQUILERES HISTÓRICOS SIN CONTRATO")
    print("Solo lectura. Ningún registro será modificado.")
    print(f"Identificación: notas = {NOTA_HISTORICA!r}")
    print(f"Apuntes entre {INICIO} y {FIN}; categoría ING_ALQUILERES\n")

    if not pendientes:
        print("No hay alquileres históricos sin contrato que cumplan estos filtros.")
        return

    for previsto, apunte in pendientes:
        contratos = contratos_por_inmueble.get(apunte.inmueble_id, [])
        inicio, fin = apunte.periodo_desde, apunte.periodo_hasta
        periodo_completo = inicio is not None and fin is not None
        if periodo_completo:
            compatibles = [c for c in contratos if contiene_periodo(c, inicio, fin)]
        else:
            # El script histórico no guardaba el período: la fecha del
            # apunte es una pista, NO demuestra el período del alquiler.
            compatibles = [c for c in contratos if contiene_periodo(c, apunte.fecha, apunte.fecha)]

        if len(compatibles) == 1 and periodo_completo:
            estado = "CANDIDATO ÚNICO POR PERÍODO"
            conteos["unico_periodo"] += 1
        elif len(compatibles) == 1:
            estado = "REVISAR: ÚNICO POR FECHA, SIN PERÍODO"
            conteos["unico_fecha"] += 1
        elif len(compatibles) > 1:
            estado = "AMBIGUO: VARIOS CONTRATOS"
            conteos["ambiguos"] += 1
        else:
            estado = "SIN CONTRATO COMPATIBLE"
            conteos["sin_candidato"] += 1

        importe = -apunte.total if apunte.importe_negativo else apunte.total
        print(f"[{estado}] previsto={previsto.id}, apunte={apunte.id}")
        print(f"  Inmueble: {apunte.inmueble.referencia} (id={apunte.inmueble_id})")
        print(f"  Fecha: {apunte.fecha} | Concepto: {apunte.concepto}")
        print(f"  Importe: {importe / 100:.2f} EUR | Estado: {previsto.estado}")
        print(f"  Período: {inicio} a {fin}" if periodo_completo else "  Período: NO INFORMADO (se buscan pistas por fecha del apunte)")
        if compatibles:
            for c in compatibles:
                print(f"  Contrato candidato: id={c.id}, vigencia efectiva={intervalo_contrato(c)}, genera_factura={c.genera_factura}")
        else:
            print("  Contratos del inmueble:")
            if contratos:
                for c in contratos:
                    print(f"    id={c.id}, vigencia efectiva={intervalo_contrato(c)}")
            else:
                print("    Ninguno registrado")
        print()

    print("RESUMEN")
    print(f"  Alquileres históricos sin contrato: {len(pendientes)}")
    print(f"  Candidato único por período explícito: {conteos['unico_periodo']}")
    print(f"  Candidato único solo por fecha (revisar): {conteos['unico_fecha']}")
    print(f"  Varios contratos candidatos: {conteos['ambiguos']}")
    print(f"  Sin contrato candidato: {conteos['sin_candidato']}")
    print("No se ha modificado la base de datos.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="Nombre de base de datos definido en contab.ini")
    args = parser.parse_args()
    bases = cargar_bases_datos()
    if args.database not in bases:
        parser.error(f"Base desconocida: {args.database}")

    engine = create_sqlite_engine(bases[args.database])
    try:
        with create_session_factory(engine)() as session:
            diagnosticar(session)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

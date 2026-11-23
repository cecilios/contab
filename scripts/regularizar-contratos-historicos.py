#!/usr/bin/env python3
"""Asocia al contrato vigente los alquileres de la carga histórica de 2026.

Uso desde la raíz de Contab:
    python scripts/regularizar-contratos-historicos.py NOMBRE_BASE

Solo actualiza MovimientoPrevisto.contrato_id, previa confirmación.
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


def preparar_asociaciones(session):
    """Devuelve asociaciones inequívocas e incidencias, sin modificar datos."""
    pendientes = session.execute(
        select(MovimientoPrevisto, ApunteContable)
        .join(
            ApunteContable,
            MovimientoPrevisto.apunte_id == ApunteContable.id,
        )
        .where(
            MovimientoPrevisto.contrato_id.is_(None),
            MovimientoPrevisto.metodo_conciliacion == "MANUAL",
            MovimientoPrevisto.notas == NOTA_HISTORICA,
            ApunteContable.fecha.between(INICIO, FIN),
            ApunteContable.naturaleza == "INGRESO",
            ApunteContable.categoria == "ING_ALQUILERES",
        )
        .order_by(ApunteContable.fecha, ApunteContable.id)
    ).all()

    contratos_por_inmueble = {}
    for contrato in session.scalars(select(Contrato)).all():
        contratos_por_inmueble.setdefault(contrato.inmueble_id, []).append(contrato)

    asociaciones = []
    incidencias = []
    for previsto, apunte in pendientes:
        candidatos = [
            contrato
            for contrato in contratos_por_inmueble.get(apunte.inmueble_id, [])
            if contrato.fecha_inicio <= apunte.fecha
            and (contrato.fecha_fin is None or contrato.fecha_fin >= apunte.fecha)
        ]
        if len(candidatos) != 1:
            incidencias.append((previsto, apunte, len(candidatos)))
            continue
        asociaciones.append((previsto, apunte, candidatos[0]))

    return asociaciones, incidencias


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="Nombre de base definido en contab.ini")
    args = parser.parse_args()

    bases = cargar_bases_datos()
    if args.database not in bases:
        parser.error(f"Base desconocida: {args.database}")

    engine = create_sqlite_engine(bases[args.database])
    try:
        with create_session_factory(engine)() as session:
            asociaciones, incidencias = preparar_asociaciones(session)

            print("REGULARIZACIÓN DE ALQUILERES HISTÓRICOS")
            print(f"Base: {args.database}")
            print(f"Asociaciones propuestas: {len(asociaciones)}")
            print(f"Incidencias: {len(incidencias)}\n")

            for previsto, apunte, contrato in asociaciones:
                print(
                    f"Previsto {previsto.id} | {apunte.inmueble.referencia} | "
                    f"{apunte.fecha} | {apunte.concepto} | "
                    f"Contrato {contrato.id} (desde {contrato.fecha_inicio})"
                )

            for previsto, apunte, cantidad in incidencias:
                print(
                    f"INCIDENCIA: previsto {previsto.id}, "
                    f"{apunte.inmueble.referencia}, {apunte.fecha}: "
                    f"{cantidad} contratos candidatos"
                )

            if incidencias:
                print("\nNo se ha modificado nada: hay asociaciones sin resolver.")
                return

            if not asociaciones:
                print("\nNo hay movimientos pendientes de regularizar.")
                return

            print("\nSolo se modificará MovimientoPrevisto.contrato_id.")
            respuesta = input("¿Confirmar la regularización? [s/N]: ").strip().lower()
            if respuesta != "s":
                print("Operación cancelada. No se ha modificado nada.")
                return

            for previsto, _, contrato in asociaciones:
                previsto.contrato_id = contrato.id

            session.commit()
            print(f"Regularización completada: {len(asociaciones)} movimientos actualizados.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

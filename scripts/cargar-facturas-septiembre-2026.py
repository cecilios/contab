#!/usr/bin/env python3
#
# Uso: python scripts/cargar-facturas-septiembre-2026.py NOMBRE_BASE
#
"""Carga las facturas históricas de septiembre de 2026."""

import argparse
from datetime import date

from sqlalchemy import select

from contab.config import cargar_bases_datos
from contab.database import (
    create_session_factory,
    create_sqlite_engine,
)
from contab.facturacion.services import crear_factura
from contab.models import Contrato, Factura


PERIODO = date(2026, 9, 1)
FIN_PERIODO = date(2026, 9, 30)
SECUENCIA = 9


def main() -> None:
    """Carga las facturas de septiembre para iniciar la numeración."""
    parser = argparse.ArgumentParser(
        description=(
            "Carga las facturas históricas de septiembre de 2026."
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
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        factura_existente = session.scalar(
            select(Factura.id)
            .where(Factura.periodo == PERIODO)
            .limit(1)
        )

        if factura_existente is not None:
            raise SystemExit(
                "Ya existen facturas de septiembre de 2026. "
                "No se ha modificado ningún dato."
            )

        contratos = session.scalars(
            select(Contrato)
            .where(
                Contrato.genera_factura.is_(True),
                Contrato.fecha_inicio <= FIN_PERIODO,
                (
                    (Contrato.fecha_fin.is_(None))
                    | (Contrato.fecha_fin >= PERIODO)
                ),
                Contrato.fecha_inicio_facturacion <= PERIODO,
            )
            .order_by(Contrato.id)
        ).all()

        facturas = []

        for contrato in contratos:
            factura = crear_factura(
                contrato,
                PERIODO,
                PERIODO,
            )

            factura.numero_secuencia = SECUENCIA
            factura.numero_factura = (
                f"{SECUENCIA:02d}/"
                f"{PERIODO.year}"
                f"{contrato.inmueble.codigo_facturacion}"
            )

            session.add(factura)
            facturas.append(factura)

        session.commit()

    print(
        f"Base actualizada: {args.database}. "
        f"{len(facturas)} facturas de septiembre de 2026 creadas."
    )


if __name__ == "__main__":
    main()

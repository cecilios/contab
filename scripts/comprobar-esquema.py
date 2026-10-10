#!/usr/bin/env python3

"""
Comprueba que una base de datos SQLite tiene exactamente el esquema
estructural definido por los modelos SQLAlchemy actuales de Contab.

Uso:
    python scripts/comprobar-esquema.py data/squash.db

Está pensado principalmente para validar una nueva migración inicial
después de hacer un squash:
    1. Crear una base de datos vacía.
    2. Ejecutar sobre ella `contab-db upgrade`.
    3. Ejecutar este script sobre la base resultante.

El script compara directamente la base de datos con Base.metadata,
obtenido de models.py. No crea ni necesita una base auxiliar
`modelos.db`.

La comparación es estructural y no depende del orden textual de
columnas, constraints o claves foráneas en los CREATE TABLE.

Si el esquema coincide muestra:
    El esquema coincide con los modelos actuales.
y termina con código 0.

Si encuentra diferencias estructurales, las muestra y termina con
código 1.
"""

import sys
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from contab.database import Base, create_sqlite_engine
import contab.models  # noqa: F401


def main() -> int:
    if len(sys.argv) != 2:
        print(
            f"Uso: {sys.argv[0]} BASE_DE_DATOS",
            file=sys.stderr,
        )
        return 2

    ruta = Path(sys.argv[1])

    if not ruta.is_file():
        print(
            f"No existe la base de datos: {ruta}",
            file=sys.stderr,
        )
        return 2

    engine = create_sqlite_engine(
        f"sqlite:///{ruta.resolve()}"
    )

    with engine.connect() as connection:
        contexto = MigrationContext.configure(
            connection
        )

        diferencias = compare_metadata(
            contexto,
            Base.metadata,
        )

    if diferencias:
        print(
            "El esquema presenta diferencias respecto "
            "a los modelos actuales:"
        )

        for diferencia in diferencias:
            print(f"  {diferencia!r}")

        return 1

    print(
        "El esquema coincide con los modelos actuales."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

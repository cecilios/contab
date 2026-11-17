
#!/usr/bin/env python3
"""Carga excepcional de apuntes históricos de enero a septiembre de 2026."""

import argparse
import re

from datetime import date
from pathlib import Path

from sqlalchemy import select

from contab.config import (
    cargar_bases_datos,
    cargar_categorias_contables,
)
from contab.contabilidad.services import crear_apunte_contable
from contab.conciliacion.services import (
    crear_movimiento_desde_apunte,
    conciliar_movimiento_previsto_manualmente,
)
from contab.database import (
    create_session_factory,
    create_sqlite_engine,
)
from contab.models import Inmueble


NOTA_CONCILIACION = (
    "Conciliado manualmente por carga histórica de datos"
)

INICIO = date(2026, 1, 1)
FIN = date(2026, 9, 30)



def importe_en_centimos(texto):
    """Convierte euros con coma decimal y miles opcionales en céntimos."""
    if not re.fullmatch(
        r"-?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?",
        texto,
    ):
        raise ValueError(f"Importe no válido: {texto!r}")

    negativo = texto.startswith("-")

    # Eliminar el signo y los separadores de miles.
    partes = texto.lstrip("-").replace(".", "").split(",")

    euros = int(partes[0])
    centimos = (
        int(partes[1].ljust(2, "0"))
        if len(partes) == 2
        else 0
    )

    importe = euros * 100 + centimos
    return -importe if negativo else importe


def leer_apuntes(ruta):
    """Lee los apuntes del archivo de texto."""
    filas = []

    for numero, linea in enumerate(
        Path(ruta).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        linea = linea.strip()

        if not linea or linea.startswith("#"):
            continue

        try:
            campos = [
                campo.strip()
                for campo in linea.split(";")
            ]

            if not 5 <= len(campos) <= 7:
                raise ValueError(
                    "Se esperan entre 5 y 7 campos"
                )

            referencia, fecha_texto, clasificacion, concepto, base_texto = (
                campos[:5]
            )

            if not referencia or not concepto:
                raise ValueError(
                    "Inmueble y concepto son obligatorios"
                )

            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", fecha_texto
            ):
                raise ValueError("Formato de fecha incorrecto")

            fecha = date.fromisoformat(fecha_texto)

            if not INICIO <= fecha <= FIN:
                raise ValueError(
                    "La fecha debe estar entre "
                    "2026-01-01 y 2026-09-30"
                )

            clasificacion = clasificacion.upper()
            partes = clasificacion.split(".")

            if len(partes) > 2 or not all(partes):
                raise ValueError("Clasificación incorrecta")

            categoria = partes[0]
            subcategoria = (
                partes[1] if len(partes) == 2 else ""
            )

            base_firmada = importe_en_centimos(base_texto)

            if base_firmada == 0:
                raise ValueError(
                    "La base debe ser distinta de cero"
                )

            iva = (
                importe_en_centimos(campos[5])
                if len(campos) >= 6 and campos[5]
                else 0
            )

            retencion = (
                importe_en_centimos(campos[6])
                if len(campos) >= 7 and campos[6]
                else 0
            )

            if iva < 0 or retencion < 0:
                raise ValueError(
                    "IVA y retención no pueden ser negativos"
                )

            filas.append({
                "referencia": referencia,
                "fecha": fecha,
                "categoria": categoria,
                "subcategoria": subcategoria,
                "concepto": concepto,
                "base": abs(base_firmada),
                "importe_negativo": base_firmada < 0,
                "iva_importe": iva,
                "retencion_importe": retencion,
            })

        except ValueError as exc:
            raise ValueError(
                f"Error en la línea {numero}: {exc}"
            ) from exc

    if not filas:
        raise ValueError(
            "El archivo no contiene apuntes"
        )

    return filas


def preparar_carga(session, categorias, filas):
    """Prepara apuntes y movimientos sin confirmar la transacción."""
    inmuebles = {
        inmueble.referencia: inmueble
        for inmueble in session.scalars(
            select(Inmueble)
        ).all()
    }

    numero_distribuciones = 0

    for numero, fila in enumerate(filas, start=1):
        try:
            inmueble = inmuebles.get(fila["referencia"])

            if inmueble is None:
                raise ValueError(
                    f"Inmueble desconocido: {fila['referencia']}"
                )

            categoria = categorias.get(fila["categoria"])

            if categoria is None:
                raise ValueError(
                    f"Categoría desconocida: {fila['categoria']}"
                )

            apunte = crear_apunte_contable(
                inmueble=inmueble,
                categorias=categorias,
                fecha=fila["fecha"],
                naturaleza=categoria.naturaleza,
                categoria=fila["categoria"],
                subcategoria=fila["subcategoria"],
                concepto=fila["concepto"],
                base=fila["base"],
                importe_negativo=fila["importe_negativo"],
                iva_importe=fila["iva_importe"],
                retencion_importe=fila["retencion_importe"],
                tratamiento="CONTABILIZAR",
            )

            movimiento = crear_movimiento_desde_apunte(
                apunte=apunte,
            )

            conciliar_movimiento_previsto_manualmente(
                movimiento,
                NOTA_CONCILIACION,
            )

            session.add(apunte)
            session.add(movimiento)

            numero_distribuciones += len(
                apunte.distribuciones
            )

        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(
                f"Error en el apunte {numero}: {exc}"
            ) from exc

    return (
        len(filas),
        len(filas),
        numero_distribuciones,
    )


def main():
    """Valida, muestra un resumen y confirma la carga histórica."""
    parser = argparse.ArgumentParser(
        description="Carga apuntes históricos de 2026."
    )
    parser.add_argument(
        "database",
        help="Nombre de la base definida en contab.ini",
    )
    parser.add_argument(
        "archivo",
        type=Path,
        help="Archivo de texto con los apuntes a importar",
    )
    args = parser.parse_args()

    bases = cargar_bases_datos()

    if args.database not in bases:
        raise SystemExit(
            f"Base desconocida: {args.database}"
        )

    try:
        filas = leer_apuntes(args.archivo)
        categorias = cargar_categorias_contables()

        engine = create_sqlite_engine(
            bases[args.database]
        )
        session_factory = create_session_factory(engine)

        with session_factory() as session:
            try:
                resumen = preparar_carga(
                    session,
                    categorias,
                    filas,
                )

                # Comprueba también las restricciones de SQLite
                # sin confirmar todavía la transacción.
                session.flush()

                print()
                print(f"Base de datos: {args.database}")
                print("Período: enero-septiembre 2026")
                print()
                print(f"Apuntes a importar: {resumen[0]}")
                print(f"Movimientos previstos: {resumen[1]}")
                print(f"Distribuciones: {resumen[2]}")
                print(f"Conciliaciones manuales: {resumen[1]}")
                print()

                respuesta = input(
                    "¿Confirmar la importación? [s/N]: "
                ).strip().lower()

                if respuesta != "s":
                    session.rollback()
                    print("Importación cancelada.")
                    return

                session.commit()
                print("Importación completada correctamente.")

            except Exception:
                session.rollback()
                raise

    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()

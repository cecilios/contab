from datetime import date
from pathlib import Path

from contab.conciliacion.importacion import (
    leer_csv_ibercaja,
    preparar_movimientos_bancarios,
)
from contab.conciliacion.services import (
    buscar_candidatos_conciliacion,
    proponer_conciliacion,
)
from contab.models import (
    Inmueble,
    MovimientoBancario,
    MovimientoPrevisto,
)


DATOS = (
    Path(__file__).parent.parent
    / "tests"
    / "datos"
    / "movimientos-ibercaja.csv"
)


def crear_previstos() -> tuple[
    list[MovimientoPrevisto],
    list[tuple[str, str, str]],
]:
    mariscal = Inmueble(
        referencia="MARISCAL",
        tipo="V",
        codigo_facturacion="MR",
        descripcion="Piso Mariscal Ramos",
        direccion="Mariscal Ramos 15",
        poblacion="Madrid",
        provincia="Madrid",
    )

    moncada = Inmueble(
        referencia="MONCADA",
        tipo="V",
        codigo_facturacion="MO",
        descripcion="Piso Moncada",
        direccion="Moncada 7",
        poblacion="Madrid",
        provincia="Madrid",
    )

    previstos = [
        MovimientoPrevisto(
            inmueble=mariscal,
            fecha_prevista_desde=date(2026, 9, 1),
            fecha_prevista_hasta=date(2026, 9, 5),
            naturaleza="INGRESO",
            concepto="Alquiler septiembre",
            importe_esperado=167214,
            contraparte="JOSE JIMENEZ JAMARILLO",
            estado="PENDIENTE",
        ),
        MovimientoPrevisto(
            inmueble=mariscal,
            fecha_prevista_desde=date(2026, 9, 1),
            fecha_prevista_hasta=date(2026, 9, 5),
            naturaleza="INGRESO",
            concepto="Alquiler septiembre",
            importe_esperado=160000,
            contraparte="BARBARA BONITA BARCENAS",
            estado="PENDIENTE",
        ),
        MovimientoPrevisto(
            inmueble=mariscal,
            fecha_prevista_desde=date(2026, 9, 1),
            fecha_prevista_hasta=date(2026, 9, 5),
            naturaleza="GASTO",
            concepto="Comunidad septiembre",
            importe_esperado=19257,
            contraparte="",
            estado="PENDIENTE",
        ),
        MovimientoPrevisto(
            inmueble=moncada,
            fecha_prevista_desde=date(2026, 9, 1),
            fecha_prevista_hasta=date(2026, 9, 5),
            naturaleza="GASTO",
            concepto="Comunidad septiembre",
            importe_esperado=3408,
            contraparte="",
            estado="PENDIENTE",
        ),
        MovimientoPrevisto(
            inmueble=moncada,
            fecha_prevista_desde=date(2026, 8, 1),
            fecha_prevista_hasta=date(2026, 8, 10),
            naturaleza="GASTO",
            concepto="Reparación agosto",
            importe_esperado=9075,
            contraparte="INSTALACIONES GOMEZ, S.L.",
            estado="PENDIENTE",
        ),
    ]

    aliases = [
        (
            "COMUNIDAD",
            "MARISCAL",
            "C.P. MARISCAL RAMOS",
        ),
        (
            "COMUNIDAD",
            "MONCADA",
            "CDAD.PROP.CL.MONCAD",
        ),
    ]

    return previstos, aliases


def descripcion_previsto(
    movimiento: MovimientoPrevisto,
) -> str:
    return (
        f"{movimiento.inmueble.referencia} / "
        f"{movimiento.concepto}"
    )


def main() -> None:
    contenido = DATOS.read_text(encoding="utf-8")
    importados = leer_csv_ibercaja(contenido)

    # No necesitamos persistir nada para este diagnóstico.
    bancarios = [
        MovimientoBancario(
            fecha=movimiento.fecha,
            naturaleza=movimiento.naturaleza,
            importe=movimiento.importe,
            tipo_original=movimiento.tipo_original,
            descripcion_original=movimiento.descripcion_original,
            referencia_bancaria=movimiento.referencia_bancaria,
            huella_importacion=movimiento.huella_importacion,
            estado="PENDIENTE",
        )
        for movimiento in importados
    ]

    previstos, aliases = crear_previstos()

    for bancario in bancarios:
        propuesta = proponer_conciliacion(
            bancario,
            previstos,
            aliases_configurados=aliases,
        )

        if propuesta is None:
            continue

        candidatos = buscar_candidatos_conciliacion(
            bancario,
            previstos,
            aliases_configurados=aliases,
        )

        print()
        print(
            f"{bancario.fecha} "
            f"{bancario.naturaleza:7} "
            f"{bancario.importe / 100:9.2f}  "
            f"{bancario.descripcion_original}"
        )

        print(
            "  PROPUESTA:",
            descripcion_previsto(propuesta),
        )

        for candidato, puntuacion in candidatos[:3]:
            print(
                f"    {puntuacion:3}  "
                f"{descripcion_previsto(candidato)}"
            )


if __name__ == "__main__":
    main()


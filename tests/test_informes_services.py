"""Pruebas de los servicios para informes y exportaciones."""

import csv
from datetime import date
from io import StringIO

from contab.informes.services import generar_csv_iva
from contab.models import ApunteContable, Inmueble


def test_generar_csv_iva_clasifica_y_totaliza_apuntes(
    session,
    inmueble,
) -> None:
    """Comprueba el contenido fundamental de la exportación anual."""

    # Preparamos apuntes de ingreso y gasto del primer trimestre.
    ingreso = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 1, 5),
        naturaleza="INGRESO",
        categoria="ING_ALQUILER",
        concepto="Alquiler enero",
        base=100000,
        iva_importe=21000,
        retencion_importe=19000,
        total=102000,
        tratamiento="CONTABILIZAR",
        nombre_documento="Factura enero.pdf",
    )

    gasto = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 2, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad febrero",
        base=20000,
        iva_importe=4200,
        retencion_importe=0,
        total=24200,
        tratamiento="CONTABILIZAR",
        nombre_documento="Comunidad febrero.pdf",
    )

    # Estos apuntes no deben aparecer en la exportación.
    otro_anio = ApunteContable(
        inmueble=inmueble,
        fecha=date(2025, 12, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Gasto de otro año",
        base=5000,
        iva_importe=0,
        retencion_importe=0,
        total=5000,
        tratamiento="CONTABILIZAR",
        nombre_documento="Otro año.pdf",
    )

    repercutido = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 3, 1),
        naturaleza="GASTO",
        categoria="GAS_TRIBUTOS",
        concepto="Gasto repercutido",
        base=3000,
        iva_importe=0,
        retencion_importe=0,
        total=3000,
        tratamiento="REPERCUTIR",
        nombre_documento="Gasto repercutido.pdf",
    )

    session.add_all(
        [
            ingreso,
            gasto,
            otro_anio,
            repercutido,
        ]
    )
    session.commit()

    # Generamos y leemos el CSV como una tabla.
    contenido = generar_csv_iva(
        inmueble=inmueble,
        apuntes=[
            repercutido,
            otro_anio,
            gasto,
            ingreso,
        ],
        anio=2026,
    )

    filas = list(
        csv.reader(
            StringIO(contenido),
            delimiter=";",
        )
    )

    # Localizamos el primer trimestre y comprobamos sus movimientos.
    cabecera = [
        "",
        "1T",
        "Ingresos",
        "Gastos",
        "IVA",
        "Retención",
    ]
    posicion = filas.index(cabecera)

    assert filas[posicion + 1] == [
        "",
        "Alquiler enero",
        "1.000,00",
        "",
        "210,00",
        "190,00",
    ]
    assert filas[posicion + 2] == [
        "",
        "Comunidad febrero",
        "",
        "200,00",
        "",
        "",
    ]

    # Debe existir una fila vacía antes de los totales.
    # Los trimestres con apuntes no separan los totales.
    assert filas[posicion + 3] == [
        "",
        "Totales 1T",
        "1.000,00",
        "200,00",
        "210,00",
        "190,00",
    ]
    assert filas[posicion + 4] == [
        "",
        "Ingresos netos",
        "800,00",
        "",
        "",
        "",
    ]

    # Comprobamos filtros y presencia de los cuatro trimestres.
    assert "Gasto de otro año" not in contenido
    assert "Gasto repercutido" not in contenido

    assert sum(
        fila[1] in {"1T", "2T", "3T", "4T"}
        for fila in filas
        if len(fila) > 1
    ) == 4

    # Comprobamos los totales del año.
    assert [
        "",
        "Totales del año",
        "1.000,00",
        "200,00",
        "210,00",
        "190,00",
    ] in filas

    assert [
        "",
        "Ingresos netos",
        "800,00",
        "",
        "",
        "",
    ] in filas


def test_generar_csv_iva_no_mezcla_inmuebles(
    session,
    inmueble,
) -> None:
    """Comprueba que sólo se exportan apuntes del inmueble indicado."""

    # Creamos otro inmueble y un apunte que no debe exportarse.
    otro_inmueble = Inmueble(
        referencia="PISO-2",
        tipo="P",
        codigo_facturacion="P2",
        descripcion="Otro piso",
        direccion="Otra dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    apunte_ajeno = ApunteContable(
        inmueble=otro_inmueble,
        fecha=date(2026, 4, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILER",
        concepto="Ingreso de otro inmueble",
        base=50000,
        iva_importe=0,
        retencion_importe=0,
        total=50000,
        tratamiento="CONTABILIZAR",
        nombre_documento="Otro ingreso.pdf",
    )

    session.add_all(
        [
            otro_inmueble,
            apunte_ajeno,
        ]
    )
    session.commit()

    # Generamos el informe solicitado para el primer inmueble.
    contenido = generar_csv_iva(
        inmueble=inmueble,
        apuntes=[apunte_ajeno],
        anio=2026,
    )

    filas = list(
        csv.reader(
            StringIO(contenido),
            delimiter=";",
        )
    )

    assert "Ingreso de otro inmueble" not in contenido

    # Los cuatro trimestres deben existir y tener totales a cero.
    for trimestre in range(1, 5):
        cabecera = [
            "",
            f"{trimestre}T",
            "Ingresos",
            "Gastos",
            "IVA",
            "Retención",
        ]
        posicion = filas.index(cabecera)

        assert filas[posicion + 1] == [
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        assert filas[posicion + 2] == [
            "",
            f"Totales {trimestre}T",
            "0,00",
            "0,00",
            "0,00",
            "0,00",
        ]



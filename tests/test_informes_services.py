"""Pruebas de los servicios para informes y exportaciones."""

import csv
from datetime import date
from io import BytesIO, StringIO
from zipfile import ZipFile

from contab.informes.services import (
    generar_csv_iva,
    generar_csv_resumen_iva,
    generar_zip_iva,
    seleccionar_inmuebles_exportacion_iva,
)
from contab.models import (
    ApunteContable,
    Contrato,
    Inmueble,
)



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


def test_seleccionar_inmuebles_exportacion_iva(
    session,
    inmueble,
) -> None:
    """Selecciona activos e inactivos con apuntes en el año."""

    # Preparamos inmuebles con diferentes situaciones.
    activo_sin_apuntes = Inmueble(
        referencia="ACTIVO-SIN-APUNTES",
        tipo="L",
        codigo_facturacion="ASA",
        descripcion="Activo sin apuntes",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    inactivo_con_apuntes = Inmueble(
        referencia="INACTIVO-CON-APUNTES",
        tipo="L",
        codigo_facturacion="ICA",
        descripcion="Inactivo con apuntes",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        activo=False,
    )

    inactivo_otro_anio = Inmueble(
        referencia="INACTIVO-OTRO-ANIO",
        tipo="L",
        codigo_facturacion="IOA",
        descripcion="Inactivo con apuntes antiguos",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        activo=False,
    )

    apunte_actual = ApunteContable(
        inmueble=inactivo_con_apuntes,
        fecha=date(2026, 3, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
        tratamiento="CONTABILIZAR",
        nombre_documento="Comunidad.pdf",
    )

    apunte_antiguo = ApunteContable(
        inmueble=inactivo_otro_anio,
        fecha=date(2025, 3, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad antigua",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
        tratamiento="CONTABILIZAR",
        nombre_documento="Comunidad antigua.pdf",
    )

    session.add_all(
        [
            activo_sin_apuntes,
            inactivo_con_apuntes,
            inactivo_otro_anio,
            apunte_actual,
            apunte_antiguo,
        ]
    )
    session.commit()

    # Solicitamos los inmuebles aplicables a 2026.
    seleccionados = (
        seleccionar_inmuebles_exportacion_iva(
            inmuebles=[
                inactivo_otro_anio,
                inactivo_con_apuntes,
                activo_sin_apuntes,
                inmueble,
            ],
            apuntes=[
                apunte_antiguo,
                apunte_actual,
            ],
            anio=2026,
        )
    )

    assert [
        elemento.referencia
        for elemento in seleccionados
    ] == [
        "ACTIVO-SIN-APUNTES",
        "INACTIVO-CON-APUNTES",
        "LOCAL-1",
    ]


def test_generar_zip_iva_contiene_un_csv_por_inmueble(
    session,
    inmueble,
) -> None:
    """Genera un ZIP con los CSV de los inmuebles aplicables."""

    # Preparamos otro inmueble con un gasto.
    segundo = Inmueble(
        referencia="PISO-2",
        tipo="P",
        codigo_facturacion="P2",
        descripcion="Segundo inmueble",
        direccion="Dirección 2",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    ingreso = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 1, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler enero",
        base=100000,
        iva_importe=21000,
        retencion_importe=19000,
        total=102000,
        tratamiento="CONTABILIZAR",
        nombre_documento="Alquiler enero.pdf",
    )

    gasto = ApunteContable(
        inmueble=segundo,
        fecha=date(2026, 2, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad febrero",
        base=20000,
        iva_importe=0,
        retencion_importe=0,
        total=20000,
        tratamiento="CONTABILIZAR",
        nombre_documento="Comunidad febrero.pdf",
    )

    session.add_all(
        [
            segundo,
            ingreso,
            gasto,
        ]
    )
    session.commit()

    # Generamos el archivo comprimido.
    contenido_zip = generar_zip_iva(
        inmuebles=[
            segundo,
            inmueble,
        ],
        apuntes=[
            gasto,
            ingreso,
        ],
        anio=2026,
    )

    # Abrimos el ZIP y comprobamos sus archivos.
    with ZipFile(BytesIO(contenido_zip)) as archivo:
        assert archivo.namelist() == [
            "iva-LOCAL-1-2026.csv",
            "iva-PISO-2-2026.csv",
        ]

        csv_local = archivo.read(
            "iva-LOCAL-1-2026.csv"
        ).decode("utf-8")

        csv_piso = archivo.read(
            "iva-PISO-2-2026.csv"
        ).decode("utf-8")

    assert "Alquiler enero" in csv_local
    assert "Comunidad febrero" not in csv_local

    assert "Comunidad febrero" in csv_piso
    assert "Alquiler enero" not in csv_piso


def test_generar_csv_resumen_iva_clasifica_y_totaliza(
    session,
) -> None:
    """Genera el resumen separando inmuebles facturables del resto."""

    # Creamos un local facturable y un piso sin factura.
    local = Inmueble(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local comercial",
        direccion="Dirección local",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )
    piso = Inmueble(
        referencia="PISO-1",
        tipo="P",
        codigo_facturacion="P1",
        descripcion="Piso",
        direccion="Dirección piso",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )
    subdividido_sin_apuntes = Inmueble(
        referencia="SUBDIVIDIDO-SIN-APUNTES",
        tipo="T",
        codigo_facturacion="SSA",
        descripcion="Subdividido vacío",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )
    subdividido_con_apuntes = Inmueble(
        referencia="SUBDIVIDIDO-CON-APUNTES",
        tipo="T",
        codigo_facturacion="SCA",
        descripcion="Subdividido con gastos",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato_local = Contrato(
        inmueble=local,
        fecha_inicio=date(2026, 1, 1),
        fecha_vencimiento=date(2030, 12, 31),
        genera_factura=True,
        fecha_inicio_facturacion=date(2026, 1, 1),
        fianza=0,
        direccion_facturacion="Dirección local",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler local",
    )
    contrato_piso = Contrato(
        inmueble=piso,
        fecha_inicio=date(2026, 1, 1),
        fecha_vencimiento=date(2030, 12, 31),
        genera_factura=False,
        fecha_inicio_facturacion=date(2026, 1, 1),
        fianza=0,
        direccion_facturacion="",
        poblacion_facturacion="",
        provincia_facturacion="",
        concepto_factura="",
    )

    # Añadimos ingresos y gastos del primer trimestre.
    apuntes = [
        ApunteContable(
            inmueble=local,
            fecha=date(2026, 1, 5),
            naturaleza="INGRESO",
            categoria="ING_ALQUILER",
            concepto="Alquiler local",
            base=100000,
            iva_importe=21000,
            retencion_importe=19000,
            total=102000,
            tratamiento="CONTABILIZAR",
            nombre_documento="Factura local.pdf",
        ),
        ApunteContable(
            inmueble=local,
            fecha=date(2026, 2, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad local",
            base=20000,
            iva_importe=0,
            retencion_importe=0,
            total=20000,
            tratamiento="CONTABILIZAR",
            nombre_documento="Comunidad local.pdf",
        ),
        ApunteContable(
            inmueble=piso,
            fecha=date(2026, 1, 5),
            naturaleza="INGRESO",
            categoria="ING_ALQUILER",
            concepto="Alquiler piso",
            base=80000,
            iva_importe=0,
            retencion_importe=0,
            total=80000,
            tratamiento="CONTABILIZAR",
            nombre_documento="Ingreso piso.pdf",
        ),
        ApunteContable(
            inmueble=piso,
            fecha=date(2026, 2, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad piso",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
            tratamiento="CONTABILIZAR",
            nombre_documento="Comunidad piso.pdf",
        ),
        ApunteContable(
            inmueble=subdividido_con_apuntes,
            fecha=date(2026, 2, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad inmueble",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
            tratamiento="CONTABILIZAR",
            nombre_documento="Comunidad inmueble.pdf",
        ),
    ]

    session.add_all(
        [
            local,
            piso,
            subdividido_sin_apuntes,
            subdividido_con_apuntes,
            contrato_local,
            contrato_piso,
            *apuntes,
        ]
    )
    session.commit()

    # Generamos y leemos el resumen.
    contenido = generar_csv_resumen_iva(
        inmuebles=[
            local,
            piso,
            subdividido_sin_apuntes,
            subdividido_con_apuntes,
        ],
        contratos=[
            contrato_local,
            contrato_piso,
        ],
        apuntes=apuntes,
        anio=2026,
        porcentaje_irpf_estimado=2500,
    )

    filas = list(
        csv.reader(
            StringIO(contenido),
            delimiter=";",
        )
    )

    # El local usa su retención real:
    # 1.000 - 200 - 210 - 190 = 400.
    assert [
        "LOCAL-1",
        "1.000,00",
        "200,00",
        "190,00",
        "210,00",
        "400,00",
    ] in filas

    # El piso aplica la estimación indicada del 25 %:
    # 800 - 100 - 200 = 500.
    assert [
        "PISO-1",
        "800,00",
        "100,00",
        "200,00",
        "0,00",
        "500,00",
    ] in filas

    # El local subdividido con apuntes aparece
    # sólo tiene un gasto de 100,00; no tiene ingresos, IVA ni retención
    assert [
        "SUBDIVIDIDO-CON-APUNTES",
        "0,00",
        "100,00",
        "0,00",
        "0,00",
        "-100,00",
    ] in filas
    assert (
        "SUBDIVIDIDO-SIN-APUNTES"
        not in contenido
    )

    assert "1T - Locales comerciales" in contenido
    assert "1T - Pisos y otros" in contenido
    assert "Totales 1T" in contenido
    assert "Totales del año 2026" in contenido
    assert "Hacienda (25,00%)" in contenido



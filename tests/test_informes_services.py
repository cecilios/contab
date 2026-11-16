"""Pruebas de los servicios para informes y exportaciones."""

import csv
from datetime import date
from io import BytesIO, StringIO
from zipfile import ZipFile

from contab.config import CategoriaContable
from contab.informes.services import (
    generar_csv_iva,
    generar_zip_iva,
    importe_irpf_estimado,
    preparar_ingresos_gastos_anuales,
    preparar_resumen_anual_iva,
    seleccionar_inmuebles_exportacion_iva,
)
from contab.models import (
    ApunteContable,
    Contrato,
    DistribucionApunte,
    ImputacionContrato,
    Inmueble,
)



def _crear_inmueble_prueba(**datos) -> Inmueble:
    """Construye un inmueble con datos de propiedad válidos."""

    es_hijo = (
        datos.get("inmueble_padre") is not None
        or datos.get("inmueble_padre_id") is not None
    )

    if es_hijo:
        propiedad = {
            "porcentaje_titular": None,
            "tipo_derecho": None,
            "porcentaje_derecho": None,
            "fecha_adquisicion": None,
            "tipo_adquisicion": None,
            "importe_adquisicion": None,
            "gastos_adquisicion": None,
            "fecha_transmision": None,
        }
    else:
        propiedad = {
            "porcentaje_titular": 10000,
            "tipo_derecho": "PLENA_PROPIEDAD",
            "porcentaje_derecho": 10000,
            "fecha_adquisicion": date(2020, 1, 1),
            "tipo_adquisicion": "ONEROSA",
            "importe_adquisicion": 0,
            "gastos_adquisicion": 0,
            "fecha_transmision": None,
        }

    return Inmueble(**{**propiedad, **datos})




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

    assert filas[posicion + 3] == [
        "",
        "Gasto repercutido",
        "",
        "30,00",
        "",
        "",
    ]

    # Debe existir una fila vacía antes de los totales.
    # Los trimestres con apuntes no separan los totales.
    assert filas[posicion + 4] == [
        "",
        "Totales 1T",
        "1.000,00",
        "230,00",
        "210,00",
        "190,00",
    ]
    assert filas[posicion + 5] == [
        "",
        "Ingresos netos",
        "770,00",
        "",
        "",
        "",
    ]

    # Comprobamos filtros y presencia de los cuatro trimestres.
    assert "Gasto de otro año" not in contenido

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
        "230,00",
        "210,00",
        "190,00",
    ] in filas

    assert [
        "",
        "Ingresos netos",
        "770,00",
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
    otro_inmueble = _crear_inmueble_prueba(
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
    activo_sin_apuntes = _crear_inmueble_prueba(
        referencia="ACTIVO-SIN-APUNTES",
        tipo="L",
        codigo_facturacion="ASA",
        descripcion="Activo sin apuntes",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    inactivo_con_apuntes = _crear_inmueble_prueba(
        referencia="INACTIVO-CON-APUNTES",
        tipo="L",
        codigo_facturacion="ICA",
        descripcion="Inactivo con apuntes",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        activo=False,
    )

    inactivo_otro_anio = _crear_inmueble_prueba(
        referencia="INACTIVO-OTRO-ANIO",
        tipo="L",
        codigo_facturacion="IOA",
        descripcion="Inactivo con apuntes antiguos",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        activo=False,
    )

    inactivo_con_facturable = _crear_inmueble_prueba(
        referencia="INACTIVO-CON-FACTURABLE",
        tipo="L",
        codigo_facturacion="ICF",
        descripcion="Inactivo con gasto facturable",
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

    apunte_facturable = ApunteContable(
        inmueble=inactivo_con_facturable,
        fecha=date(2026, 4, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Gasto facturable",
        base=12000,
        iva_importe=0,
        retencion_importe=0,
        total=12000,
        tratamiento="FACTURAR",
        nombre_documento="Gasto facturable.pdf",
    )

    session.add_all(
        [
            activo_sin_apuntes,
            inactivo_con_apuntes,
            inactivo_otro_anio,
            inactivo_con_facturable,
            apunte_actual,
            apunte_antiguo,
            apunte_facturable,
        ]
    )
    session.commit()

    # Solicitamos los inmuebles aplicables a 2026.
    seleccionados = (
        seleccionar_inmuebles_exportacion_iva(
            inmuebles=[
                inactivo_otro_anio,
                inactivo_con_apuntes,
                inactivo_con_facturable,
                activo_sin_apuntes,
                inmueble,
            ],
            apuntes=[
                apunte_antiguo,
                apunte_actual,
                apunte_facturable,
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
        "INACTIVO-CON-FACTURABLE",
        "LOCAL-1",
    ]


def test_generar_zip_iva_contiene_un_csv_por_inmueble(
    session,
    inmueble,
) -> None:
    """Genera un ZIP con los CSV de los inmuebles aplicables."""

    # Preparamos otro inmueble con un gasto.
    segundo = _crear_inmueble_prueba(
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


def test_preparar_resumen_anual_iva_clasifica_y_totaliza(
    session,
) -> None:
    """Genera el resumen separando inmuebles facturables del resto."""

    # Creamos un local facturable y un piso sin factura.
    local = _crear_inmueble_prueba(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local comercial",
        direccion="Dirección local",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )
    piso = _crear_inmueble_prueba(
        referencia="PISO-1",
        tipo="P",
        codigo_facturacion="P1",
        descripcion="Piso",
        direccion="Dirección piso",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )
    subdividido_sin_apuntes = _crear_inmueble_prueba(
        referencia="SUBDIVIDIDO-SIN-APUNTES",
        tipo="T",
        codigo_facturacion="SSA",
        descripcion="Subdividido vacío",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )
    subdividido_con_apuntes = _crear_inmueble_prueba(
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
        ApunteContable(
            inmueble=local,
            fecha=date(2026, 3, 1),
            naturaleza="GASTO",
            categoria="GAS_REPARACIONES",
            concepto="Reparación a facturar",
            base=5000,
            iva_importe=1050,
            retencion_importe=0,
            total=6050,
            tratamiento="FACTURAR",
            nombre_documento="Reparación a facturar.pdf",
        ),
    ]

    gasto_repercutido = ApunteContable(
            inmueble=piso,
            fecha=date(2026, 3, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad repercutida",
            base=10000,
            iva_importe=0,
            retencion_importe=0,
            total=10000,
            tratamiento="REPERCUTIR",
            nombre_documento="Comunidad repercutida.pdf",
        )

    imputacion = ImputacionContrato(
        apunte=gasto_repercutido,
        contrato=contrato_piso,
        base=6000,
        iva_importe=0,
        retencion_importe=0,
        importe=6000,
    )

    apuntes=[
        *apuntes,
        gasto_repercutido,
    ]

    session.add_all(
        [
            local,
            piso,
            subdividido_sin_apuntes,
            subdividido_con_apuntes,
            contrato_local,
            contrato_piso,
            imputacion,
            *apuntes,
        ]
    )
    session.commit()


    # Preparamos el resumen anual.
    filas = preparar_resumen_anual_iva(
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

    # El local conserva su retención real.
    # Ingresos: 1.000 €, gastos: 250 €,
    # retención: 190 €, IVA: 210 €.
    assert [
        "LOCAL-1",
        100000,
        25000,
        19000,
        21000,
        56000,
    ] in filas

    # El piso aplica el 25 % sobre ingresos menos gastos.
    # Ingresos: 800 €, gastos: 140 €.
    # Hacienda: (800 - 140) * 25 % = 165 €.
    assert [
        "PISO-1",
        80000,
        14000,
        16500,
        0,
        49500,
    ] in filas

    # Los inmuebles T no aparecen como contabilidad propia.
    referencias = [fila[0] for fila in filas]

    assert "SUBDIVIDIDO-CON-APUNTES" not in referencias
    assert "SUBDIVIDIDO-SIN-APUNTES" not in referencias

    # El resumen conserva ambos grupos y los cuatro trimestres.
    assert "1T - Locales comerciales" in referencias
    assert "1T - Pisos y otros" in referencias

    for trimestre in range(1, 5):
        assert f"Totales {trimestre}T" in referencias

    # Comprobamos los totales del primer trimestre y del año.
    # Ingresos: 1.800 €, gastos: 390 €,
    # retención/Hacienda: 355 €, IVA: 210 €.
    # Neto: 1.800 - 390 - 355 = 1.055 €.
    totales = [
        180000,
        39000,
        35500,
        21000,
        105500,
    ]

    assert ["Totales 1T", *totales] in filas
    assert ["Totales del año 2026", *totales] in filas

    # Se conserva el encabezado del porcentaje seleccionado.
    assert any(
        fila[3] == "Hacienda (25,00%)"
        for fila in filas
    )


def test_generar_csv_iva_resta_apuntes_negativos_de_su_columna(
    session,
    inmueble,
) -> None:
    # El usuario registra un ingreso de 1.000 €.
    ingreso = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler octubre",
        base=100000,
        iva_importe=0,
        retencion_importe=0,
        total=100000,
        tratamiento="CONTABILIZAR",
    )

    # Registra una regularización negativa del ingreso: 100 €.
    ingreso_negativo = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Regularización alquiler",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
        importe_negativo=True,
        tratamiento="CONTABILIZAR",
    )

    # Registra un gasto de comunidad de 200 €.
    gasto = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad octubre",
        base=20000,
        iva_importe=0,
        retencion_importe=0,
        total=20000,
        tratamiento="CONTABILIZAR",
    )

    # La comunidad devuelve 30 € de un cobro anterior.
    gasto_negativo = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Devolución de comunidad",
        base=3000,
        iva_importe=0,
        retencion_importe=0,
        total=3000,
        importe_negativo=True,
        tratamiento="CONTABILIZAR",
    )

    session.add_all([
        ingreso,
        ingreso_negativo,
        gasto,
        gasto_negativo,
    ])
    session.commit()

    # El usuario exporta el informe contable del inmueble.
    contenido = generar_csv_iva(
        inmueble=inmueble,
        apuntes=[
            ingreso,
            ingreso_negativo,
            gasto,
            gasto_negativo,
        ],
        anio=2026,
    )

    filas = list(
        csv.reader(
            StringIO(contenido),
            delimiter=";",
        )
    )

    # La devolución de un ingreso permanece en Ingresos.
    assert [
        "",
        "Regularización alquiler",
        "-100,00",
        "",
        "0,00",
        "0,00",
    ] in filas

    # La devolución de comunidad permanece en Gastos.
    assert [
        "",
        "Devolución de comunidad",
        "",
        "-30,00",
        "",
        "",
    ] in filas

    # El cuarto trimestre presenta los importes netos:
    # ingresos = 1.000 - 100 = 900 €
    # gastos = 200 - 30 = 170 €
    assert [
        "",
        "Totales 4T",
        "900,00",
        "170,00",
        "0,00",
        "0,00",
    ] in filas

    # El resultado económico es 900 - 170 = 730 €.
    assert [
        "",
        "Ingresos netos",
        "730,00",
        "",
        "",
        "",
    ] in filas

    # Como todos los apuntes pertenecen al mismo año,
    # los totales anuales coinciden con los trimestrales.
    assert [
        "",
        "Totales del año",
        "900,00",
        "170,00",
        "0,00",
        "0,00",
    ] in filas


def test_generar_csv_iva_incluye_gasto_facturable(
    session,
    inmueble,
) -> None:
    """Un gasto FACTURAR sigue siendo gasto del propietario."""

    gasto = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 3, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Gasto a facturar",
        base=12000,
        iva_importe=2520,
        retencion_importe=0,
        total=14520,
        tratamiento="FACTURAR",
        nombre_documento="Gasto a facturar.pdf",
    )

    session.add(gasto)
    session.commit()

    contenido = generar_csv_iva(
        inmueble=inmueble,
        apuntes=[gasto],
        anio=2026,
    )

    filas = list(
        csv.reader(
            StringIO(contenido),
            delimiter=";",
        )
    )

    assert [
        "",
        "Gasto a facturar",
        "",
        "120,00",
        "",
        "",
    ] in filas

    assert [
        "",
        "Totales 1T",
        "0,00",
        "120,00",
        "0,00",
        "0,00",
    ] in filas


def test_generar_csv_iva_usa_distribucion_de_inmueble_subdividido(
    session,
) -> None:
    """Un gasto de un T se informa en el local hijo según su distribución."""

    inmueble_total = _crear_inmueble_prueba(
        referencia="TOTAL-1",
        tipo="T",
        codigo_facturacion="T1",
        descripcion="Inmueble subdividido",
        direccion="Dirección total",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    local = _crear_inmueble_prueba(
        inmueble_padre=inmueble_total,
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="LA",
        descripcion="Local A",
        direccion="Dirección local A",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=6000,
    )

    apunte = ApunteContable(
        inmueble=inmueble_total,
        fecha=date(2026, 2, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad general",
        base=10000,
        iva_importe=2100,
        retencion_importe=0,
        total=12100,
        tratamiento="CONTABILIZAR",
        nombre_documento="Comunidad general.pdf",
    )

    distribucion = DistribucionApunte(
        apunte=apunte,
        inmueble=local,
        participacion=6000,
        base=6000,
        iva_importe=1260,
        retencion_importe=0,
        total=7260,
    )

    session.add_all(
        [
            inmueble_total,
            local,
            apunte,
            distribucion,
        ]
    )
    session.commit()

    contenido = generar_csv_iva(
        inmueble=local,
        apuntes=[apunte],
        anio=2026,
    )

    filas = list(
        csv.reader(
            StringIO(contenido),
            delimiter=";",
        )
    )

    assert [
        "",
        "Comunidad general",
        "",
        "60,00",
        "",
        "",
    ] in filas

    assert [
        "",
        "Totales 1T",
        "0,00",
        "60,00",
        "0,00",
        "0,00",
    ] in filas




def test_generar_csv_iva_repercutir_incluye_solo_parte_propietario(
    session,
    inmueble,
    contrato,
) -> None:
    """REPERCUTIR excluye la parte atribuida al contrato."""

    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 3, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad repercutida",
        base=10000,
        iva_importe=2100,
        retencion_importe=0,
        total=12100,
        tratamiento="REPERCUTIR",
        nombre_documento="Comunidad repercutida.pdf",
    )

    imputacion = ImputacionContrato(
        apunte=apunte,
        contrato=contrato,
        base=6000,
        iva_importe=1260,
        retencion_importe=0,
        importe=7260,
    )

    session.add_all(
        [
            apunte,
            imputacion,
        ]
    )
    session.commit()

    contenido = generar_csv_iva(
        inmueble=inmueble,
        apuntes=[apunte],
        anio=2026,
    )

    filas = list(
        csv.reader(
            StringIO(contenido),
            delimiter=";",
        )
    )

    assert [
        "",
        "Comunidad repercutida",
        "",
        "40,00",
        "",
        "",
    ] in filas

    assert [
        "",
        "Totales 1T",
        "0,00",
        "40,00",
        "0,00",
        "0,00",
    ] in filas


def test_generar_csv_iva_repercutir_distribucion_incluye_resto_propietario(
    session,
) -> None:
    """REPERCUTIR sobre un T excluye sólo la parte imputada al contrato."""

    inmueble_total = _crear_inmueble_prueba(
        referencia="TOTAL-1",
        tipo="T",
        codigo_facturacion="T1",
        descripcion="Inmueble subdividido",
        direccion="Dirección total",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    local = _crear_inmueble_prueba(
        inmueble_padre=inmueble_total,
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="LA",
        descripcion="Local A",
        direccion="Dirección local A",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=6000,
    )

    contrato = Contrato(
        inmueble=local,
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

    apunte = ApunteContable(
        inmueble=inmueble_total,
        fecha=date(2026, 2, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad repercutida",
        base=10000,
        iva_importe=2100,
        retencion_importe=0,
        total=12100,
        tratamiento="REPERCUTIR",
        nombre_documento="Comunidad repercutida.pdf",
    )

    distribucion = DistribucionApunte(
        apunte=apunte,
        inmueble=local,
        participacion=6000,
        base=6000,
        iva_importe=1260,
        retencion_importe=0,
        total=7260,
    )

    imputacion = ImputacionContrato(
        distribucion_apunte=distribucion,
        contrato=contrato,
        base=4000,
        iva_importe=840,
        retencion_importe=0,
        importe=4840,
    )

    session.add_all(
        [
            inmueble_total,
            local,
            contrato,
            apunte,
            distribucion,
            imputacion,
        ]
    )
    session.commit()

    contenido = generar_csv_iva(
        inmueble=local,
        apuntes=[apunte],
        anio=2026,
    )

    filas = list(
        csv.reader(
            StringIO(contenido),
            delimiter=";",
        )
    )

    assert [
        "",
        "Comunidad repercutida",
        "",
        "20,00",
        "",
        "",
    ] in filas

    assert [
        "",
        "Totales 1T",
        "0,00",
        "20,00",
        "0,00",
        "0,00",
    ] in filas


def test_preparar_resumen_anual_iva_usa_distribucion_de_inmueble_subdividido(
    session,
) -> None:
    """El resumen atribuye al local hijo los gastos distribuidos de un T."""

    inmueble_total = _crear_inmueble_prueba(
        referencia="TOTAL-1",
        tipo="T",
        codigo_facturacion="T1",
        descripcion="Inmueble subdividido",
        direccion="Dirección total",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    local = _crear_inmueble_prueba(
        inmueble_padre=inmueble_total,
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="LA",
        descripcion="Local A",
        direccion="Dirección local A",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=6000,
    )

    contrato = Contrato(
        inmueble=local,
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

    apunte = ApunteContable(
        inmueble=inmueble_total,
        fecha=date(2026, 2, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad general",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
        tratamiento="CONTABILIZAR",
        nombre_documento="Comunidad general.pdf",
    )

    distribucion = DistribucionApunte(
        apunte=apunte,
        inmueble=local,
        participacion=6000,
        base=6000,
        iva_importe=0,
        retencion_importe=0,
        total=6000,
    )

    session.add_all(
        [
            inmueble_total,
            local,
            contrato,
            apunte,
            distribucion,
        ]
    )
    session.commit()


    filas = preparar_resumen_anual_iva(
        inmuebles=[inmueble_total, local],
        contratos=[contrato],
        apuntes=[apunte],
        anio=2026,
        porcentaje_irpf_estimado=2500,
    )

    # El gasto del inmueble T se atribuye al local hijo
    # según su distribución persistida: 100 * 60 % = 60 €.
    assert [
        "LOCAL-A",
        0,
        6000,
        0,
        0,
        -6000,
    ] in filas

    # El inmueble contenedor no aparece como contabilidad propia.
    assert all(
        fila[0] != "TOTAL-1"
        for fila in filas
    )


def test_preparar_resumen_anual_iva_repercutir_distribucion_incluye_resto_propietario(
    session,
) -> None:
    """El resumen excluye de una distribución sólo la parte repercutida."""

    inmueble_total = _crear_inmueble_prueba(
        referencia="TOTAL-1",
        tipo="T",
        codigo_facturacion="T1",
        descripcion="Inmueble subdividido",
        direccion="Dirección total",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    local = _crear_inmueble_prueba(
        inmueble_padre=inmueble_total,
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="LA",
        descripcion="Local A",
        direccion="Dirección local A",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=6000,
    )

    contrato = Contrato(
        inmueble=local,
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

    apunte = ApunteContable(
        inmueble=inmueble_total,
        fecha=date(2026, 2, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad repercutida",
        base=10000,
        iva_importe=2100,
        retencion_importe=0,
        total=12100,
        tratamiento="REPERCUTIR",
        nombre_documento="Comunidad repercutida.pdf",
    )

    distribucion = DistribucionApunte(
        apunte=apunte,
        inmueble=local,
        participacion=6000,
        base=6000,
        iva_importe=1260,
        retencion_importe=0,
        total=7260,
    )

    imputacion = ImputacionContrato(
        distribucion_apunte=distribucion,
        contrato=contrato,
        base=4000,
        iva_importe=840,
        retencion_importe=0,
        importe=4840,
    )

    session.add_all(
        [
            inmueble_total,
            local,
            contrato,
            apunte,
            distribucion,
            imputacion,
        ]
    )
    session.commit()


    filas = preparar_resumen_anual_iva(
        inmuebles=[inmueble_total, local],
        contratos=[contrato],
        apuntes=[apunte],
        anio=2026,
        porcentaje_irpf_estimado=2500,
    )

    # El local recibe 60 € del gasto del inmueble T.
    # De ellos, 40 € se imputaron al contrato.
    # Los 20 € restantes son gasto del propietario.
    assert [
        "LOCAL-A",
        0,
        2000,
        0,
        0,
        -2000,
    ] in filas

    assert all(
        fila[0] != "TOTAL-1"
        for fila in filas
    )


def test_preparar_resumen_anual_iva_repercutir_distribucion_completa_deja_gasto_cero(
    session,
) -> None:
    """Una distribución totalmente repercutida no deja gasto al propietario."""

    inmueble_total = _crear_inmueble_prueba(
        referencia="TOTAL-1",
        tipo="T",
        codigo_facturacion="T1",
        descripcion="Inmueble subdividido",
        direccion="Dirección total",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    local = _crear_inmueble_prueba(
        inmueble_padre=inmueble_total,
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="LA",
        descripcion="Local A",
        direccion="Dirección local A",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=6000,
    )

    contrato = Contrato(
        inmueble=local,
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

    apunte = ApunteContable(
        inmueble=inmueble_total,
        fecha=date(2026, 2, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad repercutida",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
        tratamiento="REPERCUTIR",
        nombre_documento="Comunidad repercutida.pdf",
    )

    distribucion = DistribucionApunte(
        apunte=apunte,
        inmueble=local,
        participacion=6000,
        base=6000,
        iva_importe=0,
        retencion_importe=0,
        total=6000,
    )

    imputacion = ImputacionContrato(
        distribucion_apunte=distribucion,
        contrato=contrato,
        base=6000,
        iva_importe=0,
        retencion_importe=0,
        importe=6000,
    )

    session.add_all(
        [
            inmueble_total,
            local,
            contrato,
            apunte,
            distribucion,
            imputacion,
        ]
    )
    session.commit()


    filas = preparar_resumen_anual_iva(
        inmuebles=[inmueble_total, local],
        contratos=[contrato],
        apuntes=[apunte],
        anio=2026,
        porcentaje_irpf_estimado=2500,
    )

    # Los 60 € distribuidos al local se han imputado
    # íntegramente al contrato.
    # No queda ningún gasto para el propietario.
    assert [
        "LOCAL-A",
        0,
        0,
        0,
        0,
        0,
    ] in filas

    assert all(
        fila[0] != "TOTAL-1"
        for fila in filas
    )


def test_preparar_resumen_anual_iva_descuenta_importes_negativos(
    session,
    inmueble,
    contrato,
) -> None:
    # El usuario contabiliza un alquiler de 1.000 €.
    ingreso = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler octubre",
        base=100000,
        iva_importe=21000,
        retencion_importe=19000,
        total=102000,
        tratamiento="CONTABILIZAR",
    )

    # Registra una reducción del ingreso de 100 €.
    ingreso_negativo = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Regularización alquiler",
        base=10000,
        iva_importe=2100,
        retencion_importe=1900,
        total=10200,
        importe_negativo=True,
        tratamiento="CONTABILIZAR",
    )

    # Registra un gasto de comunidad de 200 €.
    gasto = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad octubre",
        base=20000,
        iva_importe=0,
        retencion_importe=0,
        total=20000,
        tratamiento="CONTABILIZAR",
    )

    # La comunidad devuelve 30 €.
    gasto_negativo = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Devolución de comunidad",
        base=3000,
        iva_importe=0,
        retencion_importe=0,
        total=3000,
        importe_negativo=True,
        tratamiento="CONTABILIZAR",
    )

    session.add_all([
        ingreso,
        ingreso_negativo,
        gasto,
        gasto_negativo,
    ])
    session.commit()


    filas = preparar_resumen_anual_iva(
        inmuebles=[inmueble],
        contratos=[contrato],
        apuntes=[
            ingreso,
            ingreso_negativo,
            gasto,
            gasto_negativo,
        ],
        anio=2026,
        porcentaje_irpf_estimado=1900,
    )

    # Cuarto trimestre:
    # Ingresos: 1.000 - 100 = 900 €
    # Gastos: 200 - 30 = 170 €
    # Retención: 190 - 19 = 171 €
    # IVA: 210 - 21 = 189 €
    # Neto: 900 - 170 - 171 = 559 €.
    fila_esperada = [
        inmueble.referencia,
        90000,
        17000,
        17100,
        18900,
        55900,
    ]

    assert fila_esperada in filas

    # Los importes acumulados del cuarto trimestre
    # coinciden con el total anual.
    assert [
        "Totales 4T",
        90000,
        17000,
        17100,
        18900,
        55900,
    ] in filas

    assert [
        "Totales del año 2026",
        90000,
        17000,
        17100,
        18900,
        55900,
    ] in filas


def test_preparar_resumen_anual_iva_sin_apuntes():
    """El resumen conserva cuatro trimestres vacíos."""

    filas = preparar_resumen_anual_iva(
        inmuebles=[],
        contratos=[],
        apuntes=[],
        anio=2026,
        porcentaje_irpf_estimado=2400,
    )

    assert filas[0][0] == "Resumen del año 2026"

    for trimestre in range(1, 5):
        assert any(
            fila[0] == f"Totales {trimestre}T"
            and fila[1:] == [0, 0, 0, 0, 0]
            for fila in filas
        )

    assert [
        "Totales del año 2026",
        0,
        0,
        0,
        0,
        0,
    ] == filas[-1]


def test_hacienda_estimada_descontando_gastos():
    """Calcula Hacienda sobre ingresos menos gastos."""

    impuesto = importe_irpf_estimado(
        ingresos=595000,
        gastos=315011,
        retencion=0,
        porcentaje_estimado=5000,
        descontar_gastos=True,
        solo_retencion_real=False,
    )

    assert impuesto == 139995


def test_hacienda_estimada_sobre_bruto():
    """Permite calcular Hacienda sin descontar gastos."""

    impuesto = importe_irpf_estimado(
        ingresos=595000,
        gastos=315011,
        retencion=0,
        porcentaje_estimado=5000,
        descontar_gastos=False,
        solo_retencion_real=False,
    )

    assert impuesto == 297500


def test_hacienda_estimada_no_puede_ser_negativa():
    """Los gastos superiores a los ingresos dan base cero."""

    impuesto = importe_irpf_estimado(
        ingresos=10000,
        gastos=20000,
        retencion=0,
        porcentaje_estimado=5000,
        descontar_gastos=True,
        solo_retencion_real=False,
    )

    assert impuesto == 0


def test_local_conserva_retencion_real():
    """La retención del local no depende de la estimación."""

    for descontar_gastos in (True, False):
        impuesto = importe_irpf_estimado(
            ingresos=100000,
            gastos=20000,
            retencion=19000,
            porcentaje_estimado=5000,
            descontar_gastos=descontar_gastos,
            solo_retencion_real=True,
        )

        assert impuesto == 19000


def test_local_sin_retencion_no_recibe_estimacion():
    """Un local con retención cero mantiene ese importe."""

    for descontar_gastos in (True, False):
        impuesto = importe_irpf_estimado(
            ingresos=100000,
            gastos=20000,
            retencion=0,
            porcentaje_estimado=5000,
            descontar_gastos=descontar_gastos,
            solo_retencion_real=True,
        )

        assert impuesto == 0


def test_ingresos_gastos_anuales_categorias_y_totales(
    session,
    inmueble,
) -> None:
    categorias = {
        codigo: CategoriaContable(
            codigo=codigo,
            naturaleza=naturaleza,
            nombre=nombre,
            activa=True,
            subcategorias=(),
        )
        for codigo, naturaleza, nombre in (
            ("ING_ALQUILERES", "INGRESO", "Alquileres"),
            ("GAS_SEGUROS", "GASTO", "Seguros"),
            ("GAS_COMUNIDAD", "GASTO", "Comunidad"),
        )
    }

    ingreso = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 1, 5),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler enero",
        base=100000,
        iva_importe=21000,
        retencion_importe=19000,
        total=102000,
        tratamiento="CONTABILIZAR",
        nombre_documento="Factura.pdf",
    )

    gasto = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 4, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad abril",
        base=20000,
        iva_importe=0,
        retencion_importe=0,
        total=20000,
        tratamiento="CONTABILIZAR",
        nombre_documento="Comunidad.pdf",
    )

    session.add_all([ingreso, gasto])
    session.commit()

    informe = preparar_ingresos_gastos_anuales(
        inmueble=inmueble,
        apuntes=[gasto, ingreso],
        categorias=categorias,
        anio=2026,
    )

    assert informe["categorias_gasto"] == (
        ("GAS_SEGUROS", "Seguros"),
        ("GAS_COMUNIDAD", "Comunidad"),
    )

    primer_trimestre = informe["trimestres"][0]
    segundo_trimestre = informe["trimestres"][1]

    assert primer_trimestre["filas"][0]["concepto"] == "Alquiler enero"
    assert primer_trimestre["totales"]["ingresos"] == 100000
    assert primer_trimestre["totales"]["iva"] == 21000
    assert primer_trimestre["totales"]["retencion"] == 19000

    assert segundo_trimestre["filas"][0]["concepto"] == "Comunidad abril"
    assert segundo_trimestre["totales"]["gastos"]["GAS_COMUNIDAD"] == 20000
    assert segundo_trimestre["totales"]["gastos"]["GAS_SEGUROS"] == 0

    assert informe["totales_anuales"]["ingresos"] == 100000
    assert informe["totales_anuales"]["total_gastos"] == 20000
    assert len(informe["trimestres"]) == 4


def test_ingresos_gastos_anuales_usa_distribucion_ingreso(
    session,
) -> None:
    padre = _crear_inmueble_prueba(
        referencia="EDIFICIO",
        tipo="T",
        codigo_facturacion="ED",
        descripcion="Edificio",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    hijo = _crear_inmueble_prueba(
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="LA",
        descripcion="Local A",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        inmueble_padre=padre,
        participacion=4000,
    )

    ingreso = ApunteContable(
        inmueble=padre,
        fecha=date(2026, 2, 15),
        naturaleza="INGRESO",
        categoria="ING_OTRAS_RENTAS",
        concepto="Antena de telefonía",
        base=100000,
        iva_importe=21000,
        retencion_importe=0,
        total=121000,
        tratamiento="CONTABILIZAR",
        nombre_documento="Antena.pdf",
    )

    distribucion = DistribucionApunte(
        apunte=ingreso,
        inmueble=hijo,
        participacion=4000,
        base=40000,
        iva_importe=8400,
        retencion_importe=0,
        total=48400,
    )

    session.add_all([padre, hijo, ingreso, distribucion])
    session.commit()

    categorias = {
        "ING_OTRAS_RENTAS": CategoriaContable(
            codigo="ING_OTRAS_RENTAS",
            naturaleza="INGRESO",
            nombre="Otras rentas",
            activa=True,
            subcategorias=(),
        )
    }

    informe_padre = preparar_ingresos_gastos_anuales(
        inmueble=padre,
        apuntes=[ingreso],
        categorias=categorias,
        anio=2026,
    )

    informe_hijo = preparar_ingresos_gastos_anuales(
        inmueble=hijo,
        apuntes=[ingreso],
        categorias=categorias,
        anio=2026,
    )

    assert informe_padre["totales_anuales"]["ingresos"] == 100000
    assert informe_padre["totales_anuales"]["iva"] == 21000

    assert informe_hijo["totales_anuales"]["ingresos"] == 40000
    assert informe_hijo["totales_anuales"]["iva"] == 8400

    assert len(informe_hijo["trimestres"][0]["filas"]) == 1


def test_ingresos_gastos_anuales_tratamientos_y_negativos(
    session,
    inmueble,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="De comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_vencimiento=date(2026, 12, 31),
        genera_factura=False,
        fecha_inicio_facturacion=date(2026, 1, 1),
        fianza=0,
        direccion_facturacion="",
        poblacion_facturacion="",
        provincia_facturacion="",
        concepto_factura="",
    )

    repercutido = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 1, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad repercutida",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
        tratamiento="REPERCUTIR",
        nombre_documento="Comunidad.pdf",
    )

    imputacion = ImputacionContrato(
        apunte=repercutido,
        contrato=contrato,
        base=6000,
        iva_importe=0,
        retencion_importe=0,
        importe=6000,
    )

    facturable = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 2, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Gasto facturable",
        base=10000,
        iva_importe=0,
        retencion_importe=0,
        total=10000,
        tratamiento="FACTURAR",
        nombre_documento="Facturable.pdf",
    )

    negativo = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 3, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Abono comunidad",
        base=2000,
        iva_importe=0,
        retencion_importe=0,
        total=2000,
        tratamiento="CONTABILIZAR",
        importe_negativo=True,
        nombre_documento="Abono.pdf",
    )

    session.add_all([
        contrato,
        repercutido,
        imputacion,
        facturable,
        negativo,
    ])
    session.commit()

    informe = preparar_ingresos_gastos_anuales(
        inmueble=inmueble,
        apuntes=[negativo, facturable, repercutido],
        categorias=categorias,
        anio=2026,
    )

    filas = informe["trimestres"][0]["filas"]

    assert [fila["concepto"] for fila in filas] == [
        "Comunidad repercutida",
        "Gasto facturable",
        "Abono comunidad",
    ]

    assert [
        fila["gastos"]["GAS_COMUNIDAD"]
        for fila in filas
    ] == [
        4000,    # 100,00 - 60,00 del inquilino
        10000,   # Gasto facturable completo
        -2000,   # Abono que reduce el gasto
    ]

    assert informe["trimestres"][0]["totales"]["total_gastos"] == 12000
    assert informe["totales_anuales"]["total_gastos"] == 12000


def test_ingresos_gastos_anuales_gastos_distribuidos(
    session,
) -> None:
    padre = _crear_inmueble_prueba(
        referencia="EDIFICIO",
        tipo="T",
        codigo_facturacion="ED",
        descripcion="Edificio",
        direccion="Dirección edificio",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    hijo = _crear_inmueble_prueba(
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="LA",
        descripcion="Local A",
        direccion="Dirección local",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        inmueble_padre=padre,
        participacion=4000,
    )

    contrato = Contrato(
        inmueble=hijo,
        fecha_inicio=date(2026, 1, 1),
        fecha_vencimiento=date(2026, 12, 31),
        genera_factura=False,
        fecha_inicio_facturacion=date(2026, 1, 1),
        fianza=0,
        direccion_facturacion="",
        poblacion_facturacion="",
        provincia_facturacion="",
        concepto_factura="",
    )

    gasto_comun = ApunteContable(
        inmueble=padre,
        fecha=date(2026, 4, 10),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad edificio",
        base=30000,
        iva_importe=0,
        retencion_importe=0,
        total=30000,
        tratamiento="CONTABILIZAR",
        nombre_documento="Comunidad.pdf",
    )

    distribucion_comun = DistribucionApunte(
        apunte=gasto_comun,
        inmueble=hijo,
        participacion=4000,
        base=12000,
        iva_importe=0,
        retencion_importe=0,
        total=12000,
    )

    gasto_repercutido = ApunteContable(
        inmueble=padre,
        fecha=date(2026, 5, 10),
        naturaleza="GASTO",
        categoria="GAS_TRIBUTOS",
        concepto="Tributo edificio",
        base=20000,
        iva_importe=0,
        retencion_importe=0,
        total=20000,
        tratamiento="REPERCUTIR",
        nombre_documento="Tributo.pdf",
    )

    distribucion_repercutida = DistribucionApunte(
        apunte=gasto_repercutido,
        inmueble=hijo,
        participacion=4000,
        base=8000,
        iva_importe=0,
        retencion_importe=0,
        total=8000,
    )

    imputacion = ImputacionContrato(
        distribucion_apunte=distribucion_repercutida,
        contrato=contrato,
        base=5000,
        iva_importe=0,
        retencion_importe=0,
        importe=5000,
    )

    session.add_all([
        padre,
        hijo,
        contrato,
        gasto_comun,
        distribucion_comun,
        gasto_repercutido,
        distribucion_repercutida,
        imputacion,
    ])
    session.commit()

    categorias = {
        codigo: CategoriaContable(
            codigo=codigo,
            naturaleza="GASTO",
            nombre=nombre,
            activa=True,
            subcategorias=(),
        )
        for codigo, nombre in (
            ("GAS_COMUNIDAD", "De comunidad"),
            ("GAS_TRIBUTOS", "Tributos"),
        )
    }

    apuntes = [gasto_repercutido, gasto_comun]

    informe_padre = preparar_ingresos_gastos_anuales(
        inmueble=padre,
        apuntes=apuntes,
        categorias=categorias,
        anio=2026,
    )

    informe_hijo = preparar_ingresos_gastos_anuales(
        inmueble=hijo,
        apuntes=apuntes,
        categorias=categorias,
        anio=2026,
    )

    # El edificio muestra sus gastos propios completos.
    gastos_padre = informe_padre["trimestres"][1]["totales"]["gastos"]

    assert gastos_padre["GAS_COMUNIDAD"] == 30000
    assert gastos_padre["GAS_TRIBUTOS"] == 20000

    # El local usa las distribuciones persistidas.
    gastos_hijo = informe_hijo["trimestres"][1]["totales"]["gastos"]

    assert gastos_hijo["GAS_COMUNIDAD"] == 12000

    # De los 80 € distribuidos, 50 € corresponden
    # al inquilino. El propietario soporta 30 €.
    assert gastos_hijo["GAS_TRIBUTOS"] == 3000

    assert informe_hijo["trimestres"][1]["totales"]["total_gastos"] == 15000

    assert [
        fila["concepto"]
        for fila in informe_hijo["trimestres"][1]["filas"]
    ] == [
        "Comunidad edificio",
        "Tributo edificio",
    ]


def test_ingresos_gastos_anuales_omite_repercutidos_sin_parte_propietario(
    session,
    inmueble,
) -> None:
    categorias = {
        "GAS_SERVICIOS_SUMINISTROS": CategoriaContable(
            codigo="GAS_SERVICIOS_SUMINISTROS",
            naturaleza="GASTO",
            nombre="Por servicios y suministros",
            activa=True,
            subcategorias=(),
        ),
    }

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_vencimiento=date(2026, 12, 31),
        genera_factura=False,
        fecha_inicio_facturacion=date(2026, 1, 1),
        fianza=0,
        direccion_facturacion="",
        poblacion_facturacion="",
        provincia_facturacion="",
        concepto_factura="",
    )

    gasto = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 3, 10),
        naturaleza="GASTO",
        categoria="GAS_SERVICIOS_SUMINISTROS",
        concepto="Agua totalmente repercutida",
        base=9000,
        iva_importe=0,
        retencion_importe=0,
        total=9000,
        tratamiento="REPERCUTIR",
        nombre_documento="Agua.pdf",
    )

    imputacion = ImputacionContrato(
        apunte=gasto,
        contrato=contrato,
        base=9000,
        iva_importe=0,
        retencion_importe=0,
        importe=9000,
    )

    session.add_all([contrato, gasto, imputacion])
    session.commit()

    informe = preparar_ingresos_gastos_anuales(
        inmueble=inmueble,
        apuntes=[gasto],
        categorias=categorias,
        anio=2026,
    )

    assert informe["trimestres"][0]["filas"] == []
    assert informe["trimestres"][0]["totales"]["total_gastos"] == 0
    assert informe["totales_anuales"]["total_gastos"] == 0


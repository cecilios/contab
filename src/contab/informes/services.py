"""Servicios para generar informes y exportaciones."""

import csv
from datetime import date
from collections.abc import Sequence
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile

from werkzeug.utils import secure_filename
from contab.models import (
    ApunteContable,
    Contrato,
    Inmueble,
)


def _importe_irpf_estimado(
    *,
    ingresos: int,
    retencion: int,
    porcentaje_estimado: int,
) -> int:
    """Devuelve la retención real o estima el IRPF cuando no existe."""
    if retencion:
        return retencion

    return (
        ingresos * porcentaje_estimado + 5000
    ) // 10000


def _importe_neto_estimado(
    *,
    ingresos: int,
    gastos: int,
    iva: int,
    retencion: int,
    porcentaje_estimado: int,
) -> int:
    """Calcula el ingreso neto después de gastos e impuestos."""
    impuesto = _importe_irpf_estimado(
        ingresos=ingresos,
        retencion=retencion,
        porcentaje_estimado=porcentaje_estimado,
    )

    return ingresos - gastos - iva - impuesto


def _inmueble_genera_factura(
    *,
    inmueble: Inmueble,
    contratos: Sequence[Contrato],
) -> bool:
    """Indica si el inmueble tiene algún contrato facturable."""
    return any(
        contrato.inmueble_id == inmueble.id
        and contrato.genera_factura
        for contrato in contratos
    )


def _totales_inmueble_trimestre(
    *,
    inmueble: Inmueble,
    apuntes: Sequence[ApunteContable],
    anio: int,
    trimestre: int,
    porcentaje_irpf_estimado: int,
) -> tuple[int, int, int, int, int]:
    """Calcula ingresos, gastos, impuesto, IVA y neto de un trimestre."""
    apuntes_aplicables = [
        apunte
        for apunte in apuntes
        if apunte.inmueble_id == inmueble.id
        and apunte.fecha.year == anio
        and (apunte.fecha.month - 1) // 3 + 1
        == trimestre
        and apunte.tratamiento == "CONTABILIZAR"
    ]

    ingresos = sum(
        apunte.base
        for apunte in apuntes_aplicables
        if apunte.naturaleza == "INGRESO"
    )
    gastos = sum(
        apunte.base
        for apunte in apuntes_aplicables
        if apunte.naturaleza == "GASTO"
    )
    iva = sum(
        apunte.iva_importe
        for apunte in apuntes_aplicables
        if apunte.naturaleza == "INGRESO"
    )
    retencion = sum(
        apunte.retencion_importe
        for apunte in apuntes_aplicables
        if apunte.naturaleza == "INGRESO"
    )

    impuesto = _importe_irpf_estimado(
        ingresos=ingresos,
        retencion=retencion,
        porcentaje_estimado=(
            porcentaje_irpf_estimado
        ),
    )

    neto = _importe_neto_estimado(
        ingresos=ingresos,
        gastos=gastos,
        iva=iva,
        retencion=retencion,
        porcentaje_estimado=(
            porcentaje_irpf_estimado
        ),
    )

    return ingresos, gastos, impuesto, iva, neto


def _formatear_importe(centimos: int) -> str:
    """Convierte un importe en céntimos al formato numérico español."""
    importe = f"{centimos / 100:,.2f}"

    return importe.translate(
        str.maketrans(
            {
                ",": ".",
                ".": ",",
            }
        )
    )


def _fila_vacia() -> list[str]:
    """Devuelve una fila vacía con las seis columnas del informe."""
    return ["", "", "", "", "", ""]


def seleccionar_inmuebles_exportacion_iva(
    *,
    inmuebles: Sequence[Inmueble],
    apuntes: Sequence[ApunteContable],
    anio: int,
) -> list[Inmueble]:
    """Selecciona los inmuebles que deben incluirse en la exportación conjunta.

    - Incluye todos los inmuebles activos.
    - Incluye los inmuebles inactivos que tengan algún apunte
      CONTABILIZAR durante el año solicitado.
    - Excluye los inmuebles inactivos sin apuntes aplicables.
    - Devuelve los inmuebles ordenados por referencia.
    """
    inmuebles_con_apuntes = {
        apunte.inmueble_id
        for apunte in apuntes
        if apunte.fecha.year == anio
        and apunte.tratamiento == "CONTABILIZAR"
    }

    return sorted(
        (
            inmueble
            for inmueble in inmuebles
            if inmueble.id in inmuebles_con_apuntes
            or (
                inmueble.activo
                and inmueble.tipo != "T"
            )
        ),
        key=lambda inmueble: (
            inmueble.referencia.casefold()
        ),
    )


def generar_csv_iva(
    *,
    inmueble: Inmueble,
    apuntes: Sequence[ApunteContable],
    anio: int,
) -> str:
    """Genera el CSV anual de un inmueble orientado a la declaración del IVA.

    - Selecciona los apuntes del inmueble y año indicados.
    - Incluye únicamente los de tratamiento CONTABILIZAR.
    - Los separa en cuatro trimestres.
    - Los ordena por fecha e identificador.
    - Genera los cuatro bloques, incluso cuando estén vacíos.
    - Calcula los totales trimestrales y anuales.
    - Calcula los ingresos netos como ingresos menos gastos.
    - Muestra IVA y retención únicamente para los ingresos.
    - No traslada al informe el IVA soportado de los gastos.
    - Utiliza punto y coma como separador y coma decimal.
    - Genera valores calculados, no fórmulas.
    """
    apuntes_seleccionados = sorted(
        (
            apunte
            for apunte in apuntes
            if apunte.inmueble_id == inmueble.id
            and apunte.fecha.year == anio
            and apunte.tratamiento == "CONTABILIZAR"
        ),
        key=lambda apunte: (
            apunte.fecha,
            apunte.id or 0,
        ),
    )

    filas: list[list[str]] = [
        [
            inmueble.direccion,
            "",
            "",
            "",
            "",
            inmueble.referencia,
        ],
        _fila_vacia(),
        _fila_vacia(),
    ]

    total_anual_ingresos = 0
    total_anual_gastos = 0
    total_anual_iva = 0
    total_anual_retencion = 0

    for trimestre in range(1, 5):
        filas.append(
            [
                "",
                f"{trimestre}T",
                "Ingresos",
                "Gastos",
                "IVA",
                "Retención",
            ]
        )

        apuntes_trimestre = [
            apunte
            for apunte in apuntes_seleccionados
            if (apunte.fecha.month - 1) // 3 + 1
            == trimestre
        ]

        ingresos = 0
        gastos = 0
        iva = 0
        retencion = 0

        for apunte in apuntes_trimestre:
            if apunte.naturaleza == "INGRESO":
                ingresos += apunte.base
                iva += apunte.iva_importe
                retencion += apunte.retencion_importe

                filas.append(
                    [
                        "",
                        apunte.concepto,
                        _formatear_importe(apunte.base),
                        "",
                        _formatear_importe(
                            apunte.iva_importe
                        ),
                        _formatear_importe(
                            apunte.retencion_importe
                        ),
                    ]
                )

            else:
                gastos += apunte.base

                filas.append(
                    [
                        "",
                        apunte.concepto,
                        "",
                        _formatear_importe(apunte.base),
                        "",
                        "",
                    ]
                )

        total_anual_ingresos += ingresos
        total_anual_gastos += gastos
        total_anual_iva += iva
        total_anual_retencion += retencion

        if not apuntes_trimestre:
            filas.append(_fila_vacia())

        filas.append(
            [
                "",
                f"Totales {trimestre}T",
                _formatear_importe(ingresos),
                _formatear_importe(gastos),
                _formatear_importe(iva),
                _formatear_importe(retencion),
            ]
        )
        filas.append(
            [
                "",
                "Ingresos netos",
                _formatear_importe(
                    ingresos - gastos
                ),
                "",
                "",
                "",
            ]
        )
        filas.append(
            [
                "",
                "IVA (21%)",
                _formatear_importe(
                    (ingresos * 21 + 50) // 100
                ),
                "",
                "",
                "",
            ]
        )
        filas.append(_fila_vacia())

    filas.append(
        [
            "",
            "Año",
            "Ingresos",
            "Gastos",
            "IVA",
            "Retención",
        ]
    )
    filas.append(
        [
            "",
            "Totales del año",
            _formatear_importe(total_anual_ingresos),
            _formatear_importe(total_anual_gastos),
            _formatear_importe(total_anual_iva),
            _formatear_importe(total_anual_retencion),
        ]
    )
    filas.append(
        [
            "",
            "Ingresos netos",
            _formatear_importe(
                total_anual_ingresos
                - total_anual_gastos
            ),
            "",
            "",
            "",
        ]
    )
    filas.append(
        [
            "",
            "IVA (21%)",
            _formatear_importe(
                (total_anual_ingresos * 21 + 50)
                // 100
            ),
            "",
            "",
            "",
        ]
    )

    salida = StringIO(newline="")
    escritor = csv.writer(
        salida,
        delimiter=";",
        quotechar='"',
        lineterminator="\n",
    )
    escritor.writerows(filas)

    return salida.getvalue()


def generar_csv_resumen_iva(
    *,
    inmuebles: Sequence[Inmueble],
    contratos: Sequence[Contrato],
    apuntes: Sequence[ApunteContable],
    anio: int,
    porcentaje_irpf_estimado: int,
) -> str:
    """Genera el resumen anual de IVA de todos los inmuebles aplicables.
        - Incluye todos los inmuebles activos.
        - Incluye los inactivos con apuntes CONTABILIZAR en el año.
        - Genera cuatro bloques trimestrales.
        - Separa los contratos facturables de los pisos y otros.
        - Calcula ingresos, gastos, retención o IRPF estimado, IVA y neto.
        - Utiliza la retención registrada cuando existe.
        - Estima el IRPF al 24 % cuando no existe retención.
        - Calcula totales trimestrales y anuales.
        - Utiliza punto y coma como separador y coma decimal.
        - Genera valores calculados, no fórmulas.
    """
    seleccionados = seleccionar_inmuebles_exportacion_iva(
        inmuebles=inmuebles,
        apuntes=apuntes,
        anio=anio,
    )

    filas: list[list[str]] = [
        [
            f"Resumen del año {anio}",
            "",
            "",
            "",
            "",
            "",
        ],
        _fila_vacia(),
        [
            "Notas:",
            "Neto significa Ingr. Bruto - Gastos "
            "- Retención/Hacienda - IVA",
            "",
            "",
            "",
            "",
        ],
        _fila_vacia(),
    ]

    totales_anuales = [0, 0, 0, 0, 0]

    for trimestre in range(1, 5):
        grupos = [
            (
                "Locales comerciales",
                [
                    inmueble
                    for inmueble in seleccionados
                        if _inmueble_genera_factura(
                            inmueble=inmueble,
                            contratos=contratos,
                        )
                ],
                "Retención",
            ),
            (
                "Pisos y otros",
                [
                    inmueble
                    for inmueble in seleccionados
                        if not _inmueble_genera_factura(
                            inmueble=inmueble,
                            contratos=contratos,
                        )
                ],
                f"Hacienda ({_formatear_importe(porcentaje_irpf_estimado)}%)",
            ),
        ]

        totales_trimestre = [0, 0, 0, 0, 0]

        for nombre_grupo, inmuebles_grupo, literal_impuesto in grupos:
            filas.append(
                [
                    f"{trimestre}T - {nombre_grupo}",
                    "Ingr. Bruto",
                    "Gastos",
                    literal_impuesto,
                    "IVA",
                    "Neto",
                ]
            )

            totales_grupo = [0, 0, 0, 0, 0]

            for inmueble in inmuebles_grupo:
                totales = _totales_inmueble_trimestre(
                    inmueble=inmueble,
                    apuntes=apuntes,
                    anio=anio,
                    trimestre=trimestre,
                    porcentaje_irpf_estimado=(
                        porcentaje_irpf_estimado
                    ),
                )

                filas.append(
                    [
                        inmueble.referencia,
                        *[
                            _formatear_importe(importe)
                            for importe in totales
                        ],
                    ]
                )

                for posicion, importe in enumerate(totales):
                    totales_grupo[posicion] += importe
                    totales_trimestre[posicion] += importe
                    totales_anuales[posicion] += importe

            filas.append(
                [
                    f"Totales {nombre_grupo}",
                    *[
                        _formatear_importe(importe)
                        for importe in totales_grupo
                    ],
                ]
            )
            filas.append(_fila_vacia())

        filas.append(
            [
                f"Totales {trimestre}T",
                *[
                    _formatear_importe(importe)
                    for importe in totales_trimestre
                ],
            ]
        )
        filas.append(_fila_vacia())

    filas.append(
        [
            f"Totales del año {anio}",
            *[
                _formatear_importe(importe)
                for importe in totales_anuales
            ],
        ]
    )

    salida = StringIO(newline="")
    escritor = csv.writer(
        salida,
        delimiter=";",
        quotechar='"',
        lineterminator="\n",
    )
    escritor.writerows(filas)

    return salida.getvalue()


def generar_zip_iva(
    *,
    inmuebles: Sequence[Inmueble],
    apuntes: Sequence[ApunteContable],
    anio: int,
) -> bytes:
    """Genera un ZIP con un CSV anual por cada inmueble aplicable.
        - Incluye todos los inmuebles activos.
        - Incluye los inactivos con apuntes CONTABILIZAR en el año.
        - Genera cada CSV mediante generar_csv_iva.
        - Utiliza la referencia del inmueble en el nombre del archivo.
        - Devuelve el contenido completo del ZIP en memoria.
    """
    seleccionados = (
        seleccionar_inmuebles_exportacion_iva(
            inmuebles=inmuebles,
            apuntes=apuntes,
            anio=anio,
        )
    )

    salida = BytesIO()

    with ZipFile(
        salida,
        mode="w",
        compression=ZIP_DEFLATED,
    ) as archivo:
        for inmueble in seleccionados:
            referencia = (
                secure_filename(inmueble.referencia)
                or f"inmueble-{inmueble.id}"
            )
            nombre = (
                f"iva-{referencia}-{anio}.csv"
            )

            contenido = generar_csv_iva(
                inmueble=inmueble,
                apuntes=apuntes,
                anio=anio,
            )

            archivo.writestr(
                nombre,
                contenido.encode("utf-8"),
            )

    return salida.getvalue()



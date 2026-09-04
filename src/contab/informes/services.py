"""Servicios para generar informes y exportaciones."""

import csv
from collections.abc import Sequence
from io import StringIO

from contab.models import ApunteContable, Inmueble


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

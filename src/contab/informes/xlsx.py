
"""Exportación Excel de los informes contables."""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.pagebreak import Break


def generar_xlsx_resumen_iva(
    filas: list[list[str | int]],
) -> bytes:
    """Genera el XLSX a partir de las filas ya calculadas.

    Los importes están expresados en céntimos.
    Las fórmulas solo realizan operaciones entre celdas.
    """

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Resumen anual IVA"
    hoja.sheet_view.showGridLines = False

    hoja.column_dimensions["A"].width = 30

    for columna in "BCEF":
        hoja.column_dimensions[columna].width = 12
    hoja.column_dimensions["D"].width = 18

    formato_importe = '#,##0.00;[Red]-#,##0.00'

    fondo_cabecera = PatternFill(
        "solid",
        fgColor="D9E2F3",
    )
    fondo_total = PatternFill(
        "solid",
        fgColor="EDEDED",
    )

    inicio_detalle = None
    totales_grupo = []
    totales_trimestre = []

    for numero_fila, valores in enumerate(filas, start=1):
        concepto = valores[0]

        es_cabecera = (
            " - Locales comerciales" in concepto
            or " - Pisos y otros" in concepto
        )

        es_total_grupo = concepto in (
            "Totales Locales comerciales",
            "Totales Pisos y otros",
        )

        es_total_trimestre = concepto in (
            "Totales 1T",
            "Totales 2T",
            "Totales 3T",
            "Totales 4T",
        )

        es_total_anual = concepto.startswith(
            "Totales del año "
        )

        es_detalle = (
            not es_cabecera
            and not concepto.startswith("Totales ")
            and any(
                isinstance(valor, int)
                for valor in valores[1:]
            )
        )

        for numero_columna, valor in enumerate(valores, start=1):
            celda = hoja.cell(
                row=numero_fila,
                column=numero_columna,
            )
            celda.font = Font(name="Liberation Sans", size=11)

            if isinstance(valor, int):
                celda.value = valor / 100
                celda.number_format = formato_importe
                celda.alignment = Alignment(horizontal="right")
            else:
                # Las referencias de inmuebles son texto,
                # nunca fórmulas aportadas por los datos.
                if valor.startswith("="):
                    valor = "'" + valor

                celda.value = valor

        if es_cabecera:
            inicio_detalle = numero_fila + 1

        if es_detalle:
            # El neto excluye el IVA:
            # ingresos - gastos - retención/Hacienda.
            hoja.cell(
                row=numero_fila,
                column=6,
                value=(
                    f"=B{numero_fila}-C{numero_fila}"
                    f"-D{numero_fila}"
                ),
            )

        if es_total_grupo:
            for numero_columna in range(2, 7):
                letra = get_column_letter(numero_columna)

                if inicio_detalle < numero_fila:
                    formula = (
                        f"=SUM({letra}{inicio_detalle}:"
                        f"{letra}{numero_fila - 1})"
                    )
                    hoja.cell(
                        row=numero_fila,
                        column=numero_columna,
                        value=formula,
                    )

            totales_grupo.append(numero_fila)

        if es_total_trimestre:
            for numero_columna in range(2, 7):
                letra = get_column_letter(numero_columna)
                referencias = ",".join(
                    f"{letra}{fila}"
                    for fila in totales_grupo
                )

                hoja.cell(
                    row=numero_fila,
                    column=numero_columna,
                    value=f"=SUM({referencias})",
                )

            totales_trimestre.append(numero_fila)
            totales_grupo = []
            if concepto == "Totales 2T":
                hoja.row_breaks.append(Break(id=numero_fila))

        if es_total_anual:
            for numero_columna in range(2, 7):
                letra = get_column_letter(numero_columna)
                referencias = ",".join(
                    f"{letra}{fila}"
                    for fila in totales_trimestre
                )

                hoja.cell(
                    row=numero_fila,
                    column=numero_columna,
                    value=f"=SUM({referencias})",
                )

        if es_cabecera or concepto.startswith("Totales "):
            for celda in hoja[numero_fila]:
                celda.font = Font(
                    name="Liberation Sans",
                    size=10,
                    bold=True,
                )
                celda.fill = (
                    fondo_cabecera
                    if es_cabecera
                    else fondo_total
                )

        if es_cabecera:
            for numero_columna in range(2, 7):
                hoja.cell(
                    row=numero_fila,
                    column=numero_columna,
                ).alignment = Alignment(horizontal="right")

        if numero_fila == 1:
            hoja.cell(1, 1).font = Font(
                name="Liberation Sans",
                bold=True,
                size=14,
            )

        # Todas las celdas numéricas, incluidas las
        # que contienen fórmulas, usan el mismo formato.
        for numero_columna in range(2, 7):
            celda = hoja.cell(
                numero_fila,
                numero_columna,
            )

            if isinstance(celda.value, (int, float)) or (
                isinstance(celda.value, str)
                and celda.value.startswith("=")
            ):
                celda.number_format = formato_importe
                celda.alignment = Alignment(
                    horizontal="right"
                )

    hoja.merge_cells("A1:F1")
    hoja.merge_cells("B3:F3")

    hoja.freeze_panes = "B5"

    hoja.sheet_properties.pageSetUpPr.fitToPage = True
    hoja.page_setup.orientation = "portrait"
    hoja.page_setup.fitToWidth = 1
    hoja.page_setup.fitToHeight = 0
    hoja.print_options.horizontalCentered = True

    salida = BytesIO()
    libro.save(salida)

    return salida.getvalue()

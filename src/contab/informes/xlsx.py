
"""Exportación Excel de los informes contables."""

import re

from io import BytesIO
from collections.abc import Sequence
from copy import copy
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.pagebreak import Break



def _nombre_hoja_inmueble(referencia: str, usados: set[str]) -> str:
    """Obtiene un nombre de hoja válido y no repetido."""

    nombre = re.sub(r"[\[\]:*?/\\]", "-", referencia).strip()
    nombre = nombre.strip("'") or "Inmueble"
    nombre = nombre[:31]

    candidato = nombre
    numero = 2

    while candidato.casefold() in usados:
        sufijo = f" ({numero})"
        candidato = nombre[:31 - len(sufijo)] + sufijo
        numero += 1

    usados.add(candidato.casefold())
    return candidato


def _texto_excel(valor: str) -> str:
    """Impide interpretar como fórmula un texto de un apunte."""
    return "'" + valor if valor.startswith("=") else valor


def generar_xlsx_ingresos_gastos(
    informes: Sequence[dict],
) -> bytes:
    """Exporta uno o varios informes de ingresos y gastos.

    Cada inmueble ocupa una hoja independiente.
    Los importes contables proceden de los informes
    preparados, expresados en céntimos.
    """

    libro = Workbook()
    usados: set[str] = set()

    formato_importe = '#,##0.00;[Red]-#,##0.00'
    formato_fecha = "DD/MM/YYYY"

    fondo_cabecera = PatternFill(
        "solid", fgColor="DCDCDC"
    )
    fondo_total = PatternFill(
        "solid", fgColor="FFFFFF"   #EDFFED"
    )
    lado_fino = Side(style="thin", color="000000")

    borde_apunte = Border(
        left=lado_fino,
        right=lado_fino,
        top=lado_fino,
        bottom=lado_fino,
    )

    for indice, informe in enumerate(informes):
        hoja = libro.active if indice == 0 else libro.create_sheet()

        hoja.title = _nombre_hoja_inmueble(
            informe["inmueble"].referencia,
            usados,
        )
        hoja.sheet_view.showGridLines = True

        categorias = informe["categorias_gasto"]
        numero_categorias = len(categorias)

        # A: Fecha; B: Concepto; C: Ingresos;
        # D...: Categorías; últimas: IVA y Retención.
        columna_iva = 4 + numero_categorias
        columna_retencion = columna_iva + 1
        ultima_columna = columna_retencion

        hoja.column_dimensions["A"].width = 13
        hoja.column_dimensions["B"].width = 38

        # Todas las columnas de importes:
        # Ingresos, categorías de gastos, IVA y Retención.
        for numero in range(3, ultima_columna + 1):
            letra = get_column_letter(numero)
            hoja.column_dimensions[letra].width = 11

        def escribir_importe(
            fila: int,
            columna: int,
            valor: int | str,
        ) -> None:
            celda = hoja.cell(fila, columna)

            celda.value = (
                round(valor / 100, 2)
                if isinstance(valor, int)
                else valor
            )
            celda.number_format = formato_importe
            celda.alignment = Alignment(horizontal="right")

        def fila_cabecera(
            fila: int,
            etiquetas: list[str],
        ) -> None:
            for columna, etiqueta in enumerate(etiquetas, start=1):
                celda = hoja.cell(
                    fila, columna, _texto_excel(etiqueta)
                )
                celda.fill = fondo_cabecera
                celda.font = Font(bold=True, size=10)
                celda.alignment = Alignment(
                    horizontal="right" if columna >= 3 else "left",
                    vertical="bottom",
                    wrap_text=True,
                )

            hoja.row_dimensions[fila].height = 48

        def fila_total(
            fila: int,
            etiqueta: str,
            importes: dict,
            inicio_detalle: int | None = None,
            filas_origen: list[int] | None = None,
        ) -> None:
            hoja.cell(fila, 2, etiqueta)

            columnas = [
                (3, importes["ingresos"]),
                *[
                    (4 + posicion, importes["gastos"][codigo])
                    for posicion, (codigo, _) in enumerate(categorias)
                ],
                (columna_iva, importes["iva"]),
                (columna_retencion, importes["retencion"]),
            ]

            for columna, valor in columnas:
                letra = get_column_letter(columna)

                if filas_origen is not None:
                    referencias = ",".join(
                        f"{letra}{origen}"
                        for origen in filas_origen
                    )
                    resultado = (
                        f"=SUM({referencias})"
                        if referencias
                        else 0
                    )
                elif inicio_detalle is not None and inicio_detalle < fila:
                    resultado = (
                        f"=SUM({letra}{inicio_detalle}:"
                        f"{letra}{fila - 1})"
                    )
                else:
                    resultado = valor

                escribir_importe(fila, columna, resultado)

            for columna in range(1, ultima_columna + 1):
                celda = hoja.cell(fila, columna)
                celda.fill = fondo_total
                celda.font = Font(bold=True)

        def resumen(
            fila: int,
            etiqueta: str,
            fila_total_detalle: int,
        ) -> int:
            """Escribe cabecera y totales del resumen compacto."""

            encabezados = [
                "Concepto", "Ingresos", "Gastos",
                "IVA", "Retención",
            ]

            for columna, texto in enumerate(encabezados, start=2):
                celda = hoja.cell(fila, columna, texto)
                celda.fill = fondo_cabecera
                celda.font = Font(bold=True)
                celda.alignment = Alignment(
                    horizontal="right" if columna > 2 else "left"
                )

            fila += 1
            hoja.cell(fila, 2, etiqueta)

            escribir_importe(
                fila, 3, f"=C{fila_total_detalle}"
            )

            columnas_gasto = [
                get_column_letter(4 + posicion)
                for posicion in range(numero_categorias)
            ]

            referencias = ",".join(
                f"{letra}{fila_total_detalle}"
                for letra in columnas_gasto
            )
            escribir_importe(
                fila, 4,
                f"=SUM({referencias})" if referencias else 0,
            )

            escribir_importe(
                fila, 5,
                f"={get_column_letter(columna_iva)}"
                f"{fila_total_detalle}",
            )
            escribir_importe(
                fila, 6,
                f"={get_column_letter(columna_retencion)}"
                f"{fila_total_detalle}",
            )

            for columna in range(2, 7):
                celda = hoja.cell(fila, columna)
                celda.fill = fondo_total
                celda.font = Font(bold=True)

            return fila + 1

        hoja.cell(
            1, 1,
            "Ingresos y gastos del año "
            f"{informe['anio']} — "
            f"{_texto_excel(informe['inmueble'].referencia)}"
            f" - {_texto_excel(informe['inmueble'].descripcion)}",
        )
        hoja.cell(1, 1).font = Font(bold=True, size=14)
        hoja.row_dimensions[1].height = 24

        fila = 3
        filas_totales_trimestres = []

        for trimestre in informe["trimestres"]:
            etiquetas = [
                "Fecha",
                f"{trimestre['numero']}T - Concepto",
                "Ingresos",
                *(nombre for _, nombre in categorias),
                "IVA",
                "Retención",
            ]

            fila_cabecera(fila, etiquetas)
            fila += 1
            inicio_detalle = fila

            for apunte in trimestre["filas"]:
                fecha = hoja.cell(
                    fila, 1, apunte["fecha"]
                )
                fecha.number_format = formato_fecha
                fecha.alignment = Alignment(horizontal="left")

                hoja.cell(
                    fila, 2, _texto_excel(apunte["concepto"])
                )

                if apunte["ingresos"]:
                    escribir_importe(fila, 3, apunte["ingresos"])

                for posicion, (codigo, _) in enumerate(categorias):
                    importe = apunte["gastos"][codigo]
                    if importe:
                        escribir_importe(
                            fila, 4 + posicion, importe
                        )

                if apunte["iva"]:
                    escribir_importe(
                        fila, columna_iva, apunte["iva"]
                    )

                if apunte["retencion"]:
                    escribir_importe(
                        fila, columna_retencion,
                        apunte["retencion"],
                    )

                # Bordes en todas las celdas del apunte,
                # incluidas las que no tienen importe.
                for columna in range(1, ultima_columna + 1):
                    hoja.cell(fila, columna).border = borde_apunte

                fila += 1

            fila_total_trimestre = fila

            fila_total(
                fila,
                f"Totales {trimestre['numero']}T",
                trimestre["totales"],
                inicio_detalle=inicio_detalle,
            )

            filas_totales_trimestres.append(fila)
            fila += 2

            fila = resumen(
                fila,
                f"Totales {trimestre['numero']}T",
                fila_total_trimestre,
            )

            fila += 2

        # Totales anuales, separados del cuarto trimestre.
        fila_cabecera(
            fila,
            [
                "Fecha", "Año", "Ingresos",
                *(nombre for _, nombre in categorias),
                "IVA", "Retención",
            ],
        )
        fila += 1

        fila_total_anual = fila

        fila_total(
            fila,
            "Totales del año",
            informe["totales_anuales"],
            filas_origen=filas_totales_trimestres,
        )

        fila += 2
        resumen(fila, "Totales del año", fila_total_anual)

        hoja.sheet_properties.pageSetUpPr.fitToPage = True
        hoja.page_setup.orientation = "landscape"
        hoja.page_setup.paperSize = hoja.PAPERSIZE_A3
        hoja.page_setup.fitToWidth = 1
        hoja.page_setup.fitToHeight = 0

        hoja.print_options.horizontalCentered = True
        hoja.print_area = (
            f"A1:{get_column_letter(ultima_columna)}"
            f"{hoja.max_row}"
        )

        # Aplicar Liberation Sans 11pt a todas las celdas de la hoja
        for fila_celdas in hoja.iter_rows():
            for celda in fila_celdas:
                fuente = copy(celda.font)
                fuente.name = "Liberation Sans"
                fuente.sz = 11
                celda.font = fuente

    # El título de la hoja a 14pt
    hoja["A1"].font = Font(
        name="Liberation Sans",
        size=14,
        bold=True,
    )

    if not informes:
        libro.active.title = "Sin inmuebles"
        libro.active["A1"] = "No hay inmuebles para exportar."

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


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
        fgColor="DCDCDC",
    )
    fondo_total = PatternFill(
        "solid",
        fgColor="E6FFE6",
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


"""Pruebas de exportación XLSX de informes."""

from io import BytesIO

from openpyxl import load_workbook

from contab.informes.xlsx import generar_xlsx_resumen_iva


def test_xlsx_resumen_iva_valores_y_formulas():
    """Conserva valores contables y genera sumas en Excel."""

    filas = [
        ["Resumen del año 2026", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        [
            "Notas:",
            "Neto significa Ingr. Bruto - Gastos "
            "- Retención/Hacienda",
            "", "", "", "",
        ],
        ["", "", "", "", "", ""],
        [
            "1T - Locales comerciales",
            "Ingr. Bruto", "Gastos",
            "Retención", "IVA", "Neto",
        ],
        ["LOCAL-1", 100000, 20000, 19000, 21000, 61000],
        ["Totales Locales comerciales", 100000, 20000, 19000, 21000, 61000],
        ["", "", "", "", "", ""],
        [
            "1T - Pisos y otros",
            "Ingr. Bruto", "Gastos",
            "Hacienda (25,00%)", "IVA", "Neto",
        ],
        ["PISO-1", 80000, 20000, 15000, 0, 45000],
        ["Totales Pisos y otros", 80000, 20000, 15000, 0, 45000],
        ["", "", "", "", "", ""],
        ["Totales 1T", 180000, 40000, 34000, 21000, 85000],
        ["", "", "", "", "", ""],
        ["Totales del año 2026", 180000, 40000, 34000, 21000, 85000],
    ]

    contenido = generar_xlsx_resumen_iva(filas)

    libro = load_workbook(BytesIO(contenido))
    hoja = libro["Resumen anual IVA"]

    # Importes contables como números en euros.
    assert hoja["B6"].value == 1000
    assert hoja["C6"].value == 200
    assert hoja["D6"].value == 190
    assert hoja["E6"].value == 210

    assert hoja["B10"].value == 800
    assert hoja["D10"].value == 150

    # Neto y totales como fórmulas.
    assert hoja["F6"].value == "=B6-C6-D6"
    assert hoja["F10"].value == "=B10-C10-D10"

    assert hoja["B7"].value == "=SUM(B6:B6)"
    assert hoja["B11"].value == "=SUM(B10:B10)"
    assert hoja["B13"].value == "=SUM(B7,B11)"
    assert hoja["B15"].value == "=SUM(B13)"

    assert hoja["B6"].number_format != "General"
    assert hoja.column_dimensions["A"].width == 30

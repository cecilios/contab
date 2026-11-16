"""Servicios para generar informes y exportaciones."""

from datetime import date
from collections.abc import Sequence

from contab.models import (
    ApunteContable,
    Contrato,
    DistribucionApunte,
    ImputacionContrato,
    Inmueble,
)



def _importe_firmado(
    apunte: ApunteContable,
    importe: int,
) -> int:
    """Aplica el signo del apunte a un importe positivo."""

    return -importe if apunte.importe_negativo else importe


def _base_propietario(
    apunte: ApunteContable,
) -> int:
    """Devuelve la base del apunte que corresponde al propietario."""

    if apunte.tratamiento in {
        "CONTABILIZAR",
        "FACTURAR",
    }:
        return apunte.base

    if apunte.tratamiento == "REPERCUTIR":
        return apunte.base - sum(
            imputacion.base
            for imputacion in apunte.imputaciones_contrato
        )

    return 0


def _distribucion_inmueble(
    *,
    apunte: ApunteContable,
    inmueble: Inmueble,
):
    """Devuelve la distribución del apunte correspondiente al inmueble."""

    return next(
        (
            distribucion
            for distribucion in apunte.distribuciones
            if distribucion.inmueble_id == inmueble.id
        ),
        None,
    )


def _base_propietario_distribucion(
    distribucion: DistribucionApunte,
) -> int:
    """Devuelve la base de la distribución que corresponde al propietario."""

    if distribucion.apunte.tratamiento in {
        "CONTABILIZAR",
        "FACTURAR",
    }:
        return distribucion.base

    if distribucion.apunte.tratamiento == "REPERCUTIR":
        return distribucion.base - sum(
            imputacion.base
            for imputacion in distribucion.imputaciones_contrato
        )

    return 0


def _base_propietario_inmueble(
    *,
    apunte: ApunteContable,
    inmueble: Inmueble,
) -> int:
    """Devuelve la base del apunte atribuible al propietario del inmueble."""

    distribucion = _distribucion_inmueble(
        apunte=apunte,
        inmueble=inmueble,
    )

    if distribucion is not None:
        return _base_propietario_distribucion(
            distribucion
        )

    return _base_propietario(apunte)


def preparar_ingresos_gastos_anuales(
    *,
    inmueble: Inmueble,
    apuntes: Sequence[ApunteContable],
    categorias: dict,
    anio: int,
) -> dict:
    """Prepara el detalle y los totales de un inmueble por trimestres.

    Los importes se expresan en céntimos.
    """

    categorias_gasto = tuple(
        (categoria.codigo, categoria.nombre)
        for categoria in categorias.values()
        if categoria.naturaleza == "GASTO"
    )
    claves_gasto = tuple(
        codigo for codigo, _ in categorias_gasto
    )

    def importes_vacios() -> dict:
        return {
            "ingresos": 0,
            "gastos": dict.fromkeys(claves_gasto, 0),
            "total_gastos": 0,
            "iva": 0,
            "retencion": 0,
        }

    def acumular(destino: dict, origen: dict) -> None:
        destino["ingresos"] += origen["ingresos"]
        destino["total_gastos"] += origen["total_gastos"]
        destino["iva"] += origen["iva"]
        destino["retencion"] += origen["retencion"]

        for codigo in claves_gasto:
            destino["gastos"][codigo] += origen["gastos"][codigo]

    trimestres = [
        {
            "numero": numero,
            "filas": [],
            "totales": importes_vacios(),
        }
        for numero in range(1, 5)
    ]

    totales_anuales = importes_vacios()

    seleccionados = sorted(
        (
            apunte
            for apunte in apuntes
            if apunte.fecha.year == anio
            and apunte.tratamiento in {
                "CONTABILIZAR",
                "FACTURAR",
                "REPERCUTIR",
            }
            and (
                apunte.inmueble_id == inmueble.id
                or _distribucion_inmueble(
                    apunte=apunte,
                    inmueble=inmueble,
                ) is not None
            )
        ),
        key=lambda apunte: (
            apunte.fecha,
            apunte.id or 0,
        ),
    )

    for apunte in seleccionados:
        distribucion = _distribucion_inmueble(
            apunte=apunte,
            inmueble=inmueble,
        )

        importe_base = (
            distribucion.base
            if distribucion is not None
            else apunte.base
        )

        importe_iva = (
            distribucion.iva_importe
            if distribucion is not None
            else apunte.iva_importe
        )

        importe_retencion = (
            distribucion.retencion_importe
            if distribucion is not None
            else apunte.retencion_importe
        )

        importes = importes_vacios()

        if apunte.naturaleza == "INGRESO":
            importes["ingresos"] = _importe_firmado(
                apunte, importe_base
            )
            importes["iva"] = _importe_firmado(
                apunte, importe_iva
            )
            importes["retencion"] = _importe_firmado(
                apunte, importe_retencion
            )

        else:
            if apunte.categoria not in importes["gastos"]:
                raise ValueError(
                    "Categoría de gastos no configurada: "
                    f"{apunte.categoria}"
                )

            # Reutiliza las imputaciones ya persistidas.
            base_propietario = (
                _base_propietario_distribucion(distribucion)
                if distribucion is not None
                else _base_propietario(apunte)
            )

            importe_gasto = _importe_firmado(
                apunte, base_propietario
            )

            # Los gastos totalmente repercutidos al inquilino
            # no forman parte de los gastos del propietario.
            if apunte.tratamiento == "REPERCUTIR" and base_propietario == 0:
                continue

            importes["gastos"][apunte.categoria] = importe_gasto
            importes["total_gastos"] = importe_gasto

        fila = {
            "fecha": apunte.fecha,
            "concepto": apunte.concepto,
            **importes,
        }

        trimestre = trimestres[
            (apunte.fecha.month - 1) // 3
        ]

        trimestre["filas"].append(fila)
        acumular(trimestre["totales"], importes)
        acumular(totales_anuales, importes)

    return {
        "inmueble": inmueble,
        "anio": anio,
        "categorias_gasto": categorias_gasto,
        "trimestres": trimestres,
        "totales_anuales": totales_anuales,
    }


def importe_irpf_estimado(
    *,
    ingresos: int,
    gastos: int,
    retencion: int,
    porcentaje_estimado: int,
    descontar_gastos: bool,
    solo_retencion_real: bool,
) -> int:
    """Devuelve la retención real o la estimación de Hacienda."""

    if solo_retencion_real:
        return retencion

    base = ingresos - gastos if descontar_gastos else ingresos
    base = max(0, base)

    return (
        base * porcentaje_estimado + 5000
    ) // 10000


def _importe_neto_estimado(
    *,
    ingresos: int,
    gastos: int,
    impuesto: int,
) -> int:
    """Calcula el neto sin descontar el IVA."""

    return ingresos - gastos - impuesto


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
    descontar_gastos: bool,
    solo_retencion_real: bool,
) -> tuple[int, int, int, int, int]:
    """Calcula ingresos, gastos, impuesto, IVA y neto de un trimestre."""
    apuntes_aplicables = [
        apunte
        for apunte in apuntes
        if (
            apunte.inmueble_id == inmueble.id
            or _distribucion_inmueble(
                apunte=apunte,
                inmueble=inmueble,
            )
            is not None
        )
        and apunte.fecha.year == anio
        and (apunte.fecha.month - 1) // 3 + 1
        == trimestre
        and apunte.tratamiento in {
            "CONTABILIZAR",
            "FACTURAR",
            "REPERCUTIR",
        }
    ]

    ingresos = sum(
        _importe_firmado(apunte, apunte.base)
        for apunte in apuntes_aplicables
        if apunte.naturaleza == "INGRESO"
    )

    gastos = sum(
        _importe_firmado(
            apunte,
            _base_propietario_inmueble(
                apunte=apunte,
                inmueble=inmueble,
            ),
        )
        for apunte in apuntes_aplicables
        if apunte.naturaleza == "GASTO"
    )

    iva = sum(
        _importe_firmado(apunte, apunte.iva_importe)
        for apunte in apuntes_aplicables
        if apunte.naturaleza == "INGRESO"
    )

    retencion = sum(
        _importe_firmado(apunte, apunte.retencion_importe)
        for apunte in apuntes_aplicables
        if apunte.naturaleza == "INGRESO"
    )

    impuesto = importe_irpf_estimado(
        ingresos=ingresos,
        gastos=gastos,
        retencion=retencion,
        porcentaje_estimado=porcentaje_irpf_estimado,
        descontar_gastos=descontar_gastos,
        solo_retencion_real=solo_retencion_real,
    )

    neto = _importe_neto_estimado(
        ingresos=ingresos,
        gastos=gastos,
        impuesto=impuesto,
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

    - Incluye los inmuebles activos que no sean de tipo T.
    - Incluye los inmuebles inactivos con apuntes aplicables durante el año.
    - Para apuntes de inmuebles T, incluye los locales de sus distribuciones.
    - Excluye los inmuebles T como contabilidad propia.
    - Considera los tratamientos CONTABILIZAR, FACTURAR y REPERCUTIR.
    - Devuelve los inmuebles ordenados por referencia.
    """
    inmuebles_con_apuntes: set[int] = set()

    for apunte in apuntes:
        if apunte.fecha.year != anio:
            continue

        if apunte.tratamiento not in {
            "CONTABILIZAR",
            "FACTURAR",
            "REPERCUTIR",
        }:
            continue

        if apunte.inmueble.tipo == "T":
            inmuebles_con_apuntes.update(
                distribucion.inmueble_id
                for distribucion in apunte.distribuciones
            )
        else:
            inmuebles_con_apuntes.add(
                apunte.inmueble_id
            )

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


def preparar_resumen_anual_iva(
    *,
    inmuebles: Sequence[Inmueble],
    contratos: Sequence[Contrato],
    apuntes: Sequence[ApunteContable],
    anio: int,
    porcentaje_irpf_estimado: int,
    descontar_gastos: bool = True,
) -> list[list[str | int]]:
    """Prepara las filas del resumen anual de IVA.

    Los importes se mantienen como enteros en céntimos.
    No aplica formatos de presentación ni genera CSV.
    """

    seleccionados = seleccionar_inmuebles_exportacion_iva(
        inmuebles=inmuebles,
        apuntes=apuntes,
        anio=anio,
    )

    filas: list[list[str | int]] = [
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
            "- Retención/Hacienda",
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
                (
                    "Hacienda ("
                    f"{_formatear_importe(porcentaje_irpf_estimado)}"
                    "%)"
                ),
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
                    descontar_gastos=descontar_gastos,
                    solo_retencion_real=(
                        nombre_grupo == "Locales comerciales"
                    ),
                )

                filas.append(
                    [
                        inmueble.referencia,
                        *totales,
                    ]
                )

                for posicion, importe in enumerate(totales):
                    totales_grupo[posicion] += importe
                    totales_trimestre[posicion] += importe
                    totales_anuales[posicion] += importe

            filas.append(
                [
                    f"Totales {nombre_grupo}",
                    *totales_grupo,
                ]
            )
            filas.append(_fila_vacia())

        filas.append(
            [
                f"Totales {trimestre}T",
                *totales_trimestre,
            ]
        )
        filas.append(_fila_vacia())

    filas.append(
        [
            f"Totales del año {anio}",
            *totales_anuales,
        ]
    )

    return filas



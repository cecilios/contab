"""Implementa la lógica de negocio relacionada con la facturación."""

from datetime import date
from dataclasses import dataclass

from contab.models import Contrato, Factura, FacturaLinea, RevisionRenta
from contab.contratos.services import renta_facturable

from contab.calculos import redondear_division


class CalculoFacturaError(Exception):
    """Indica que no puede obtenerse un cálculo válido de factura."""

class FacturacionError(Exception):
    """Indica que no puede generarse una factura válida."""



@dataclass(frozen=True)
class CalculoFactura:
    """Contiene los importes resultantes del cálculo de una factura."""

    base: int
    iva_importe: int
    retencion_importe: int
    total: int

@dataclass(frozen=True)
class RepercusionGasto:
    """Describe un gasto que debe repercutirse como línea de factura."""

    concepto: str
    importe: int


def siguiente_numero_factura(
    contrato: Contrato,
    anio: int,
) -> tuple[int, str]:
    """Calcula la siguiente secuencia y número de factura del inmueble."""
    inmueble = contrato.inmueble

    secuencias = [
        factura.numero_secuencia
        for contrato_inmueble in inmueble.contratos
        for factura in contrato_inmueble.facturas
        if factura.anio == anio
    ]

    secuencia = max(secuencias, default=0) + 1

    numero = (
        f"{secuencia:02d}/"
        f"{anio}"
        f"{inmueble.codigo_facturacion}"
    )

    return secuencia, numero


def calcular_importes_factura(
    lineas: list[FacturaLinea],
    iva_porcentaje: int,
    retencion_porcentaje: int,
) -> CalculoFactura:
    """Calcula base, IVA, retención y total a partir de las líneas."""
    if iva_porcentaje < 0:
        raise CalculoFacturaError(
            "El porcentaje de IVA no puede ser negativo."
        )

    if retencion_porcentaje < 0:
        raise CalculoFacturaError(
            "El porcentaje de retención no puede ser negativo."
        )

    base = sum(linea.importe for linea in lineas)

    if base < 0:
        raise CalculoFacturaError(
            "Las líneas de factura no pueden producir una base negativa."
        )

    iva_importe = redondear_division(
        base * iva_porcentaje,
        10000,
    )

    retencion_importe = redondear_division(
        base * retencion_porcentaje,
        10000,
    )

    total = base + iva_importe - retencion_importe

    if total < 0:
        raise CalculoFacturaError(
            "El cálculo produce un total de factura negativo."
        )

    return CalculoFactura(
        base=base,
        iva_importe=iva_importe,
        retencion_importe=retencion_importe,
        total=total,
    )


def crear_factura(
    contrato: Contrato,
    periodo: date,
    fecha_emision: date,
    ruta_pdf: str = "",
    revision_renta: RevisionRenta | None = None,
    diferencia_revision: int = 0,
    aviso_revision: str | None = None,
    repercusiones: list[RepercusionGasto] | None = None,
) -> Factura:
    """Prepara una factura ordinaria mensual sin persistirla."""
    if periodo.day != 1:
        raise FacturacionError(
            "El periodo facturado debe corresponder al día 1 del mes."
        )

    if periodo < contrato.fecha_inicio_facturacion:
        raise FacturacionError(
            "No puede facturarse un periodo anterior al inicio de facturación."
        )

    secuencia, numero = siguiente_numero_factura(
        contrato,
        periodo.year,
    )

    importe_renta = renta_facturable(
        contrato,
        periodo,
    )

    linea_renta = FacturaLinea(
        orden=1,
        tipo="RENTA",
        concepto=contrato.concepto_factura,
        importe=importe_renta,
    )
    lineas = [linea_renta]

    if diferencia_revision != 0:
        if revision_renta is None:
            raise FacturacionError(
                "Una diferencia de revisión debe estar vinculada a una revisión."
            )

        lineas.append(
            FacturaLinea(
                orden=2,
                tipo="DIFERENCIA_REVISION",
                concepto="Diferencia de revisión de renta",
                importe=diferencia_revision,
            )
        )

    if repercusiones:
        for repercusion in repercusiones:
            if repercusion.importe < 0:
                raise FacturacionError(
                    "El importe de un gasto repercutido no puede ser negativo."
                )

            if not repercusion.concepto.strip():
                raise FacturacionError(
                    "Todo gasto repercutido debe tener un concepto."
                )

            lineas.append(
                FacturaLinea(
                    orden=len(lineas) + 1,
                    tipo="REPERCUSION_GASTO",
                    concepto=repercusion.concepto,
                    importe=repercusion.importe,
                )
            )

    calculo = calcular_importes_factura(
        lineas=lineas,
        iva_porcentaje=contrato.iva_porcentaje,
        retencion_porcentaje=contrato.retencion_porcentaje,
    )

    factura = Factura(
        contrato=contrato,
        numero_secuencia=secuencia,
        anio=periodo.year,
        numero_factura=numero,
        fecha_emision=fecha_emision,
        periodo=periodo,
        base=calculo.base,
        iva_porcentaje=contrato.iva_porcentaje,
        iva_importe=calculo.iva_importe,
        retencion_porcentaje=contrato.retencion_porcentaje,
        retencion_importe=calculo.retencion_importe,
        total=calculo.total,
        ruta_pdf=ruta_pdf,
        revision_renta=revision_renta,
        aviso_revision=aviso_revision,
    )

    factura.lineas.extend(lineas)

    return factura


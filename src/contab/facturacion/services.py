"""Implementa la lógica de negocio relacionada con la facturación."""

from dataclasses import dataclass

from contab.calculos import redondear_division
from contab.models import Contrato, FacturaLinea

class CalculoFacturaError(Exception):
    """Indica que no puede obtenerse un cálculo válido de factura."""


@dataclass(frozen=True)
class CalculoFactura:
    """Contiene los importes resultantes del cálculo de una factura."""

    base: int
    iva_importe: int
    retencion_importe: int
    total: int



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

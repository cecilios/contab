"""Implementa la lógica de negocio relacionada con la facturación."""

from contab.models import Contrato


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

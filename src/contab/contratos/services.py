"""Implementa la lógica de negocio relacionada con contratos y rentas."""

from datetime import date

from contab.models import Contrato, RentaContrato


class RentaNoDisponibleError(Exception):
    """Indica que no existe una renta aplicable para la fecha solicitada."""

class RentaFacturableError(Exception):
    """Indica que no puede calcularse una renta facturable válida."""


"""Funciones auxiliares"""
def _redondear_division(numerador: int, denominador: int) -> int:
    """Redondea una división entera al entero más próximo con mitad hacia arriba."""
    return (numerador + denominador // 2) // denominador


"""Funciones de negocio"""
def renta_vigente(contrato: Contrato, fecha: date) -> RentaContrato:
    """Devuelve la renta ordinaria vigente de un contrato en una fecha."""
    rentas_aplicables = (
        renta
        for renta in contrato.rentas
        if renta.fecha_desde <= fecha
    )

    try:
        return max(
            rentas_aplicables,
            key=lambda renta: renta.fecha_desde,
        )
    except ValueError as exc:
        raise RentaNoDisponibleError(
            f"No existe renta vigente para el contrato {contrato.id} "
            f"en la fecha {fecha.isoformat()}."
        ) from exc


def renta_facturable(contrato: Contrato, fecha: date) -> int:
    """Devuelve en céntimos la renta facturable de un contrato en una fecha."""
    renta = renta_vigente(contrato, fecha)
    importe = renta.importe

    ajustes = [
        ajuste
        for ajuste in contrato.ajustes_renta
        if ajuste.fecha_desde <= fecha <= ajuste.fecha_hasta
    ]

    if len(ajustes) > 1:
        raise RentaFacturableError(
            f"El contrato {contrato.id} tiene varios ajustes activos "
            f"en la fecha {fecha.isoformat()}."
        )

    if not ajustes:
        return importe

    ajuste = ajustes[0]

    if ajuste.tipo == "REDUCCION_PORCENTUAL":
        return _redondear_division(
            importe * (10000 - ajuste.valor),
            10000,
        )

    if ajuste.tipo == "REDUCCION_FIJA":
        resultado = importe - ajuste.valor

        if resultado < 0:
            raise RentaFacturableError(
                "La reducción fija produce una renta facturable negativa."
            )

        return resultado

    if ajuste.tipo == "IMPORTE_FIJO":
        return ajuste.valor

    raise RentaFacturableError(
        f"Tipo de ajuste desconocido: {ajuste.tipo}."
    )


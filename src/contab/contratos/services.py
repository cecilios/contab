"""Implementa la lógica de negocio relacionada con contratos y rentas."""

from datetime import date

from contab.models import Contrato, RentaContrato


class RentaNoDisponibleError(Exception):
    """Indica que no existe una renta aplicable para la fecha solicitada."""


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

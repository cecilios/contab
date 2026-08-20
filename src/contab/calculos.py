"""Proporciona funciones comunes para cálculos monetarios y porcentuales."""


def redondear_division(numerador: int, denominador: int) -> int:
    """Redondea una división al entero más próximo, con mitad hacia arriba."""
    return (numerador + denominador // 2) // denominador

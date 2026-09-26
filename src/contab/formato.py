from decimal import Decimal, InvalidOperation
from datetime import date, datetime



def fecha_a_texto(valor: date) -> str:
    """Convierte una fecha al formato usado por la interfaz."""
    return valor.strftime("%d/%m/%Y")


def texto_a_fecha(texto: str) -> date:
    """Convierte una fecha dd/mm/aaaa a date."""
    texto = texto.strip()

    if not texto:
        raise ValueError("La fecha no puede estar vacía.")

    try:
        return datetime.strptime(
            texto,
            "%d/%m/%Y",
        ).date()
    except ValueError as exc:
        raise ValueError(
            "La fecha indicada no es válida o no tiene "
            "el formato dd/mm/aaaa."
        ) from exc


def periodo_a_texto(periodo: date) -> str:
    """Convierte un período mensual al formato usado por la interfaz."""
    return periodo.strftime("%m/%Y")


def texto_a_periodo(texto: str) -> date:
    """Convierte un período mensual de la interfaz al primer día del mes."""
    texto = texto.strip()

    if not texto:
        raise ValueError("El período no puede estar vacío.")

    try:
        return datetime.strptime(
            texto,
            "%m/%Y",
        ).date().replace(day=1)
    except ValueError as exc:
        raise ValueError(
            "El período no es válido o no tiene "
            "el formato mm/aaaa."
        ) from exc


def importe_a_texto(importe: int) -> str:
    """Convierte un importe en céntimos a texto"""

    euros, centimos = divmod(importe, 100)

    euros_texto = f"{euros:,}".replace(",", ".")

    return f"{euros_texto},{centimos:02d}"


def texto_a_importe(texto: str) -> int:
    """Convierte un importe en euros con coma decimal a céntimos."""
    texto = texto.strip()

    if not texto:
        raise ValueError("El importe no puede estar vacío.")

    try:
        euros = Decimal(texto.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("El importe no es válido.") from exc

    return int(euros * 100)


def importe_a_texto_entrada(importe: int) -> str:
    """Convierte céntimos al formato usado en campos editables."""
    signo = "-" if importe < 0 else ""
    importe = abs(importe)

    euros, centimos = divmod(importe, 100)

    return f"{signo}{euros},{centimos:02d}"


def texto_a_porcentaje(texto: str) -> int:
    """Convierte un porcentaje decimal a centésimas."""
    texto = texto.strip()

    if not texto:
        raise ValueError("El porcentaje no puede estar vacío.")

    try:
        porcentaje = Decimal(texto.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("El porcentaje no es válido.") from exc

    return int(porcentaje * 100)


def porcentaje_a_texto_entrada(porcentaje: int) -> str:
    """Convierte centésimas de porcentaje a texto editable."""
    signo = "-" if porcentaje < 0 else ""
    porcentaje = abs(porcentaje)

    entero, decimales = divmod(porcentaje, 100)

    if decimales == 0:
        return f"{signo}{entero}"

    return f"{signo}{entero},{decimales:02d}"


def fecha_a_texto_largo(fecha: date) -> str:
    """Devuelve una fecha con el mes escrito en español."""

    meses = (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    )

    return (
        f"{fecha.day} de "
        f"{meses[fecha.month - 1]} de "
        f"{fecha.year}"
    )


def periodo_a_texto_largo(periodo: date) -> str:
    """Devuelve un período mensual con el mes escrito en español."""

    meses = (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    )

    mes = meses[periodo.month - 1]

    return f"{mes.capitalize()} de {periodo.year}"



"""Pruebas de la lógica de negocio de facturación."""

from datetime import date

from contab.facturacion.services import siguiente_numero_factura
from contab.models import Contrato, Factura


def test_primera_factura_del_ano_comienza_en_uno(contrato) -> None:
    """Comprueba que la primera factura anual de un inmueble tiene secuencia 1."""
    secuencia, numero = siguiente_numero_factura(contrato, 2026)

    assert secuencia == 1
    assert numero == "01/2026A1"


def test_siguiente_factura_incrementa_secuencia(session, contrato) -> None:
    """Comprueba que la numeración continúa después de la última factura."""
    factura = Factura(
        contrato=contrato,
        numero_secuencia=1,
        anio=2026,
        numero_factura="01/2026A1",
        fecha_emision=date(2026, 2, 1),
        periodo=date(2026, 2, 1),
        base=100000,
        iva_porcentaje=0,
        iva_importe=0,
        retencion_porcentaje=0,
        retencion_importe=0,
        total=100000,
        ruta_pdf="factura.pdf",
    )

    session.add(factura)
    session.commit()

    secuencia, numero = siguiente_numero_factura(contrato, 2026)

    assert secuencia == 2
    assert numero == "02/2026A1"


def test_numeracion_se_reinicia_cada_ano(session, contrato) -> None:
    """Comprueba que cada inmueble reinicia su secuencia al cambiar de año."""
    factura = Factura(
        contrato=contrato,
        numero_secuencia=7,
        anio=2026,
        numero_factura="07/2026A1",
        fecha_emision=date(2026, 12, 1),
        periodo=date(2026, 12, 1),
        base=100000,
        iva_porcentaje=0,
        iva_importe=0,
        retencion_porcentaje=0,
        retencion_importe=0,
        total=100000,
        ruta_pdf="factura.pdf",
    )

    session.add(factura)
    session.commit()

    secuencia, numero = siguiente_numero_factura(contrato, 2027)

    assert secuencia == 1
    assert numero == "01/2027A1"


def test_numeracion_continua_entre_contratos_del_mismo_inmueble(
    session, inmueble
) -> None:
    """Comprueba que un nuevo contrato continúa la secuencia del inmueble."""
    contrato_anterior = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2025, 1, 1),
        fecha_vencimiento=date(2026, 6, 30),
        fecha_fin=date(2026, 6, 30),
        fecha_inicio_facturacion=date(2025, 1, 1),
        fianza=100000,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )

    contrato_nuevo = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2026, 7, 1),
        fecha_vencimiento=date(2030, 6, 30),
        fecha_inicio_facturacion=date(2026, 7, 1),
        fianza=100000,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )

    factura = Factura(
        contrato=contrato_anterior,
        numero_secuencia=6,
        anio=2026,
        numero_factura="06/2026A1",
        fecha_emision=date(2026, 6, 1),
        periodo=date(2026, 6, 1),
        base=100000,
        iva_porcentaje=0,
        iva_importe=0,
        retencion_porcentaje=0,
        retencion_importe=0,
        total=100000,
        ruta_pdf="factura.pdf",
    )

    session.add_all([contrato_anterior, contrato_nuevo, factura])
    session.commit()

    secuencia, numero = siguiente_numero_factura(contrato_nuevo, 2026)

    assert secuencia == 7
    assert numero == "07/2026A1"


def test_factura_anulada_sigue_consumiento_numero(session, contrato) -> None:
    """Comprueba que una factura anulada no libera su número de secuencia."""
    factura = Factura(
        contrato=contrato,
        numero_secuencia=1,
        anio=2026,
        numero_factura="01/2026A1",
        fecha_emision=date(2026, 2, 1),
        periodo=date(2026, 2, 1),
        base=100000,
        iva_porcentaje=0,
        iva_importe=0,
        retencion_porcentaje=0,
        retencion_importe=0,
        total=100000,
        estado="ANULADA",
        ruta_pdf="factura.pdf",
    )

    session.add(factura)
    session.commit()

    secuencia, numero = siguiente_numero_factura(contrato, 2026)

    assert secuencia == 2
    assert numero == "02/2026A1"



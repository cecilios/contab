"""Pruebas de la lógica de negocio de facturación."""

import pytest

from contab.facturacion.services import (
    CalculoFacturaError,
    calcular_importes_factura,
    siguiente_numero_factura,
)
from contab.models import Contrato, Factura, FacturaLinea

from datetime import date



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


def test_calcular_factura_sin_impuestos() -> None:
    """Comprueba el cálculo de una factura sin IVA ni retención."""
    lineas = [
        FacturaLinea(
            orden=1,
            tipo="RENTA",
            concepto="Alquiler",
            importe=100000,
        )
    ]

    calculo = calcular_importes_factura(
        lineas=lineas,
        iva_porcentaje=0,
        retencion_porcentaje=0,
    )

    assert calculo.base == 100000
    assert calculo.iva_importe == 0
    assert calculo.retencion_importe == 0
    assert calculo.total == 100000


def test_calcular_factura_con_iva_y_retencion() -> None:
    """Comprueba que IVA y retención se calculan sobre la base completa."""
    lineas = [
        FacturaLinea(
            orden=1,
            tipo="RENTA",
            concepto="Alquiler",
            importe=100000,
        )
    ]

    calculo = calcular_importes_factura(
        lineas=lineas,
        iva_porcentaje=2100,
        retencion_porcentaje=1900,
    )

    assert calculo.base == 100000
    assert calculo.iva_importe == 21000
    assert calculo.retencion_importe == 19000
    assert calculo.total == 102000


def test_calcular_factura_suma_todas_las_lineas() -> None:
    """Comprueba que renta, diferencias y gastos repercutidos forman la base."""
    lineas = [
        FacturaLinea(
            orden=1,
            tipo="RENTA",
            concepto="Alquiler",
            importe=100000,
        ),
        FacturaLinea(
            orden=2,
            tipo="DIFERENCIA_REVISION",
            concepto="Diferencia revisión",
            importe=2300,
        ),
        FacturaLinea(
            orden=3,
            tipo="REPERCUSION_GASTO",
            concepto="Agua",
            importe=8347,
        ),
    ]

    calculo = calcular_importes_factura(
        lineas=lineas,
        iva_porcentaje=2100,
        retencion_porcentaje=1900,
    )

    assert calculo.base == 110647
    assert calculo.total == (
        calculo.base
        + calculo.iva_importe
        - calculo.retencion_importe
    )


def test_calcular_factura_admite_diferencia_revision_negativa() -> None:
    """Comprueba que una diferencia negativa reduce la base de la factura."""
    lineas = [
        FacturaLinea(
            orden=1,
            tipo="RENTA",
            concepto="Alquiler",
            importe=100000,
        ),
        FacturaLinea(
            orden=2,
            tipo="DIFERENCIA_REVISION",
            concepto="Diferencia revisión",
            importe=-2500,
        ),
    ]

    calculo = calcular_importes_factura(
        lineas=lineas,
        iva_porcentaje=0,
        retencion_porcentaje=0,
    )

    assert calculo.base == 97500
    assert calculo.total == 97500


def test_calcular_factura_redondea_impuestos_al_centimo() -> None:
    """Comprueba que IVA y retención usan el redondeo contable al céntimo."""
    lineas = [
        FacturaLinea(
            orden=1,
            tipo="RENTA",
            concepto="Alquiler",
            importe=10001,
        )
    ]

    calculo = calcular_importes_factura(
        lineas=lineas,
        iva_porcentaje=5000,
        retencion_porcentaje=0,
    )

    # 100,01 € x 50 % = 50,005 € -> 50,01 €
    assert calculo.iva_importe == 5001
    assert calculo.total == 15002


def test_calcular_factura_rechaza_base_negativa() -> None:
    """Comprueba que las líneas no pueden producir una base negativa."""
    lineas = [
        FacturaLinea(
            orden=1,
            tipo="DIFERENCIA_REVISION",
            concepto="Diferencia revisión",
            importe=-10001,
        )
    ]

    with pytest.raises(CalculoFacturaError):
        calcular_importes_factura(
            lineas=lineas,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
        )





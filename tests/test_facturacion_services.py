"""Pruebas de la lógica de negocio de facturación."""

import pytest

from datetime import date

from contab.models import (
    AjusteRenta,
    Contrato,
    Factura,
    FacturaLinea,
    RentaContrato,
    RevisionRenta,
)

from contab.facturacion.services import (
    CalculoFacturaError,
    FacturacionError,
    RepercusionGasto,
    calcular_importes_factura,
    crear_factura,
    siguiente_numero_factura,
)


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


def test_calcular_factura_redondea_iva_hacia_arriba() -> None:
    """Comprueba el redondeo del IVA hacia arriba al superar medio céntimo."""
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

    assert calculo.iva_importe == 5001


def test_calcular_factura_redondea_iva_hacia_abajo() -> None:
    """Comprueba el redondeo del IVA hacia abajo por debajo de medio céntimo."""
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
        iva_porcentaje=2500,
        retencion_porcentaje=0,
    )

    # 100,01 € x 25 % = 25,0025 € -> 25,00 €
    assert calculo.iva_importe == 2500


def test_calcular_factura_redondea_retencion_al_centimo() -> None:
    """Comprueba que la retención usa la misma regla de redondeo monetario."""
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
        iva_porcentaje=0,
        retencion_porcentaje=5000,
    )

    assert calculo.retencion_importe == 5001
    assert calculo.total == 5000


def test_calcular_factura_rechaza_iva_negativo() -> None:
    """Comprueba que el porcentaje de IVA no puede ser negativo."""
    lineas = [
        FacturaLinea(
            orden=1,
            tipo="RENTA",
            concepto="Alquiler",
            importe=100000,
        )
    ]

    with pytest.raises(CalculoFacturaError):
        calcular_importes_factura(
            lineas=lineas,
            iva_porcentaje=-1,
            retencion_porcentaje=0,
        )


def test_calcular_factura_rechaza_retencion_negativa() -> None:
    """Comprueba que el porcentaje de retención no puede ser negativo."""
    lineas = [
        FacturaLinea(
            orden=1,
            tipo="RENTA",
            concepto="Alquiler",
            importe=100000,
        )
    ]

    with pytest.raises(CalculoFacturaError):
        calcular_importes_factura(
            lineas=lineas,
            iva_porcentaje=0,
            retencion_porcentaje=-1,
        )


def test_calcular_factura_admite_base_cero() -> None:
    """Comprueba que una factura con base cero produce importes nulos."""
    lineas = [
        FacturaLinea(
            orden=1,
            tipo="RENTA",
            concepto="Alquiler",
            importe=0,
        )
    ]

    calculo = calcular_importes_factura(
        lineas=lineas,
        iva_porcentaje=2100,
        retencion_porcentaje=1900,
    )

    assert calculo.base == 0
    assert calculo.iva_importe == 0
    assert calculo.retencion_importe == 0
    assert calculo.total == 0


def test_crear_factura_ordinaria(session, contrato) -> None:
    """Comprueba que se crea una factura mensual ordinaria con una línea de renta."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    session.commit()

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 9, 1),
        fecha_emision=date(2026, 9, 1),
        ruta_pdf="facturas/01-2026A1.pdf",
    )

    assert factura.id is None
    assert factura.numero_secuencia == 1
    assert factura.numero_factura == "01/2026A1"
    assert factura.anio == 2026
    assert factura.periodo == date(2026, 9, 1)
    assert factura.fecha_emision == date(2026, 9, 1)

    assert len(factura.lineas) == 1
    assert factura.lineas[0].tipo == "RENTA"
    assert factura.lineas[0].importe == 100000

    assert factura.base == 100000
    assert factura.iva_importe == 0
    assert factura.retencion_importe == 0
    assert factura.total == 100000


def test_crear_factura_aplica_iva_y_retencion(session, contrato) -> None:
    """Comprueba que la factura usa los porcentajes fiscales del contrato."""
    contrato.iva_porcentaje = 2100
    contrato.retencion_porcentaje = 1900
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    session.commit()

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 9, 1),
        fecha_emision=date(2026, 9, 1),
        ruta_pdf="facturas/01-2026A1.pdf",
    )

    assert factura.base == 100000
    assert factura.iva_importe == 21000
    assert factura.retencion_importe == 19000
    assert factura.total == 102000


def test_crear_factura_rechaza_periodo_que_no_sea_dia_primero(
    session, contrato
) -> None:
    """Comprueba que el periodo facturado debe representarse por el día 1."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    session.commit()

    with pytest.raises(FacturacionError):
        crear_factura(
            contrato=contrato,
            periodo=date(2026, 9, 15),
            fecha_emision=date(2026, 9, 1),
            ruta_pdf="factura.pdf",
        )


def test_crear_factura_rechaza_periodo_anterior_al_inicio_facturacion(
    session, contrato
) -> None:
    """Comprueba que no puede facturarse un mes anterior al inicio de facturación."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    session.commit()

    with pytest.raises(FacturacionError):
        crear_factura(
            contrato=contrato,
            periodo=date(2026, 1, 1),
            fecha_emision=date(2026, 1, 1),
            ruta_pdf="factura.pdf",
        )


def test_crear_factura_usa_renta_facturable_con_ajuste(
    session, contrato
) -> None:
    """Comprueba que la línea de renta usa la renta facturable del periodo."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    contrato.ajustes_renta.append(
        AjusteRenta(
            fecha_desde=date(2026, 3, 1),
            fecha_hasta=date(2026, 10, 1),
            tipo="REDUCCION_PORCENTUAL",
            valor=4000,
        )
    )
    session.commit()

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 9, 1),
        fecha_emision=date(2026, 9, 1),
        ruta_pdf="facturas/01-2026A1.pdf",
    )

    assert factura.lineas[0].importe == 60000
    assert factura.base == 60000


def test_crear_factura_con_diferencia_revision_positiva(
    session, contrato
) -> None:
    """Comprueba que una diferencia positiva se añade como línea adicional."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 9, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=230,
        fecha_resolucion=date(2026, 10, 1),
    )
    session.add(revision)
    session.commit()

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
        ruta_pdf="facturas/01-2026A1.pdf",
        revision_renta=revision,
        diferencia_revision=2300,
        aviso_revision="APLICADA",
    )

    assert len(factura.lineas) == 2
    assert factura.lineas[0].tipo == "RENTA"
    assert factura.lineas[1].tipo == "DIFERENCIA_REVISION"
    assert factura.lineas[1].importe == 2300

    assert factura.base == 102300
    assert factura.revision_renta is revision
    assert factura.aviso_revision == "APLICADA"


def test_crear_factura_con_diferencia_revision_negativa(
    session, contrato
) -> None:
    """Comprueba que una diferencia negativa reduce la base de la factura."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 9, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=-250,
        fecha_resolucion=date(2026, 10, 1),
    )
    session.add(revision)
    session.commit()

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
        ruta_pdf="facturas/01-2026A1.pdf",
        revision_renta=revision,
        diferencia_revision=-2500,
        aviso_revision="APLICADA",
    )

    assert len(factura.lineas) == 2
    assert factura.lineas[1].importe == -2500
    assert factura.base == 97500


def test_crear_factura_sin_diferencia_no_anade_linea(
    session, contrato
) -> None:
    """Comprueba que una diferencia cero no genera una línea adicional."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    session.commit()

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 9, 1),
        fecha_emision=date(2026, 9, 1),
        ruta_pdf="facturas/01-2026A1.pdf",
        diferencia_revision=0,
    )

    assert len(factura.lineas) == 1
    assert factura.lineas[0].tipo == "RENTA"


def test_crear_factura_con_revision_sin_diferencia(
    session, contrato
) -> None:
    """Comprueba que una factura puede vincularse a una revisión sin diferencia."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 10, 1),
        metodo="IPC_NACIONAL",
    )
    session.add(revision)
    session.commit()

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 9, 1),
        fecha_emision=date(2026, 9, 1),
        ruta_pdf="facturas/01-2026A1.pdf",
        revision_renta=revision,
        aviso_revision="PREVIO",
    )

    assert factura.revision_renta is revision
    assert factura.aviso_revision == "PREVIO"
    assert len(factura.lineas) == 1


def test_crear_factura_rechaza_diferencia_sin_revision(
    session, contrato
) -> None:
    """Comprueba que una diferencia de revisión exige indicar la revisión."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    session.commit()

    with pytest.raises(FacturacionError):
        crear_factura(
            contrato=contrato,
            periodo=date(2026, 10, 1),
            fecha_emision=date(2026, 10, 1),
            ruta_pdf="factura.pdf",
            diferencia_revision=2300,
        )


def test_crear_factura_con_gasto_repercutido(session, contrato) -> None:
    """Comprueba que un gasto repercutido se añade como línea de factura."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    session.commit()

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 9, 1),
        fecha_emision=date(2026, 9, 1),
        ruta_pdf="factura.pdf",
        repercusiones=[
            RepercusionGasto(
                concepto="Agua del 15/03/2026 al 18/05/2026",
                importe=8347,
            )
        ],
    )

    assert len(factura.lineas) == 2
    assert factura.lineas[1].tipo == "REPERCUSION_GASTO"
    assert factura.lineas[1].importe == 8347
    assert factura.base == 108347


def test_crear_factura_admite_varios_gastos_repercutidos(
    session, contrato
) -> None:
    """Comprueba que pueden añadirse varios gastos repercutidos ordenadamente."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    session.commit()

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 9, 1),
        fecha_emision=date(2026, 9, 1),
        ruta_pdf="factura.pdf",
        repercusiones=[
            RepercusionGasto(
                concepto="Agua",
                importe=5000,
            ),
            RepercusionGasto(
                concepto="Electricidad",
                importe=7500,
            ),
        ],
    )

    assert len(factura.lineas) == 3
    assert factura.lineas[1].orden == 2
    assert factura.lineas[2].orden == 3
    assert factura.base == 112500


def test_crear_factura_rechaza_gasto_repercutido_negativo(
    session, contrato
) -> None:
    """Comprueba que un gasto repercutido no puede tener importe negativo."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    session.commit()

    with pytest.raises(FacturacionError):
        crear_factura(
            contrato=contrato,
            periodo=date(2026, 9, 1),
            fecha_emision=date(2026, 9, 1),
            ruta_pdf="factura.pdf",
            repercusiones=[
                RepercusionGasto(
                    concepto="Agua",
                    importe=-1,
                )
            ],
        )



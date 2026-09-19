"""Pruebas de la lógica de negocio de facturación."""

import pytest

from datetime import date

from contab.config import CategoriaContable
from contab.models import (
    AjusteRenta,
    ApunteContable,
    Contrato,
    ContratoInquilino,
    Factura,
    FacturaLinea,
    Inquilino,
    MovimientoPrevisto,
    RentaContrato,
    RevisionRenta,
)
from contab.facturacion.services import (
    CalculoFacturaError,
    FacturacionError,
    RepercusionGasto,
    calcular_importes_factura,
    componer_destinatario,
    crear_factura,
    emitir_factura,
    preparar_periodo_facturacion,
    preparar_registro_contable_factura,
    siguiente_numero_factura,
)


def _anadir_titular(
    contrato: Contrato,
    *,
    nombre: str = "Ana Pérez",
    nif: str = "11111111A",
    orden: int = 1,
) -> Inquilino:
    """Añade un titular al contrato para los tests de facturación."""

    inquilino = Inquilino(
        nombre=nombre,
        nif=nif,
    )

    contrato.titulares.append(
        ContratoInquilino(
            inquilino=inquilino,
            orden=orden,
        )
    )

    return inquilino


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
        genera_factura=True,
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
        genera_factura=True,
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
    assert factura.ruta_pdf == "facturas/01-2026A1.pdf"


def test_factura_admite_ruta_pdf_vacia_por_defecto(session, contrato) -> None:
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
    assert factura.ruta_pdf == ""


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


def test_preparar_registro_contable_factura(
    session,
    contrato,
) -> None:
    """Comprueba los efectos contables de una factura emitida."""

    categorias = {
        "ING_ALQUILERES": CategoriaContable(
            codigo="ING_ALQUILERES",
            naturaleza="INGRESO",
            nombre="Alquileres",
            activa=True,
            subcategorias=(),
        ),
    }

    contrato.iva_porcentaje = 2100
    contrato.retencion_porcentaje = 1900

    titular_1 = Inquilino(
        nombre="Ana Pérez",
        nif="11111111A",
    )
    titular_2 = Inquilino(
        nombre="Juan Pérez",
        nif="22222222B",
    )

    contrato.titulares.extend(
        [
            ContratoInquilino(
                inquilino=titular_1,
                orden=1,
            ),
            ContratoInquilino(
                inquilino=titular_2,
                orden=2,
            ),
        ]
    )

    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    session.commit()

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    apunte, movimiento = preparar_registro_contable_factura(
        factura=factura,
        categorias=categorias,
    )

    assert isinstance(apunte, ApunteContable)
    assert apunte.id is None

    assert apunte.inmueble is contrato.inmueble
    assert apunte.fecha == date(2026, 10, 1)
    assert apunte.naturaleza == "INGRESO"
    assert apunte.categoria == "ING_ALQUILERES"
    assert apunte.subcategoria is None

    assert apunte.periodo_desde == date(2026, 10, 1)
    assert apunte.periodo_hasta == date(2026, 10, 31)

    assert apunte.base == 100000
    assert apunte.iva_importe == 21000
    assert apunte.retencion_importe == 19000
    assert apunte.total == 102000

    assert apunte.tercero_nombre == "Ana Pérez / Juan Pérez"
    assert apunte.tercero_nif == "11111111A / 22222222B"
    assert apunte.referencia_documento == factura.numero_factura

    assert isinstance(movimiento, MovimientoPrevisto)
    assert movimiento.id is None

    assert movimiento.apunte is apunte
    assert movimiento.contrato is contrato
    assert movimiento.inmueble is contrato.inmueble

    assert movimiento.naturaleza == "INGRESO"
    assert movimiento.importe_esperado == 102000

    assert movimiento.fecha_prevista_desde == date(2026, 10, 1)
    assert movimiento.fecha_prevista_hasta == date(2026, 10, 31)

    assert movimiento.contraparte == "Ana Pérez / Juan Pérez"
    assert movimiento.estado == "PENDIENTE"


def test_preparar_registro_contable_factura_calcula_fin_de_febrero(
    session,
    contrato,
) -> None:
    """Usa todo el mes como ventana prevista de cobro."""

    categorias = {
        "ING_ALQUILERES": CategoriaContable(
            codigo="ING_ALQUILERES",
            naturaleza="INGRESO",
            nombre="Alquileres",
            activa=True,
            subcategorias=(),
        ),
    }

    _anadir_titular(contrato)

    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    session.commit()

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2028, 2, 1),
        fecha_emision=date(2028, 2, 1),
    )

    apunte, movimiento = preparar_registro_contable_factura(
        factura=factura,
        categorias=categorias,
    )

    assert apunte.periodo_desde == date(2028, 2, 1)
    assert apunte.periodo_hasta == date(2028, 2, 29)
    assert movimiento.fecha_prevista_desde == date(2028, 2, 1)
    assert movimiento.fecha_prevista_hasta == date(2028, 2, 29)


def test_preparar_registro_contable_factura_calcula_fin_de_diciembre(
    session,
    contrato,
) -> None:
    """Calcula correctamente el cambio de año."""

    categorias = {
        "ING_ALQUILERES": CategoriaContable(
            codigo="ING_ALQUILERES",
            naturaleza="INGRESO",
            nombre="Alquileres",
            activa=True,
            subcategorias=(),
        ),
    }

    _anadir_titular(contrato)

    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    session.commit()

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 12, 1),
        fecha_emision=date(2026, 12, 1),
    )

    apunte, movimiento = preparar_registro_contable_factura(
        factura=factura,
        categorias=categorias,
    )

    assert apunte.periodo_desde == date(2026, 12, 1)
    assert apunte.periodo_hasta == date(2026, 12, 31)
    assert movimiento.fecha_prevista_desde == date(2026, 12, 1)
    assert movimiento.fecha_prevista_hasta == date(2026, 12, 31)


def test_preparar_periodo_facturacion_separa_locales_y_otros(
    session,
    contrato,
) -> None:
    """Separa contratos con factura de otros ingresos del período."""

    contrato.genera_factura = True
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )
    contrato.iva_porcentaje = 2100
    contrato.retencion_porcentaje = 1900

    contrato_sin_factura = Contrato(
        inmueble=contrato.inmueble,
        fecha_inicio=contrato.fecha_inicio,
        fecha_vencimiento=contrato.fecha_vencimiento,
        fecha_inicio_facturacion=contrato.fecha_inicio,
        genera_factura=False,
        fianza=contrato.fianza,
        iva_porcentaje=0,
        retencion_porcentaje=0,
        direccion_facturacion="Calle Mayor, 1",
        codigo_postal_facturacion="36001",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler vivienda",
    )

    _anadir_titular(
        contrato_sin_factura,
        nombre="Ana Pérez",
        nif="11111111A",
    )
    contrato_sin_factura.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=85000,
        )
    )

    session.add(contrato_sin_factura)
    _anadir_titular(
        contrato,
        nombre="Juan Pérez",
        nif="22222222B",
    )
    session.commit()

    facturas_antes = session.query(Factura).count()

    preparacion = preparar_periodo_facturacion(
        contratos=[contrato, contrato_sin_factura],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    assert preparacion.periodo == date(2026, 10, 1)
    assert preparacion.fecha_emision == date(2026, 10, 1)

    assert len(preparacion.locales) == 1
    assert len(preparacion.otros) == 1

    local = preparacion.locales[0]

    assert local.destinatario_nombre == "Juan Pérez"
    assert local.destinatario_nif == "22222222B"
    assert local.factura is None

    _, numero_esperado = siguiente_numero_factura(contrato,2026)
    assert local.numero_factura == numero_esperado

    assert local.direccion_facturacion == contrato.direccion_facturacion
    assert local.codigo_postal_facturacion == contrato.codigo_postal_facturacion
    assert local.poblacion_facturacion == contrato.poblacion_facturacion
    assert local.provincia_facturacion == contrato.provincia_facturacion

    assert local.contrato is contrato
    assert local.inmueble is contrato.inmueble
    assert local.base == 100000
    assert local.iva_importe == 21000
    assert local.retencion_importe == 19000
    assert local.total == 102000

    otro = preparacion.otros[0]

    assert otro.contrato is contrato_sin_factura
    assert otro.inmueble is contrato_sin_factura.inmueble
    assert otro.importe == 85000

    assert session.query(Factura).count() == facturas_antes


def test_preparar_periodo_facturacion_filtra_contratos_por_vigencia(
    session,
    contrato,
) -> None:
    """Incluye sólo contratos vigentes en algún momento del período."""

    contrato.genera_factura = False
    contrato.fecha_inicio = date(2026, 10, 15)
    contrato.fecha_vencimiento = date(2027, 10, 14)
    contrato.fecha_inicio_facturacion = contrato.fecha_inicio
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=85000,
        )
    )

    session.commit()

    octubre = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    septiembre = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 9, 1),
        fecha_emision=date(2026, 9, 1),
    )

    assert len(octubre.otros) == 1
    assert len(septiembre.otros) == 0

    contrato.fecha_inicio = date(2025, 10, 1)
    contrato.fecha_inicio_facturacion = contrato.fecha_inicio
    contrato.fecha_fin = date(2026, 9, 30)
    session.commit()

    octubre = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    assert len(octubre.otros) == 0


def test_componer_destinatario_con_un_titular(
    contrato,
) -> None:
    """Compone nombre y NIF de un único titular."""

    titular = Inquilino(
        nombre="Ana Pérez",
        nif="11111111A",
    )
    contrato.titulares.append(
        ContratoInquilino(
            inquilino=titular,
            orden=1,
        )
    )

    nombre, nif = componer_destinatario(contrato)

    assert nombre == "Ana Pérez"
    assert nif == "11111111A"


def test_componer_destinatario_con_varios_titulares(
    contrato,
) -> None:
    """Incluye todos los titulares respetando su orden."""

    titular_1 = Inquilino(
        nombre="Ana Pérez",
        nif="11111111A",
    )
    titular_2 = Inquilino(
        nombre="Juan Pérez",
        nif="22222222B",
    )

    contrato.titulares.extend(
        [
            ContratoInquilino(
                inquilino=titular_2,
                orden=2,
            ),
            ContratoInquilino(
                inquilino=titular_1,
                orden=1,
            ),
        ]
    )

    nombre, nif = componer_destinatario(contrato)

    assert nombre == "Ana Pérez / Juan Pérez"
    assert nif == "11111111A / 22222222B"


def test_componer_destinatario_sin_titulares_falla(
    contrato,
) -> None:
    """Una factura requiere al menos un destinatario."""

    with pytest.raises(
        FacturacionError,
        match="titular",
    ):
        componer_destinatario(contrato)


def test_preparar_periodo_facturacion_reconoce_factura_emitida(
    session,
    contrato,
) -> None:
    """Asocia a la preparación una factura ya emitida del período."""

    _anadir_titular(
        contrato,
        nombre="Ana Pérez",
        nif="11111111A",
    )

    contrato.genera_factura = True
    contrato.iva_porcentaje = 2100
    contrato.retencion_porcentaje = 1900
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    session.add(factura)
    session.commit()

    # cambiamos los datos para comprobar que se muestran los datos de la factura ya
    # emitida, no los nuevos datos calculados
    contrato.iva_porcentaje = 1000
    contrato.retencion_porcentaje = 0
    session.commit()

    preparacion = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    assert len(preparacion.locales) == 1

    local = preparacion.locales[0]

    assert local.contrato is contrato
    assert local.factura is factura
    assert local.numero_factura == factura.numero_factura

    assert local.base == factura.base
    assert local.iva_importe == 21000
    assert local.retencion_importe == 19000
    assert local.total == 102000


def test_preparar_periodo_facturacion_no_consume_numero_factura(
    session,
    contrato,
) -> None:
    """Preparar varias veces el período no consume números de factura."""

    _anadir_titular(contrato)

    contrato.genera_factura = True
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    session.commit()

    facturas_antes = session.query(Factura).count()

    primera = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    segunda = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    assert len(primera.locales) == 1
    assert len(segunda.locales) == 1

    assert (
        primera.locales[0].numero_factura
        == segunda.locales[0].numero_factura
    )

    assert primera.locales[0].factura is None
    assert segunda.locales[0].factura is None

    assert session.query(Factura).count() == facturas_antes


def test_emitir_factura_prepara_operacion_completa(
    session,
    contrato,
) -> None:
    """Prepara factura, apunte y cobro previsto sin persistirlos."""

    categorias = {
        "ING_ALQUILERES": CategoriaContable(
            codigo="ING_ALQUILERES",
            naturaleza="INGRESO",
            nombre="Alquileres",
            activa=True,
            subcategorias=(),
        ),
    }

    _anadir_titular(
        contrato,
        nombre="Ana Pérez",
        nif="11111111A",
    )

    contrato.genera_factura = True
    contrato.iva_porcentaje = 2100
    contrato.retencion_porcentaje = 1900
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    session.commit()

    factura, apunte, movimiento = emitir_factura(
        contrato=contrato,
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
        categorias=categorias,
    )

    assert factura.id is None
    assert apunte.id is None
    assert movimiento.id is None

    assert factura.contrato is contrato
    assert factura.periodo == date(2026, 10, 1)
    assert factura.fecha_emision == date(2026, 10, 1)
    assert factura.estado == "EMITIDA"

    assert len(factura.lineas) == 1
    assert factura.lineas[0].tipo == "RENTA"
    assert factura.lineas[0].importe == 100000

    assert factura.base == 100000
    assert factura.iva_importe == 21000
    assert factura.retencion_importe == 19000
    assert factura.total == 102000

    assert apunte.inmueble is contrato.inmueble
    assert apunte.referencia_documento == factura.numero_factura
    assert apunte.total == factura.total

    assert movimiento.apunte is apunte
    assert movimiento.contrato is contrato
    assert movimiento.inmueble is contrato.inmueble
    assert movimiento.importe_esperado == factura.total
    assert movimiento.estado == "PENDIENTE"


def test_emitir_factura_rechaza_periodo_ya_facturado(
    session,
    contrato,
) -> None:
    """No permite emitir dos facturas ordinarias del mismo período."""

    categorias = {
        "ING_ALQUILERES": CategoriaContable(
            codigo="ING_ALQUILERES",
            naturaleza="INGRESO",
            nombre="Alquileres",
            activa=True,
            subcategorias=(),
        ),
    }

    _anadir_titular(contrato)

    contrato.genera_factura = True
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    session.add(factura)
    session.commit()

    with pytest.raises(
        FacturacionError,
        match="Ya existe",
    ):
        emitir_factura(
            contrato=contrato,
            periodo=date(2026, 10, 1),
            fecha_emision=date(2026, 10, 1),
            categorias=categorias,
        )



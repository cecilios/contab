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
    FacturaDestinatario,
    FacturaLinea,
    Inmueble,
    Inquilino,
    MovimientoPrevisto,
    RentaContrato,
    RevisionRenta,
)
from contab.facturacion.services import (
    CalculoFacturaError,
    FacturacionError,
    FacturaEditada,
    FacturaPreparada,
    LineaFacturaEditada,
    LineaFacturaPreparada,
    RepercusionGasto,
    calcular_importes_factura,
    componer_destinatario,
    contabilizar_ingreso_sin_factura,
    crear_factura,
    emitir_factura,
    notas_automaticas_factura,
    notas_revision_factura,
    preparar_datos_documento_factura,
    preparar_eliminacion_factura,
    preparar_periodo_facturacion,
    preparar_reapertura_revision,
    preparar_registro_contable_factura,
    preparar_revisiones_renta,
    reabrir_revision_renta,
    siguiente_numero_factura,
)
from contab.contratos.services import (
    resolver_revision_renta,
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


def _crear_factura_persistida(
    contrato: Contrato,
    **cambios,
) -> Factura:
    """Crea una factura válida para tests de facturación."""

    datos = {
        "contrato": contrato,
        "numero_secuencia": 1,
        "anio": 2026,
        "numero_factura": "01/2026A1",
        "fecha_emision": date(2026, 2, 1),
        "periodo": date(2026, 2, 1),
        "referencia_inmueble": contrato.inmueble.referencia,
        "descripcion_inmueble": contrato.inmueble.descripcion,
        "direccion_facturacion": contrato.direccion_facturacion,
        "codigo_postal_facturacion": (
            contrato.codigo_postal_facturacion
        ),
        "poblacion_facturacion": contrato.poblacion_facturacion,
        "provincia_facturacion": contrato.provincia_facturacion,
        "base": 100000,
        "iva_porcentaje": 0,
        "iva_importe": 0,
        "retencion_porcentaje": 0,
        "retencion_importe": 0,
        "total": 100000,
    }

    datos.update(cambios)

    return Factura(**datos)


def _emitir_factura_para_eliminacion(
    session,
    contrato,
    categorias,
    *,
    periodo=date(2026, 10, 1),
):
    """Crea y persiste una factura ordinaria con apunte y movimiento."""

    factura, apunte, movimiento = emitir_factura(
        contrato=contrato,
        periodo=periodo,
        fecha_emision=periodo,
        categorias=categorias,
    )

    session.add_all(
        [
            factura,
            apunte,
            movimiento,
        ]
    )
    session.commit()

    return factura, apunte, movimiento



def test_primera_factura_del_ano_comienza_en_uno(contrato) -> None:
    """Comprueba que la primera factura anual de un inmueble tiene secuencia 1."""
    secuencia, numero = siguiente_numero_factura(contrato, 2026)

    assert secuencia == 1
    assert numero == "01/2026A1"


def test_siguiente_factura_incrementa_secuencia(session, contrato) -> None:
    """Comprueba que la numeración continúa después de la última factura."""

    factura = _crear_factura_persistida(contrato)
    session.add(factura)
    session.commit()

    secuencia, numero = siguiente_numero_factura(contrato, 2026)

    assert secuencia == 2
    assert numero == "02/2026A1"


def test_numeracion_se_reinicia_cada_ano(session, contrato) -> None:
    """Comprueba que cada inmueble reinicia su secuencia al cambiar de año."""

    factura = _crear_factura_persistida(
        contrato,
        numero_secuencia=7,
        numero_factura="07/2026A1",
        fecha_emision=date(2026, 12, 1),
        periodo=date(2026, 12, 1),
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

    factura = _crear_factura_persistida(
        contrato_anterior,
        numero_secuencia=6,
        numero_factura="06/2026A1",
        fecha_emision=date(2026, 6, 1),
        periodo=date(2026, 6, 1),
    )

    session.add_all([contrato_anterior, contrato_nuevo, factura])
    session.commit()

    secuencia, numero = siguiente_numero_factura(contrato_nuevo, 2026)

    assert secuencia == 7
    assert numero == "07/2026A1"


def test_factura_anulada_sigue_consumiento_numero(session, contrato) -> None:
    """Comprueba que una factura anulada no libera su número de secuencia."""

    factura = _crear_factura_persistida(
        contrato,
        estado="ANULADA",
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
            concepto="Alquiler",
            importe=100000,
        )
    ]

    calculo = calcular_importes_factura(
        importes=[
            linea.importe
            for linea in lineas
        ],
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
            concepto="Alquiler",
            importe=100000,
        )
    ]

    calculo = calcular_importes_factura(
        importes=[
            linea.importe
            for linea in lineas
        ],
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
            concepto="Alquiler",
            importe=100000,
        ),
        FacturaLinea(
            orden=2,
            concepto="Diferencia revisión",
            importe=2300,
        ),
        FacturaLinea(
            orden=3,
            concepto="Agua",
            importe=8347,
        ),
    ]

    calculo = calcular_importes_factura(
        importes=[
            linea.importe
            for linea in lineas
        ],
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
            concepto="Alquiler",
            importe=100000,
        ),
        FacturaLinea(
            orden=2,
            concepto="Diferencia revisión",
            importe=-2500,
        ),
    ]

    calculo = calcular_importes_factura(
        importes=[
            linea.importe
            for linea in lineas
        ],
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
            concepto="Alquiler",
            importe=10001,
        )
    ]

    calculo = calcular_importes_factura(
        importes=[
            linea.importe
            for linea in lineas
        ],
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
            concepto="Diferencia revisión",
            importe=-10001,
        )
    ]

    with pytest.raises(CalculoFacturaError):
        calcular_importes_factura(
            importes=[
                linea.importe
                for linea in lineas
            ],
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
        )


def test_calcular_factura_redondea_iva_hacia_arriba() -> None:
    """Comprueba el redondeo del IVA hacia arriba al superar medio céntimo."""
    lineas = [
        FacturaLinea(
            orden=1,
            concepto="Alquiler",
            importe=10001,
        )
    ]

    calculo = calcular_importes_factura(
        importes=[
            linea.importe
            for linea in lineas
        ],
        iva_porcentaje=5000,
        retencion_porcentaje=0,
    )

    assert calculo.iva_importe == 5001


def test_calcular_factura_redondea_iva_hacia_abajo() -> None:
    """Comprueba el redondeo del IVA hacia abajo por debajo de medio céntimo."""
    lineas = [
        FacturaLinea(
            orden=1,
            concepto="Alquiler",
            importe=10001,
        )
    ]

    calculo = calcular_importes_factura(
        importes=[
            linea.importe
            for linea in lineas
        ],
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
            concepto="Alquiler",
            importe=10001,
        )
    ]

    calculo = calcular_importes_factura(
        importes=[
            linea.importe
            for linea in lineas
        ],
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
            concepto="Alquiler",
            importe=100000,
        )
    ]

    with pytest.raises(CalculoFacturaError):
        calcular_importes_factura(
            importes=[
                linea.importe
                for linea in lineas
            ],
            iva_porcentaje=-1,
            retencion_porcentaje=0,
        )


def test_calcular_factura_rechaza_retencion_negativa() -> None:
    """Comprueba que el porcentaje de retención no puede ser negativo."""
    lineas = [
        FacturaLinea(
            orden=1,
            concepto="Alquiler",
            importe=100000,
        )
    ]

    with pytest.raises(CalculoFacturaError):
        calculo = calcular_importes_factura(
            importes=[
                linea.importe
                for linea in lineas
            ],
            iva_porcentaje=0,
            retencion_porcentaje=-1,
        )


def test_calcular_factura_admite_base_cero() -> None:
    """Comprueba que una factura con base cero produce importes nulos."""
    lineas = [
        FacturaLinea(
            orden=1,
            concepto="Alquiler",
            importe=0,
        )
    ]

    calculo = calcular_importes_factura(
        importes=[
            linea.importe
            for linea in lineas
        ],
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
    assert preparacion.otros[0].destinatario_nombre == "Ana Pérez"

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
    assert local.lineas == (
        LineaFacturaPreparada(
            concepto=(
                f"{contrato.concepto_factura.rstrip('.')}. "
                "Octubre de 2026"
            ),
            importe=100000,
        ),
    )

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
    _anadir_titular(
        contrato,
        nombre="Ana Pérez",
        nif="11111111A",
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


def test_preparar_periodo_facturacion_indica_revision_pendiente(
    session,
    contrato,
) -> None:
    """Indica pendiente cuando ya ha pasado el mes previsto de revisión."""

    _anadir_titular(contrato)

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
        estado="PENDIENTE",
    )

    session.add(revision)
    session.commit()

    preparacion = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 11, 1),
        fecha_emision=date(2026, 11, 1),
    )

    local = preparacion.locales[0]

    assert local.revision is revision
    assert local.revision_estado == "PENDIENTE"


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
    concepto_emitido = contrato.concepto_factura

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
    contrato.concepto_factura = "Concepto modificado"
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
    assert local.lineas == (
        LineaFacturaPreparada(
            concepto=concepto_emitido,
            importe=100000,
        ),
    )
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


def test_preparar_periodo_facturacion_avisa_revision_del_mes_siguiente(
    session,
    contrato,
) -> None:
    """Muestra aviso cuando hay una revisión pendiente el mes siguiente."""

    _anadir_titular(contrato)

    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 11, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add(revision)
    session.commit()

    preparacion = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    assert len(preparacion.locales) == 1
    assert preparacion.locales[0].revision is revision
    assert preparacion.locales[0].revision_estado == "AVISO"


def test_preparar_periodo_facturacion_no_avisa_revision_resuelta(
    session,
    contrato,
) -> None:
    """No muestra aviso para una revisión que ya no está pendiente."""

    _anadir_titular(contrato)

    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    contrato.revisiones_renta.append(
        RevisionRenta(
            fecha_prevista=date(2026, 11, 1),
            metodo="IPC_NACIONAL",
            estado="NO_APLICADA",
        )
    )

    session.commit()

    preparacion = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    assert preparacion.locales[0].revision is None
    assert preparacion.locales[0].revision_estado is None


def test_preparar_periodo_facturacion_indica_espera_del_indice(
    session,
    contrato,
) -> None:
    """Indica espera cuando la revisión pendiente corresponde al período."""

    _anadir_titular(contrato)

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
        estado="PENDIENTE",
    )

    session.add(revision)
    session.commit()

    preparacion = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    local = preparacion.locales[0]

    assert local.revision is revision
    assert local.revision_estado == "ESPERANDO_INDICE"


def test_preparar_periodo_facturacion_otro_no_contabilizado(
    session,
    contrato,
) -> None:
    """Un ingreso sin apunte asociado sigue pendiente de contabilizar."""

    _anadir_titular(contrato)

    contrato.genera_factura = False
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=80000,
        )
    )

    session.commit()

    preparacion = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    assert len(preparacion.otros) == 1

    ingreso = preparacion.otros[0]

    assert ingreso.contrato is contrato
    assert ingreso.movimiento is None


def test_preparar_periodo_facturacion_reconoce_otro_contabilizado(
    session,
    contrato,
) -> None:
    """Reconoce un ingreso ya contabilizado del contrato y período."""

    _anadir_titular(contrato)

    contrato.genera_factura = False
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=80000,
        )
    )

    apunte = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler",
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 10, 31),
        tratamiento="CONTABILIZAR",
        base=80000,
        iva_importe=0,
        retencion_importe=0,
        total=80000,
    )

    movimiento = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        apunte=apunte,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 31),
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=80000,
        estado="PENDIENTE",
    )

    session.add(movimiento)
    session.commit()

    preparacion = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    assert len(preparacion.otros) == 1
    assert preparacion.otros[0].movimiento is movimiento


def test_preparar_periodo_facturacion_no_confunde_otro_de_otro_mes(
    session,
    contrato,
) -> None:
    """Un ingreso contabilizado de septiembre no resuelve octubre."""

    _anadir_titular(contrato)

    contrato.genera_factura = False
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=80000,
        )
    )

    apunte = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 9, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler",
        periodo_desde=date(2026, 9, 1),
        periodo_hasta=date(2026, 9, 30),
        tratamiento="CONTABILIZAR",
        base=80000,
        iva_importe=0,
        retencion_importe=0,
        total=80000,
    )

    movimiento = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        apunte=apunte,
        fecha_prevista_desde=date(2026, 9, 1),
        fecha_prevista_hasta=date(2026, 9, 30),
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=80000,
        estado="PENDIENTE",
    )

    session.add(movimiento)
    session.commit()

    preparacion = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    assert len(preparacion.otros) == 1
    assert preparacion.otros[0].movimiento is None


def test_contabilizar_ingreso_sin_factura_prepara_operacion_completa(
    session,
    contrato,
) -> None:
    """Prepara apunte y cobro previsto de un alquiler sin factura."""

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

    contrato.genera_factura = False
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=80000,
        )
    )

    session.commit()

    apunte, movimiento = contabilizar_ingreso_sin_factura(
        contrato=contrato,
        periodo=date(2026, 10, 1),
        fecha=date(2026, 10, 1),
        categorias=categorias,
    )

    assert apunte.id is None
    assert apunte.inmueble is contrato.inmueble
    assert apunte.fecha == date(2026, 10, 1)
    assert apunte.naturaleza == "INGRESO"
    assert apunte.categoria == "ING_ALQUILERES"
    assert apunte.concepto == contrato.concepto_factura

    assert apunte.periodo_desde == date(2026, 10, 1)
    assert apunte.periodo_hasta == date(2026, 10, 31)

    assert apunte.base == 80000
    assert apunte.iva_importe == 0
    assert apunte.retencion_importe == 0
    assert apunte.total == 80000

    assert apunte.tercero_nombre == "Ana Pérez"
    assert apunte.tercero_nif == "11111111A"
    assert apunte.referencia_documento == ""

    assert movimiento.id is None
    assert movimiento.apunte is apunte
    assert movimiento.contrato is contrato
    assert movimiento.inmueble is contrato.inmueble

    assert movimiento.naturaleza == "INGRESO"
    assert movimiento.importe_esperado == 80000
    assert movimiento.fecha_prevista_desde == date(2026, 10, 1)
    assert movimiento.fecha_prevista_hasta == date(2026, 10, 31)


def test_contabilizar_ingreso_sin_factura_rechaza_duplicado(
    session,
    contrato,
) -> None:
    """Impide contabilizar dos veces el mismo contrato y período."""

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

    contrato.genera_factura = False
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=80000,
        )
    )

    apunte = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler",
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 10, 31),
        tratamiento="CONTABILIZAR",
        base=80000,
        iva_importe=0,
        retencion_importe=0,
        total=80000,
    )

    movimiento = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        apunte=apunte,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 31),
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=80000,
        estado="PENDIENTE",
    )

    session.add(movimiento)
    session.commit()

    with pytest.raises(
        FacturacionError,
        match="contabilizado",
    ):
        contabilizar_ingreso_sin_factura(
            contrato=contrato,
            periodo=date(2026, 10, 1),
            fecha=date(2026, 10, 1),
            categorias=categorias,
        )


def test_notas_automaticas_factura_no_anade_nota_otra_retencion() -> None:
    """No añade la nota de no residente para otra retención."""

    notas = notas_automaticas_factura(
        retencion_porcentaje=1900,
        revision=None,
        revision_estado=None,
    )

    assert notas == []


def test_notas_automaticas_factura_anade_nota_retencion_24() -> None:
    """Añade la nota de no residente para una retención del 24 %."""

    notas = notas_automaticas_factura(
        retencion_porcentaje=2400,
        revision=None,
        revision_estado=None,
    )

    assert notas == [
        (
            "Se aplica el 24% de retención por ser el emisor "
            "no residente en la UE ni el EEE"
        ),
    ]


def test_crear_factura_usa_datos_editados() -> None:
    """Crea una factura con las líneas y porcentajes editados."""

    inmueble = Inmueble(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="A1",
        descripcion="Local comercial",
        direccion="Dirección de prueba",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_vencimiento=date(2030, 12, 31),
        genera_factura=True,
        fecha_inicio_facturacion=date(2026, 1, 1),
        fianza=100000,
        iva_porcentaje=1000,
        retencion_porcentaje=500,
        direccion_facturacion="Calle del Cliente 10",
        codigo_postal_facturacion="36001",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler local",
    )

    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    factura_editada = FacturaEditada(
        lineas=[
            LineaFacturaEditada(
                concepto="Alquiler octubre",
                importe=100000,
            ),
            LineaFacturaEditada(
                concepto="Consumo de agua",
                importe=3500,
            ),
        ],
        notas=[
            "Primera nota de prueba.",
            "Segunda nota de prueba.",
        ],
        iva_porcentaje=2100,
        retencion_porcentaje=1900,
        base=103500,
        iva_importe=21735,
        retencion_importe=19665,
        total=105570,
    )

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
        factura_editada=factura_editada,
    )

    assert len(factura.lineas) == 2

    assert factura.lineas[0].orden == 1
    assert factura.lineas[0].concepto == "Alquiler octubre"
    assert factura.lineas[0].importe == 100000

    assert factura.lineas[1].orden == 2
    assert factura.lineas[1].concepto == "Consumo de agua"
    assert factura.lineas[1].importe == 3500

    assert factura.base == 103500
    assert factura.iva_porcentaje == 2100
    assert factura.iva_importe == 21735
    assert factura.retencion_porcentaje == 1900
    assert factura.retencion_importe == 19665
    assert factura.total == 105570

    assert factura.notas == (
        "Primera nota de prueba.\n"
        "Segunda nota de prueba."
    )


def test_emitir_factura_usa_factura_editada(
    session,
    contrato,
) -> None:
    """Emite y contabiliza los datos de la factura editada."""

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

    # Deliberadamente distintos de los editados.
    contrato.iva_porcentaje = 1000
    contrato.retencion_porcentaje = 500

    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    session.commit()

    factura_editada = FacturaEditada(
        lineas=[
            LineaFacturaEditada(
                concepto="Alquiler octubre",
                importe=100000,
            ),
            LineaFacturaEditada(
                concepto="Consumo de agua",
                importe=3500,
            ),
        ],
        notas=[
            "Primera nota de prueba.",
            "Segunda nota de prueba.",
        ],
        iva_porcentaje=2100,
        retencion_porcentaje=1900,
        base=103500,
        iva_importe=21735,
        retencion_importe=19665,
        total=105570,
    )

    factura, apunte, movimiento = emitir_factura(
        contrato=contrato,
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
        categorias=categorias,
        factura_editada=factura_editada,
    )

    assert factura.apunte_contable is apunte

    assert len(factura.lineas) == 2

    assert factura.lineas[0].orden == 1
    assert factura.lineas[0].concepto == "Alquiler octubre"
    assert factura.lineas[0].importe == 100000

    assert factura.lineas[1].orden == 2
    assert factura.lineas[1].concepto == "Consumo de agua"
    assert factura.lineas[1].importe == 3500

    assert factura.base == 103500
    assert factura.iva_porcentaje == 2100
    assert factura.iva_importe == 21735
    assert factura.retencion_porcentaje == 1900
    assert factura.retencion_importe == 19665
    assert factura.total == 105570

    assert factura.notas == (
        "Primera nota de prueba.\n"
        "Segunda nota de prueba."
    )

    assert apunte.base == 103500
    assert apunte.iva_importe == 21735
    assert apunte.retencion_importe == 19665
    assert apunte.total == 105570

    assert movimiento.importe_esperado == 105570
    assert movimiento.estado == "PENDIENTE"


def test_notas_revision_factura_avisa_revision_mes_siguiente() -> None:
    """Avisa de la revisión prevista para el mes siguiente."""

    revision = RevisionRenta(
        fecha_prevista=date(2026, 10, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    notas = notas_revision_factura(
        revision,
        "AVISO",
    )

    assert notas == [
        (
            "Según lo estipulado en el contrato, el próximo mes "
            "de octubre corresponde actualizar el alquiler "
            "conforme a la variación experimentada por el IPC "
            "General de Precios al Consumo en los últimos doce "
            "meses."
        ),
    ]


def test_notas_revision_factura_espera_indice() -> None:
    """Explica que se mantiene la renta mientras se espera el índice."""

    revision = RevisionRenta(
        fecha_prevista=date(2026, 10, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    notas = notas_revision_factura(
        revision,
        "ESPERANDO_INDICE",
    )

    assert notas == [
        (
            "Según lo estipulado en el contrato, corresponde este "
            "mes actualizar el alquiler conforme a la variación "
            "experimentada por el IPC General de Precios al "
            "Consumo en los últimos doce meses. Como dicho dato "
            "no está aún disponible, se mantiene en este mes el "
            "alquiler del año anterior. Se pasará la diferencia "
            "una vez que se conozca el dato del IPC General de "
            "Precios al Consumo."
        ),
    ]


def test_notas_revision_factura_revision_aplicada() -> None:
    """Explica la revisión aplicada y los atrasos del mes anterior."""

    revision = RevisionRenta(
        fecha_prevista=date(2026, 10, 1),
        fecha_resolucion=date(2026, 11, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=360,
    )

    notas = notas_revision_factura(
        revision,
        "APLICADA",
    )

    assert notas == [
        (
            "El IPC General de Precios al Consumo de octubre ha "
            "sido del 3,6%, por lo que se incrementa el alquiler "
            "en esta cuantía."
        ),
        (
            "Atrasos de Octubre 2026 por la actualización de "
            "renta, conforme se indicó en el recibo de dicho mes."
        ),
    ]


def test_notas_revision_factura_adapta_descripcion_del_indice() -> None:
    """Usa la denominación correspondiente al índice de revisión."""

    revision = RevisionRenta(
        fecha_prevista=date(2026, 8, 1),
        metodo="IPC_AUTONOMICO",
        estado="PENDIENTE",
    )

    notas = notas_revision_factura(
        revision,
        "AVISO",
    )

    assert notas == [
        (
            "Según lo estipulado en el contrato, el próximo mes "
            "de agosto corresponde actualizar el alquiler "
            "conforme a la variación experimentada por el IPC "
            "General de la Comunidad de Madrid en los últimos doce meses."
        ),
    ]


def test_notas_revision_factura_sin_revision() -> None:
    """No genera notas cuando no existe revisión de renta."""

    assert notas_revision_factura(
        None,
        None,
    ) == []


def test_preparar_periodo_facturacion_indica_revision_aplicada(
    session,
    contrato,
) -> None:
    """Indica la revisión aplicada durante el mes siguiente."""

    _anadir_titular(
        contrato,
        nombre="Ana Pérez",
        nif="11111111A",
    )

    contrato.genera_factura = True
    contrato.iva_porcentaje = 2100
    contrato.retencion_porcentaje = 1900

    contrato.rentas.extend(
        [
            RentaContrato(
                fecha_desde=contrato.fecha_inicio,
                importe=100000,
            ),
            RentaContrato(
                fecha_desde=date(2026, 10, 1),
                importe=103600,
            ),
        ]
    )

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 10, 1),
        fecha_resolucion=date(2026, 11, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=360,
    )

    session.add(revision)
    session.commit()

    preparacion = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 11, 1),
        fecha_emision=date(2026, 11, 1),
    )

    assert len(preparacion.locales) == 1

    local = preparacion.locales[0]

    assert local.revision is revision
    assert local.revision_estado == "APLICADA"

    assert local.lineas == (
        LineaFacturaPreparada(
            concepto="Alquiler. Noviembre de 2026",
            importe=103600,
        ),
        LineaFacturaPreparada(
            concepto=(
                "Atrasos de Octubre 2026 "
                "por actualización de renta"
            ),
            importe=3600,
        ),
    )

    assert local.base == 107200
    assert local.iva_importe == 22512
    assert local.retencion_importe == 20368
    assert local.total == 109344

    assert local.notas == (
        (
            "El IPC General de Precios al Consumo de octubre ha "
            "sido del 3,6%, por lo que se incrementa el alquiler "
            "en esta cuantía."
        ),
        (
            "Atrasos de Octubre 2026 por la actualización de "
            "renta, conforme se indicó en el recibo de dicho mes."
        ),
    )

    # Comprobar que al mes siguiente el estado de la revisión ya no muestra 'Aplicada'
    preparacion_diciembre = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 12, 1),
        fecha_emision=date(2026, 12, 1),
    )

    local_diciembre = preparacion_diciembre.locales[0]

    assert local_diciembre.revision is None
    assert local_diciembre.revision_estado is None
    assert local_diciembre.notas == ()
    assert len(local_diciembre.lineas) == 1


def test_preparar_periodo_facturacion_ordena_por_referencia(
    session,
) -> None:
    """Ordena locales y otros ingresos por referencia del inmueble."""

    def crear_contrato(
        referencia: str,
        *,
        genera_factura: bool,
    ) -> Contrato:
        inmueble = Inmueble(
            referencia=referencia,
            tipo="L",
            codigo_facturacion=referencia,
            descripcion=f"Inmueble {referencia}",
            direccion="Dirección de prueba",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        contrato = Contrato(
            inmueble=inmueble,
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=genera_factura,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            iva_porcentaje=2100 if genera_factura else 0,
            retencion_porcentaje=1900 if genera_factura else 0,
            direccion_facturacion="Dirección de prueba",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
        )

        contrato.titulares.append(
            ContratoInquilino(
                inquilino=Inquilino(
                    nombre=f"Inquilino {referencia}",
                    nif=f"NIF-{referencia}",
                ),
                orden=1,
            )
        )

        contrato.rentas.append(
            RentaContrato(
                fecha_desde=date(2026, 1, 1),
                importe=100000,
            )
        )

        session.add(contrato)

        return contrato

    local_c = crear_contrato(
        "LOCAL-C",
        genera_factura=True,
    )
    local_a = crear_contrato(
        "LOCAL-A",
        genera_factura=True,
    )
    local_b = crear_contrato(
        "LOCAL-B",
        genera_factura=True,
    )

    otro_c = crear_contrato(
        "OTRO-C",
        genera_factura=False,
    )
    otro_a = crear_contrato(
        "OTRO-A",
        genera_factura=False,
    )
    otro_b = crear_contrato(
        "OTRO-B",
        genera_factura=False,
    )

    session.flush()

    preparacion = preparar_periodo_facturacion(
        contratos=[
            local_c,
            otro_b,
            local_a,
            otro_c,
            local_b,
            otro_a,
        ],
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    assert [
        local.inmueble.referencia
        for local in preparacion.locales
    ] == [
        "LOCAL-A",
        "LOCAL-B",
        "LOCAL-C",
    ]

    assert [
        otro.inmueble.referencia
        for otro in preparacion.otros
    ] == [
        "OTRO-A",
        "OTRO-B",
        "OTRO-C",
    ]


def test_preparar_datos_documento_factura_conserva_titulares(
    contrato,
) -> None:
    """Conserva cada titular con su NIF y respeta su orden."""

    _anadir_titular(
        contrato,
        nombre="María López",
        nif="22222222B",
        orden=2,
    )
    _anadir_titular(
        contrato,
        nombre="Ana Pérez",
        nif="11111111A",
        orden=1,
    )

    factura = FacturaPreparada(
        contrato=contrato,
        inmueble=contrato.inmueble,
        referencia_inmueble=contrato.inmueble.referencia,
        descripcion_inmueble=contrato.inmueble.descripcion,
        destinatario_nombre="Ana Pérez / María López",
        destinatario_nif="11111111A / 22222222B",
        direccion_facturacion="Calle del Cliente 10",
        codigo_postal_facturacion="36001",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        lineas=(
            LineaFacturaPreparada(
                concepto="Alquiler local. Octubre de 2026",
                importe=100000,
            ),
        ),
        notas=(),
        base=100000,
        iva_importe=21000,
        retencion_importe=19000,
        total=102000,
        factura=None,
        numero_factura="01/2026A1",
        revision=None,
        revision_estado=None,
    )

    factura_editada = FacturaEditada(
        lineas=[
            LineaFacturaEditada(
                concepto="Alquiler local. Octubre de 2026",
                importe=100000,
            ),
        ],
        notas=[],
        iva_porcentaje=2100,
        retencion_porcentaje=1900,
        base=100000,
        iva_importe=21000,
        retencion_importe=19000,
        total=102000,
    )

    datos = preparar_datos_documento_factura(
        factura=factura,
        factura_editada=factura_editada,
        fecha_emision=date(2026, 10, 1),
        periodo=date(2026, 10, 1),
    )

    assert len(datos.destinatario.titulares) == 2

    assert datos.destinatario.titulares[0].nombre == (
        "Ana Pérez"
    )
    assert datos.destinatario.titulares[0].nif == (
        "11111111A"
    )

    assert datos.destinatario.titulares[1].nombre == (
        "María López"
    )
    assert datos.destinatario.titulares[1].nif == (
        "22222222B"
    )


def test_preparar_datos_documento_factura_emitida_usa_snapshot_historico(
    contrato,
) -> None:
    """Una factura emitida conserva sus destinatarios históricos."""

    inquilino = _anadir_titular(
        contrato,
        nombre="Cliente Actual",
        nif="99999999Z",
    )

    factura_persistida = _crear_factura_persistida(
        contrato,
        referencia_inmueble="LOCAL-HIST",
        descripcion_inmueble="Local histórico",
        direccion_facturacion="Dirección histórica",
        codigo_postal_facturacion="36001",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
    )

    factura_persistida.destinatarios.extend(
        [
            FacturaDestinatario(
                orden=1,
                nombre="Ana Histórica",
                nif="11111111A",
            ),
            FacturaDestinatario(
                orden=2,
                nombre="Luis Histórico",
                nif="22222222B",
            ),
        ]
    )

    preparada = FacturaPreparada(
        contrato=contrato,
        inmueble=contrato.inmueble,
        referencia_inmueble="LOCAL-HIST",
        descripcion_inmueble="Local histórico",
        destinatario_nombre=(
            "Ana Histórica / Luis Histórico"
        ),
        destinatario_nif=(
            "11111111A / 22222222B"
        ),
        direccion_facturacion="Dirección histórica",
        codigo_postal_facturacion="36001",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        lineas=(
            LineaFacturaPreparada(
                concepto="Alquiler histórico",
                importe=100000,
            ),
        ),
        notas=(),
        base=100000,
        iva_importe=21000,
        retencion_importe=19000,
        total=102000,
        factura=factura_persistida,
        numero_factura="01/2026A1",
        revision=None,
        revision_estado=None,
    )

    editada = FacturaEditada(
        lineas=[
            LineaFacturaEditada(
                concepto="Alquiler histórico",
                importe=100000,
            )
        ],
        notas=[],
        iva_porcentaje=2100,
        retencion_porcentaje=1900,
        base=100000,
        iva_importe=21000,
        retencion_importe=19000,
        total=102000,
    )

    # El contrato cambia después de emitirse la factura.
    inquilino.nombre = "Cliente Modificado"
    inquilino.nif = "88888888Y"

    datos = preparar_datos_documento_factura(
        factura=preparada,
        factura_editada=editada,
        periodo=date(2026, 2, 1),
        fecha_emision=date(2026, 2, 1),
    )

    assert datos.titulo == "Local histórico"
    assert datos.referencia_inmueble == "LOCAL-HIST"

    assert [
        (titular.nombre, titular.nif)
        for titular in datos.destinatario.titulares
    ] == [
        ("Ana Histórica", "11111111A"),
        ("Luis Histórico", "22222222B"),
    ]

    assert datos.destinatario.direccion == "Dirección histórica"
    assert datos.destinatario.codigo_postal == "36001"
    assert datos.destinatario.poblacion == "Pontevedra"
    assert datos.destinatario.provincia == "Pontevedra"


def test_crear_factura_conserva_snapshot_documental(
    contrato,
) -> None:

    _anadir_titular(
        contrato,
        nombre="Ana Pérez",
        nif="11111111A",
        orden=1,
    )

    _anadir_titular(
        contrato,
        nombre="Luis Pérez",
        nif="22222222B",
        orden=2,
    )

    contrato.inmueble.referencia = "LOCAL-1"
    contrato.inmueble.descripcion = "Local comercial"
    contrato.direccion_facturacion = "Calle Antigua 10"
    contrato.codigo_postal_facturacion = "36001"
    contrato.poblacion_facturacion = "Pontevedra"
    contrato.provincia_facturacion = "Pontevedra"
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=date(2026, 2, 1),
            importe=100000,
        )
    )

    factura = crear_factura(
        contrato=contrato,
        periodo=date(2026, 10, 1),
        fecha_emision=date(2026, 10, 1),
    )

    assert factura.referencia_inmueble == "LOCAL-1"
    assert factura.descripcion_inmueble == "Local comercial"

    assert factura.direccion_facturacion == (
        "Calle Antigua 10"
    )
    assert factura.codigo_postal_facturacion == "36001"
    assert factura.poblacion_facturacion == "Pontevedra"
    assert factura.provincia_facturacion == "Pontevedra"

    assert [
        (destinatario.nombre, destinatario.nif)
        for destinatario in factura.destinatarios
    ] == [
        ("Ana Pérez", "11111111A"),
        ("Luis Pérez", "22222222B"),
    ]


def test_preparar_periodo_con_factura_emitida_usa_snapshot_historico(
    session,
    contrato,
) -> None:
    """Una factura emitida se prepara desde su snapshot histórico."""

    inquilino = _anadir_titular(
        contrato,
        nombre="Cliente Histórico",
        nif="11111111A",
    )

    factura = _crear_factura_persistida(
        contrato,
        referencia_inmueble="LOCAL-HIST",
        descripcion_inmueble="Local histórico",
        direccion_facturacion="Dirección histórica",
        codigo_postal_facturacion="36001",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
    )

    factura.destinatarios.append(
        FacturaDestinatario(
            orden=1,
            nombre="Cliente Histórico",
            nif="11111111A",
        )
    )

    factura.lineas.append(
        FacturaLinea(
            orden=1,
            concepto="Alquiler histórico",
            importe=100000,
        )
    )

    session.add(factura)
    session.commit()

    # El contrato cambia después de emitir la factura.
    contrato.inmueble.referencia = "LOCAL-NUEVO"
    contrato.inmueble.descripcion = "Local nuevo"

    contrato.direccion_facturacion = "Dirección nueva"
    contrato.codigo_postal_facturacion = "99999"
    contrato.poblacion_facturacion = "Vigo"
    contrato.provincia_facturacion = "A Coruña"

    inquilino.nombre = "Cliente Nuevo"
    inquilino.nif = "99999999Z"

    session.commit()

    preparacion = preparar_periodo_facturacion(
        contratos=[contrato],
        periodo=date(2026, 2, 1),
        fecha_emision=date(2026, 2, 1),
    )

    assert len(preparacion.locales) == 1

    preparada = preparacion.locales[0]

    assert preparada.factura is factura
    assert preparada.numero_factura == "01/2026A1"

    assert preparada.destinatario_nombre == "Cliente Histórico"
    assert preparada.destinatario_nif == "11111111A"

    assert preparada.direccion_facturacion == "Dirección histórica"
    assert preparada.codigo_postal_facturacion == "36001"
    assert preparada.poblacion_facturacion == "Pontevedra"
    assert preparada.provincia_facturacion == "Pontevedra"

    assert preparada.lineas[0].concepto == "Alquiler histórico"
    assert preparada.lineas[0].importe == 100000

    assert preparada.referencia_inmueble == "LOCAL-HIST"
    assert preparada.descripcion_inmueble == "Local histórico"


def test_preparar_eliminacion_factura_devuelve_elementos_a_eliminar(
    session,
    contrato,
) -> None:
    """Prepara la eliminación completa de una factura pendiente de cobro."""

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

    session.commit()

    factura, apunte, movimiento = (
        _emitir_factura_para_eliminacion(
            session,
            contrato,
            categorias,
        )
    )

    eliminacion = preparar_eliminacion_factura(
        factura
    )

    assert eliminacion.factura is factura
    assert eliminacion.apunte is apunte
    assert eliminacion.movimiento is movimiento


def test_preparar_eliminacion_factura_sin_movimiento_previsto_es_valida(
    session,
    contrato,
) -> None:
    """Admite temporalmente una factura histórica sin movimiento previsto."""

    factura = _crear_factura_persistida(
        contrato,
    )

    apunte = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=factura.fecha_emision,
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        tratamiento="CONTABILIZAR",
        concepto="Apunte técnico",
        base=0,
        iva_importe=0,
        retencion_importe=0,
        total=0,
        tercero_nombre="",
        tercero_nif="",
        referencia_documento=factura.numero_factura,
    )

    factura.apunte_contable = apunte

    session.add(factura)
    session.commit()

    eliminacion = preparar_eliminacion_factura(
        factura
    )

    assert eliminacion.factura is factura
    assert eliminacion.apunte is apunte
    assert eliminacion.movimiento is None


def test_preparar_eliminacion_factura_rechaza_movimiento_parcial(
    session,
    contrato,
) -> None:
    """No permite eliminar una factura parcialmente conciliada."""

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

    session.commit()

    factura, _, movimiento = (
        _emitir_factura_para_eliminacion(
            session,
            contrato,
            categorias,
        )
    )

    movimiento.estado = "PARCIAL"
    session.commit()

    with pytest.raises(
        FacturacionError,
        match="parcial",
    ):
        preparar_eliminacion_factura(
            factura
        )


def test_preparar_eliminacion_factura_rechaza_movimiento_conciliado(
    session,
    contrato,
) -> None:
    """No permite eliminar una factura ya conciliada."""

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

    session.commit()

    factura, _, movimiento = (
        _emitir_factura_para_eliminacion(
            session,
            contrato,
            categorias,
        )
    )

    movimiento.estado = "CONCILIADO"
    session.commit()

    with pytest.raises(
        FacturacionError,
        match="conciliad",
    ):
        preparar_eliminacion_factura(
            factura
        )


def test_preparar_eliminacion_factura_rechaza_si_no_es_la_ultima_del_inmueble_y_ano(
    session,
    contrato,
) -> None:
    """Sólo puede eliminarse la última factura anual del inmueble."""

    factura_1 = _crear_factura_persistida(
        contrato,
        numero_secuencia=1,
        numero_factura="01/2026A1",
        periodo=date(2026, 2, 1),
        fecha_emision=date(2026, 2, 1),
    )

    factura_2 = _crear_factura_persistida(
        contrato,
        numero_secuencia=2,
        numero_factura="02/2026A1",
        periodo=date(2026, 3, 1),
        fecha_emision=date(2026, 3, 1),
    )

    session.add_all(
        [
            factura_1,
            factura_2,
        ]
    )
    session.commit()

    with pytest.raises(
        FacturacionError,
        match="última",
    ):
        preparar_eliminacion_factura(
            factura_1
        )


def test_preparar_eliminacion_factura_rechaza_factura_anulada(
    session,
    contrato,
) -> None:
    """Eliminar sólo se aplica a facturas emitidas."""

    factura = _crear_factura_persistida(
        contrato,
        estado="ANULADA",
    )

    session.add(factura)
    session.commit()

    with pytest.raises(
        FacturacionError,
        match="emitida",
    ):
        preparar_eliminacion_factura(
            factura
        )


def test_preparar_eliminacion_factura_rechaza_varios_movimientos_previstos(
    session,
    contrato,
) -> None:
    """No elimina automáticamente una factura con varios movimientos asociados."""

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

    session.commit()

    factura, apunte, _ = (
        _emitir_factura_para_eliminacion(
            session,
            contrato,
            categorias,
        )
    )

    apunte.movimientos_previstos.append(
        MovimientoPrevisto(
            inmueble=contrato.inmueble,
            contrato=contrato,
            fecha_prevista_desde=date(2026, 10, 1),
            fecha_prevista_hasta=date(2026, 10, 31),
            naturaleza="INGRESO",
            concepto="Segundo movimiento",
            importe_esperado=100000,
            contraparte="Ana Pérez",
            estado="PENDIENTE",
        )
    )

    session.commit()

    with pytest.raises(
        FacturacionError,
        match="más de un movimiento",
    ):
        preparar_eliminacion_factura(
            factura
        )


def test_preparar_revisiones_renta_obtiene_ultima_y_proxima(
    session,
    contrato,
) -> None:
    """Muestra la última revisión resuelta y la próxima pendiente."""

    revision_anterior = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2025, 10, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=320,
        fecha_resolucion=date(2025, 10, 15),
    )

    revision_proxima = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 10, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add_all(
        [
            revision_anterior,
            revision_proxima,
        ]
    )
    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 6, 1),
    )

    assert len(preparacion.locales) == 1
    assert preparacion.otros == ()

    preparada = preparacion.locales[0]

    assert preparada.contrato is contrato
    assert preparada.ultima_revision is revision_anterior
    assert preparada.proxima_revision is revision_proxima


def test_preparar_revisiones_renta_considera_no_aplicada_como_resuelta(
    session,
    contrato,
) -> None:
    """Una revisión no aplicada también cuenta como última revisión resuelta."""

    revision_anterior = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2025, 10, 1),
        metodo="IPC_NACIONAL",
        estado="NO_APLICADA",
        fecha_resolucion=date(2025, 10, 10),
    )

    revision_proxima = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 10, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add_all(
        [
            revision_anterior,
            revision_proxima,
        ]
    )
    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 6, 1),
    )

    preparada = preparacion.locales[0]

    assert preparada.ultima_revision is revision_anterior
    assert preparada.proxima_revision is revision_proxima


def test_preparar_revisiones_renta_admite_solo_revision_pendiente(
    session,
    contrato,
) -> None:
    """Un contrato puede no tener todavía ninguna revisión resuelta."""

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 10, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add(revision)
    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 6, 1),
    )

    preparada = preparacion.locales[0]

    assert preparada.ultima_revision is None
    assert preparada.proxima_revision is revision


def test_preparar_revisiones_renta_separa_y_ordena_por_inmueble(
    session,
    contrato,
) -> None:
    """Separa locales de otros contratos y ordena por referencia."""

    contrato.inmueble.referencia = "LOCAL-B"

    inmueble_local_a = Inmueble(
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="A2",
        descripcion="Local A",
        direccion="Dirección A",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato_local_a = Contrato(
        inmueble=inmueble_local_a,
        fecha_inicio=date(2026, 1, 1),
        fecha_vencimiento=date(2030, 12, 31),
        genera_factura=True,
        fecha_inicio_facturacion=date(2026, 1, 1),
        fianza=100000,
        direccion_facturacion="Dirección A",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )

    inmueble_otro = Inmueble(
        referencia="PISO-A",
        tipo="P",
        codigo_facturacion="B1",
        descripcion="Piso A",
        direccion="Dirección B",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato_otro = Contrato(
        inmueble=inmueble_otro,
        fecha_inicio=date(2026, 1, 1),
        fecha_vencimiento=date(2030, 12, 31),
        genera_factura=False,
        fecha_inicio_facturacion=date(2026, 1, 1),
        fianza=100000,
        direccion_facturacion="Dirección B",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )

    session.add_all(
        [
            contrato_local_a,
            contrato_otro,
        ]
    )
    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[
            contrato,
            contrato_otro,
            contrato_local_a,
        ],
        fecha=date(2026, 6, 1),
    )

    assert [
        item.contrato.inmueble.referencia
        for item in preparacion.locales
    ] == [
        "LOCAL-A",
        "LOCAL-B",
    ]

    assert [
        item.contrato.inmueble.referencia
        for item in preparacion.otros
    ] == [
        "PISO-A",
    ]


def test_preparar_revisiones_renta_excluye_contratos_inactivos(
    session,
    contrato,
) -> None:
    """No muestra contratos que ya han finalizado."""

    contrato.fecha_fin = date(2026, 5, 31)

    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 6, 1),
    )

    assert preparacion.locales == ()
    assert preparacion.otros == ()


def test_preparar_revisiones_renta_excluye_contratos_futuros(
    session,
    contrato,
) -> None:
    """No muestra contratos que todavía no han comenzado."""

    contrato.fecha_inicio = date(2026, 7, 1)
    contrato.fecha_inicio_facturacion = date(2026, 7, 1)

    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 6, 1),
    )

    assert preparacion.locales == ()
    assert preparacion.otros == ()


def test_preparar_revisiones_renta_sigue_esperando_indice_durante_el_mes(
    session,
    contrato,
) -> None:
    """Una revisión del mes actual espera índice durante todo el mes."""

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 10, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add(revision)
    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 10, 3),
    )

    preparada = preparacion.locales[0]

    assert preparada.proxima_revision is revision
    assert preparada.situacion_proxima == "ESPERANDO_INDICE"


def test_preparar_revisiones_renta_indica_aviso(
    session,
    contrato,
) -> None:
    """Indica aviso cuando la revisión corresponde al mes siguiente."""

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 11, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add(revision)
    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 10, 1),
    )

    preparada = preparacion.locales[0]

    assert preparada.proxima_revision is revision
    assert preparada.situacion_proxima == "AVISO"


def test_preparar_revisiones_renta_indica_esperando_indice(
    session,
    contrato,
) -> None:
    """Indica espera de índice cuando la revisión corresponde al mes actual."""

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 10, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add(revision)
    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 10, 1),
    )

    preparada = preparacion.locales[0]

    assert preparada.proxima_revision is revision
    assert preparada.situacion_proxima == "ESPERANDO_INDICE"


def test_preparar_revisiones_renta_indica_revision_a_resolver(
    session,
    contrato,
) -> None:
    """Indica que debe resolverse una revisión pendiente ya vencida."""

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 9, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add(revision)
    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 10, 1),
    )

    preparada = preparacion.locales[0]

    assert preparada.proxima_revision is revision
    assert preparada.situacion_proxima == "RESOLVER"


def test_preparar_revisiones_renta_indica_pendiente_fuera_del_ciclo(
    session,
    contrato,
) -> None:
    """Mantiene pendiente una revisión que todavía no entra en el ciclo."""

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 3, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add(revision)
    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 10, 1),
    )

    preparada = preparacion.locales[0]

    assert preparada.proxima_revision is revision
    assert preparada.situacion_proxima == "PENDIENTE"


def test_resolver_revision_renta_no_aplicada_crea_siguiente_revision(
    session,
    contrato,
) -> None:
    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 10, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add(revision)
    session.commit()

    nueva_renta, siguiente_revision = resolver_revision_renta(
        revision=revision,
        fecha_resolucion=date(2026, 10, 4),
        aplicar=False,
        porcentaje_aplicado=None,
    )

    assert nueva_renta is None

    assert revision.estado == "NO_APLICADA"
    assert revision.porcentaje_aplicado is None
    assert revision.fecha_resolucion == date(2026, 10, 4)

    assert siguiente_revision.fecha_prevista == date(2027, 10, 1)
    assert siguiente_revision.metodo == "IPC_NACIONAL"
    assert siguiente_revision.estado == "PENDIENTE"


def test_preparar_reapertura_revision_aplicada(
    session,
    contrato,
) -> None:
    """Prepara la reapertura de una revisión aplicada sin efectos posteriores."""

    renta_anterior = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2025, 1, 1),
        importe=100000,
    )

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    renta_revision = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 4, 1),
        importe=102000,
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add_all(
        [
            renta_anterior,
            revision,
            renta_revision,
            siguiente_revision,
        ]
    )
    session.commit()

    reapertura = preparar_reapertura_revision(
        revision
    )

    assert reapertura.revision is revision
    assert reapertura.renta is renta_revision
    assert reapertura.siguiente_revision is siguiente_revision


def test_preparar_reapertura_revision_requiere_aplicada(
    contrato,
) -> None:
    """Sólo puede reabrirse una revisión aplicada."""

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    with pytest.raises(
        FacturacionError,
        match="aplicada",
    ):
        preparar_reapertura_revision(
            revision
        )


def test_preparar_reapertura_revision_requiere_renta_generada(
    session,
    contrato,
) -> None:
    """Una revisión aplicada debe conservar la renta que generó."""

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add_all(
        [
            revision,
            siguiente_revision,
        ]
    )
    session.commit()

    with pytest.raises(
        FacturacionError,
        match="renta",
    ):
        preparar_reapertura_revision(
            revision
        )


def test_preparar_reapertura_revision_rechaza_factura_de_aplicacion(
    session,
    contrato,
) -> None:
    """La factura que materializa la revisión debe eliminarse primero."""

    renta_anterior = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2025, 1, 1),
        importe=100000,
    )

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    renta_revision = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 4, 1),
        importe=102000,
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    factura = _crear_factura_persistida(
        contrato,
        periodo=date(2026, 5, 1),
        fecha_emision=date(2026, 5, 1),
        revision_renta=revision,
    )

    session.add_all(
        [
            renta_anterior,
            revision,
            renta_revision,
            siguiente_revision,
            factura,
        ]
    )
    session.commit()

    with pytest.raises(
        FacturacionError,
        match="factura",
    ):
        preparar_reapertura_revision(
            revision
        )


def test_preparar_reapertura_revision_admite_factura_del_mes_previsto(
    session,
    contrato,
) -> None:
    """La factura del mes de revisión no impide reabrirla."""

    renta_anterior = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2025, 1, 1),
        importe=100000,
    )

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    renta_revision = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 4, 1),
        importe=102000,
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    factura_abril = _crear_factura_persistida(
        contrato,
        periodo=date(2026, 4, 1),
        fecha_emision=date(2026, 4, 1),
    )

    session.add_all(
        [
            renta_anterior,
            revision,
            renta_revision,
            siguiente_revision,
            factura_abril,
        ]
    )
    session.commit()

    reapertura = preparar_reapertura_revision(
        revision
    )

    assert reapertura.renta is renta_revision
    assert reapertura.siguiente_revision is siguiente_revision


def test_preparar_reapertura_revision_rechaza_factura_posterior(
    session,
    contrato,
) -> None:
    """No reabre una revisión cuando ya existe facturación posterior."""

    renta_anterior = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2025, 1, 1),
        importe=100000,
    )

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    renta_revision = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 4, 1),
        importe=102000,
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    factura_junio = _crear_factura_persistida(
        contrato,
        periodo=date(2026, 6, 1),
        fecha_emision=date(2026, 6, 1),
    )

    session.add_all(
        [
            renta_anterior,
            revision,
            renta_revision,
            siguiente_revision,
            factura_junio,
        ]
    )
    session.commit()

    with pytest.raises(
        FacturacionError,
        match="factura",
    ):
        preparar_reapertura_revision(
            revision
        )


def test_preparar_reapertura_revision_requiere_siguiente_pendiente(
    session,
    contrato,
) -> None:
    """No reabre una revisión si la revisión anual siguiente ya se resolvió."""

    renta_anterior = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2025, 1, 1),
        importe=100000,
    )

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    renta_revision = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 4, 1),
        importe=102000,
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=150,
        fecha_resolucion=date(2027, 5, 1),
    )

    session.add_all(
        [
            renta_anterior,
            revision,
            renta_revision,
            siguiente_revision,
        ]
    )
    session.commit()

    with pytest.raises(
        FacturacionError,
        match="revisión posterior",
    ):
        preparar_reapertura_revision(
            revision
        )


def test_preparar_reapertura_revision_requiere_siguiente_revision(
    session,
    contrato,
) -> None:
    """Una revisión aplicada debe conservar la revisión anual siguiente."""

    renta_anterior = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2025, 1, 1),
        importe=100000,
    )

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    renta_revision = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 4, 1),
        importe=102000,
    )

    session.add_all(
        [
            renta_anterior,
            revision,
            renta_revision,
        ]
    )
    session.commit()

    with pytest.raises(
        FacturacionError,
        match="revisión siguiente",
    ):
        preparar_reapertura_revision(
            revision
        )


def test_preparar_reapertura_revision_rechaza_apunte_de_aplicacion(
    session,
    contrato,
    categorias,
) -> None:
    """No reabre una revisión con efectos contables ya registrados."""

    _anadir_titular(contrato)

    contrato.genera_factura = False

    renta_anterior = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2025, 1, 1),
        importe=100000,
    )

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    renta_revision = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 4, 1),
        importe=102000,
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add_all(
        [
            renta_anterior,
            revision,
            renta_revision,
            siguiente_revision,
        ]
    )
    session.flush()

    apunte, movimiento = contabilizar_ingreso_sin_factura(
        contrato=contrato,
        periodo=date(2026, 5, 1),
        fecha=date(2026, 5, 1),
        categorias=categorias,
    )

    session.add_all(
        [
            apunte,
            movimiento,
        ]
    )
    session.commit()

    with pytest.raises(
        FacturacionError,
        match="apunte contable",
    ):
        preparar_reapertura_revision(
            revision
        )


def test_preparar_reapertura_revision_admite_apunte_del_mes_previsto(
    session,
    contrato,
    categorias,
) -> None:
    """El apunte anterior a la aplicación de la revisión no la bloquea."""

    _anadir_titular(contrato)

    contrato.genera_factura = False

    renta_anterior = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2025, 1, 1),
        importe=100000,
    )

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    renta_revision = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 4, 1),
        importe=102000,
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add_all(
        [
            renta_anterior,
            revision,
            renta_revision,
            siguiente_revision,
        ]
    )
    session.flush()

    apunte, movimiento = contabilizar_ingreso_sin_factura(
        contrato=contrato,
        periodo=date(2026, 4, 1),
        fecha=date(2026, 4, 1),
        categorias=categorias,
    )

    session.add_all(
        [
            apunte,
            movimiento,
        ]
    )
    session.commit()

    reapertura = preparar_reapertura_revision(
        revision
    )

    assert reapertura.revision is revision


def test_reabrir_revision_renta_restaurar_estado_pendiente(
    session,
    contrato,
) -> None:
    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    renta_revision = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 4, 1),
        importe=102000,
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add_all(
        [
            revision,
            renta_revision,
            siguiente_revision,
        ]
    )
    session.commit()

    reapertura = preparar_reapertura_revision(
        revision
    )

    reabrir_revision_renta(
        reapertura
    )

    assert revision.estado == "PENDIENTE"
    assert revision.porcentaje_aplicado is None
    assert revision.fecha_resolucion is None


def test_reabrir_revision_renta_no_elimina_objetos(
    session,
    contrato,
) -> None:
    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    renta_revision = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 4, 1),
        importe=102000,
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add_all(
        [
            revision,
            renta_revision,
            siguiente_revision,
        ]
    )
    session.commit()

    reapertura = preparar_reapertura_revision(
        revision
    )

    reabrir_revision_renta(
        reapertura
    )

    assert reapertura.renta in session
    assert reapertura.siguiente_revision in session


def test_preparar_revisiones_renta_indica_ultima_revision_reabrible(
    session,
    contrato,
) -> None:
    """Indica que la última revisión aplicada puede corregirse."""

    renta_anterior = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2025, 1, 1),
        importe=100000,
    )

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    renta_revision = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 4, 1),
        importe=102000,
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add_all(
        [
            renta_anterior,
            revision,
            renta_revision,
            siguiente_revision,
        ]
    )
    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 5, 15),
    )

    preparada = preparacion.locales[0]

    assert preparada.ultima_revision is revision
    assert preparada.ultima_revision_reabrible is True


def test_preparar_revisiones_renta_no_indica_reabrible_con_factura_afectada(
    session,
    contrato,
) -> None:
    """No ofrece corregir mientras exista una factura afectada por la revisión."""

    renta_anterior = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2025, 1, 1),
        importe=100000,
    )

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="APLICADA",
        porcentaje_aplicado=200,
        fecha_resolucion=date(2026, 5, 1),
    )

    renta_revision = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 4, 1),
        importe=102000,
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    factura = _crear_factura_persistida(
        contrato,
        periodo=date(2026, 5, 1),
        fecha_emision=date(2026, 5, 1),
        revision_renta=revision,
    )

    session.add_all(
        [
            renta_anterior,
            revision,
            renta_revision,
            siguiente_revision,
            factura,
        ]
    )
    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 5, 15),
    )

    preparada = preparacion.locales[0]

    assert preparada.ultima_revision is revision
    assert preparada.ultima_revision_reabrible is False


def test_preparar_revisiones_renta_no_indica_no_aplicada_como_reabrible(
    session,
    contrato,
) -> None:
    """Una revisión no aplicada no puede corregirse mediante reapertura."""

    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2026, 4, 1),
        metodo="IPC_NACIONAL",
        estado="NO_APLICADA",
        porcentaje_aplicado=None,
        fecha_resolucion=date(2026, 4, 15),
    )

    siguiente_revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 4, 1),
        metodo="IPC_NACIONAL",
        estado="PENDIENTE",
    )

    session.add_all(
        [
            revision,
            siguiente_revision,
        ]
    )
    session.commit()

    preparacion = preparar_revisiones_renta(
        contratos=[contrato],
        fecha=date(2026, 5, 15),
    )

    preparada = preparacion.locales[0]

    assert preparada.ultima_revision is revision
    assert preparada.ultima_revision_reabrible is False



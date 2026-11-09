
"""Pruebas del cálculo de la situación económica de un contrato."""

from datetime import date

from contab.contabilidad.situacion_contrato import (
    calcular_situacion_contrato,
)
from contab.models import (
    ApunteContable,
    Conciliacion,
    Contrato,
    Factura,
    MovimientoBancario,
    MovimientoPrevisto,
    SolicitudReembolso,
    SolicitudReembolsoLinea,
)


def crear_factura_prueba(
    session,
    contrato,
    *,
    numero,
    fecha,
    importe,
):
    """Registra una factura emitida con su cobro previsto."""

    apunte = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=fecha,
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto=f"Alquiler {numero}",
        base=importe,
        iva_importe=0,
        retencion_importe=0,
        total=importe,
    )

    factura = Factura(
        contrato=contrato,
        numero_secuencia=numero,
        anio=fecha.year,
        numero_factura=f"TEST-{fecha.year}-{numero}",
        referencia_inmueble=contrato.inmueble.referencia,
        descripcion_inmueble=contrato.inmueble.descripcion,
        direccion_facturacion=contrato.direccion_facturacion,
        poblacion_facturacion=contrato.poblacion_facturacion,
        provincia_facturacion=contrato.provincia_facturacion,
        apunte_contable=apunte,
        fecha_emision=fecha,
        periodo=fecha.replace(day=1),
        base=importe,
        iva_porcentaje=0,
        iva_importe=0,
        retencion_porcentaje=0,
        retencion_importe=0,
        total=importe,
        estado="EMITIDA",
    )

    previsto = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        apunte=apunte,
        naturaleza="INGRESO",
        concepto=apunte.concepto,
        importe_esperado=importe,
        fecha_prevista_desde=fecha,
        estado="PENDIENTE",
    )

    session.add_all([apunte, factura, previsto])
    session.flush()

    return factura, previsto


def registrar_cobro(
    session,
    previsto,
    *,
    fecha,
    importe,
    referencia,
    cerrar_diferencia=False,
):
    """Asocia un cobro bancario al movimiento previsto."""

    bancario = MovimientoBancario(
        fecha=fecha,
        naturaleza="INGRESO",
        importe=importe,
        tipo_original="TRANSFERENCIA",
        descripcion_original=f"Cobro {referencia}",
        huella_importacion=f"TEST-{referencia}",
        estado="CONCILIADO",
    )

    conciliacion = Conciliacion(
        movimiento_bancario=bancario,
        movimiento_previsto=previsto,
        importe_asociado=importe,
        cierra_previsto=cerrar_diferencia,
    )

    previsto.estado = (
        "CONCILIADO"
        if importe == previsto.importe_esperado
        or cerrar_diferencia
        else "PARCIAL"
    )

    session.add_all([bancario, conciliacion])
    session.flush()

    return bancario


def test_factura_y_cobro_parcial_con_diferencia_aceptada(
    session,
    contrato,
):
    """Una diferencia aceptada no elimina la deuda económica."""

    # El usuario emite una factura de 1.000 euros.
    factura, previsto = crear_factura_prueba(
        session,
        contrato,
        numero=1,
        fecha=date(2026, 10, 1),
        importe=100000,
    )

    # El banco registra un cobro de 900 euros.
    # El usuario acepta la diferencia de 100 euros
    # y cierra la conciliación.
    registrar_cobro(
        session,
        previsto,
        fecha=date(2026, 10, 5),
        importe=90000,
        referencia="OCTUBRE",
        cerrar_diferencia=True,
    )

    session.commit()

    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    assert situacion.saldo_anterior == 0
    assert situacion.total_exigible == 100000
    assert situacion.total_cobrado == 90000
    assert situacion.saldo == 10000

    # La factura y su apunte contable representan
    # una única obligación, no dos.
    assert len(situacion.exigibles) == 1
    assert situacion.exigibles[0].importe == 100000
    assert situacion.exigibles[0].fecha == date(2026, 10, 1)

    assert len(situacion.cobros) == 1
    assert situacion.cobros[0].importe == 90000
    assert situacion.cobros[0].fecha == date(2026, 10, 5)


def test_cobro_conciliado_manualmente(
    session,
    contrato,
):
    """El cobro manual usa el importe y la fecha previstos."""

    # El usuario emite una factura de 750 euros.
    _, previsto = crear_factura_prueba(
        session,
        contrato,
        numero=2,
        fecha=date(2026, 9, 1),
        importe=75000,
    )

    # El usuario indica que cobró el importe fuera
    # de la cuenta bancaria importada.
    previsto.fecha_prevista_desde = date(2026, 9, 4)
    previsto.estado = "CONCILIADO"
    previsto.metodo_conciliacion = "MANUAL"
    previsto.notas = "Cobrado en efectivo"

    session.commit()

    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 9, 30),
    )

    assert situacion.total_exigible == 75000
    assert situacion.total_cobrado == 75000
    assert situacion.saldo == 0

    assert len(situacion.cobros) == 1
    assert situacion.cobros[0].fecha == date(2026, 9, 1)
    assert situacion.cobros[0].importe == 75000


def test_saldo_anterior_y_fecha_de_corte(
    session,
    contrato,
):
    """El saldo histórico se calcula sin guardarlo en la BD."""

    # El contrato ya estaba vigente durante 2025.
    contrato.fecha_inicio = date(2025, 1, 1)
    contrato.fecha_inicio_facturacion = date(2025, 1, 1)
    session.flush()

    # En diciembre de 2025 se emite una factura
    # de 1.000 euros y solamente se cobran 800.
    _, previsto_2025 = crear_factura_prueba(
        session,
        contrato,
        numero=3,
        fecha=date(2025, 12, 1),
        importe=100000,
    )

    registrar_cobro(
        session,
        previsto_2025,
        fecha=date(2025, 12, 5),
        importe=80000,
        referencia="DICIEMBRE-2025",
    )

    # En enero de 2026 se emite otra factura
    # de 1.000 euros y se cobran 900.
    _, previsto_2026 = crear_factura_prueba(
        session,
        contrato,
        numero=4,
        fecha=date(2026, 1, 1),
        importe=100000,
    )

    registrar_cobro(
        session,
        previsto_2026,
        fecha=date(2026, 1, 5),
        importe=90000,
        referencia="ENERO-2026",
    )

    # Se registra también un cobro posterior
    # a la fecha de corte: no debe incluirse.
    registrar_cobro(
        session,
        previsto_2026,
        fecha=date(2026, 2, 10),
        importe=10000,
        referencia="FEBRERO-2026",
    )

    session.commit()

    # El usuario consulta su situación a 31 de enero.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 1, 31),
    )

    assert situacion.saldo_anterior == 20000
    assert situacion.total_exigible == 100000
    assert situacion.total_cobrado == 90000
    assert situacion.saldo == 30000

    assert len(situacion.exigibles) == 1
    assert len(situacion.cobros) == 1
    assert situacion.cobros[0].fecha == date(2026, 1, 5)


def test_no_se_cuentan_cobros_sin_atribuir(
    session,
    contrato,
):
    """Un movimiento bancario no atribuido no es un cobro del contrato."""

    # El usuario emite una factura de 1.000 euros.
    crear_factura_prueba(
        session,
        contrato,
        numero=5,
        fecha=date(2026, 8, 1),
        importe=100000,
    )

    # El banco importa un ingreso de 1.000 euros,
    # pero todavía no está conciliado ni atribuido.
    bancario = MovimientoBancario(
        fecha=date(2026, 8, 3),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Ingreso sin identificar",
        huella_importacion="TEST-SIN-ATRIBUIR",
        estado="PENDIENTE",
    )

    session.add(bancario)
    session.commit()

    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 8, 31),
    )

    assert situacion.total_exigible == 100000
    assert situacion.total_cobrado == 0
    assert situacion.saldo == 100000
    assert situacion.cobros == []


def test_alquiler_sin_factura(
    session,
    contrato,
):
    """Un alquiler sin factura también genera deuda exigible."""

    # El usuario tiene un contrato que no requiere factura.
    contrato.genera_factura = False

    # El usuario contabiliza el alquiler de octubre
    # por un importe de 850 euros.
    apunte = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler octubre 2026",
        periodo_desde=date(2026, 10, 1),
        periodo_hasta=date(2026, 10, 31),
        dia_hasta_incluido=True,
        base=85000,
        iva_importe=0,
        retencion_importe=0,
        total=85000,
    )

    previsto = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        apunte=apunte,
        naturaleza="INGRESO",
        concepto="Alquiler octubre 2026",
        importe_esperado=85000,
        fecha_prevista_desde=date(2026, 10, 1),
        estado="PENDIENTE",
    )

    session.add_all([apunte, previsto])
    session.flush()

    # El inquilino paga 600 euros el 5 de octubre.
    registrar_cobro(
        session,
        previsto,
        fecha=date(2026, 10, 5),
        importe=60000,
        referencia="ALQUILER-SIN-FACTURA",
    )

    session.commit()

    # El usuario consulta la situación del contrato.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    # El alquiler es exigible aunque no exista factura.
    assert situacion.total_exigible == 85000

    # Se descuentan exclusivamente los 600 euros cobrados.
    assert situacion.total_cobrado == 60000
    assert situacion.saldo == 25000

    # La pantalla presenta una obligación y un cobro.
    assert len(situacion.exigibles) == 1
    assert len(situacion.cobros) == 1

    assert situacion.exigibles[0].fecha == date(2026, 10, 1)
    assert situacion.exigibles[0].importe == 85000
    assert situacion.cobros[0].fecha == date(2026, 10, 5)


def test_reembolso_exigible_desde_fecha_envio(
    session,
    contrato,
):
    """El reembolso se cuenta una sola vez desde su envío."""

    # El propietario registra un gasto de agua de 130 euros.
    gasto = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 9, 20),
        naturaleza="GASTO",
        categoria="GAS_AGUA",
        concepto="Agua julio-septiembre",
        tratamiento="REPERCUTIR",
        base=13000,
        iva_importe=0,
        retencion_importe=0,
        total=13000,
    )

    # El usuario envía al inquilino una solicitud
    # de reembolso el 1 de octubre.
    solicitud = SolicitudReembolso(
        contrato=contrato,
        fecha_envio=date(2026, 10, 1),
    )

    solicitud.lineas.append(
        SolicitudReembolsoLinea(
            apunte=gasto,
            concepto="Agua julio-septiembre",
            importe=13000,
        )
    )

    # La solicitud genera un movimiento previsto
    # de ingreso, asociado al mismo contrato.
    previsto = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        solicitud_reembolso=solicitud,
        naturaleza="INGRESO",
        concepto="Reembolso de agua",
        importe_esperado=13000,
        estado="PENDIENTE",
    )

    session.add_all([gasto, solicitud, previsto])
    session.flush()

    # El inquilino abona 50 euros el 5 de octubre.
    registrar_cobro(
        session,
        previsto,
        fecha=date(2026, 10, 5),
        importe=5000,
        referencia="REEMBOLSO-AGUA",
    )

    session.commit()

    # El usuario consulta la situación antes del envío.
    situacion_anterior = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 9, 30),
    )

    assert situacion_anterior.total_exigible == 0
    assert situacion_anterior.total_cobrado == 0
    assert situacion_anterior.saldo == 0

    # El usuario consulta la situación después
    # del envío y del cobro parcial.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    # El gasto original no se suma a la solicitud.
    assert situacion.total_exigible == 13000
    assert situacion.total_cobrado == 5000
    assert situacion.saldo == 8000

    # El reembolso aparece una sola vez como exigible.
    assert len(situacion.exigibles) == 1
    assert situacion.exigibles[0].fecha == date(2026, 10, 1)
    assert situacion.exigibles[0].importe == 13000

    # El cobro aparece con la fecha bancaria.
    assert len(situacion.cobros) == 1
    assert situacion.cobros[0].fecha == date(2026, 10, 5)
    assert situacion.cobros[0].importe == 5000


def test_reembolso_negativo_reduce_saldo(
    session,
    contrato,
):
    """Una solicitud negativa reduce la deuda del inquilino."""

    # El usuario registra una devolución de agua
    # por un importe de 30 euros.
    apunte = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 2),
        naturaleza="GASTO",
        categoria="GAS_AGUA",
        concepto="Devolución de agua",
        tratamiento="REPERCUTIR",
        base=3000,
        iva_importe=0,
        retencion_importe=0,
        total=3000,
        importe_negativo=True,
    )

    # El usuario envía una solicitud que reconoce
    # 30 euros a favor del inquilino.
    solicitud = SolicitudReembolso(
        contrato=contrato,
        fecha_envio=date(2026, 10, 3),
    )

    solicitud.lineas.append(
        SolicitudReembolsoLinea(
            apunte=apunte,
            concepto="Devolución de agua",
            importe=3000,
        )
    )

    session.add_all([apunte, solicitud])
    session.commit()

    # El usuario consulta el saldo del contrato.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    assert situacion.total_exigible == -3000
    assert situacion.total_cobrado == 0
    assert situacion.saldo == -3000

    assert len(situacion.exigibles) == 1
    assert situacion.exigibles[0].importe == -3000


def test_reembolso_de_saldo_cero_no_genera_deuda(
    session,
    contrato,
):
    """Una solicitud compensada no modifica el saldo."""

    # El usuario registra un gasto de agua de 50 euros.
    gasto = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_AGUA",
        concepto="Agua",
        tratamiento="REPERCUTIR",
        base=5000,
        iva_importe=0,
        retencion_importe=0,
        total=5000,
    )

    # El usuario registra una devolución de 50 euros.
    devolucion = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 2),
        naturaleza="GASTO",
        categoria="GAS_AGUA",
        concepto="Devolución de agua",
        tratamiento="REPERCUTIR",
        base=5000,
        iva_importe=0,
        retencion_importe=0,
        total=5000,
        importe_negativo=True,
    )

    # El usuario envía una solicitud con ambas líneas.
    # Su importe neto es cero y no genera cobro previsto.
    solicitud = SolicitudReembolso(
        contrato=contrato,
        fecha_envio=date(2026, 10, 3),
    )

    solicitud.lineas.extend([
        SolicitudReembolsoLinea(
            apunte=gasto,
            concepto="Agua",
            importe=5000,
        ),
        SolicitudReembolsoLinea(
            apunte=devolucion,
            concepto="Devolución de agua",
            importe=5000,
        ),
    ])

    session.add_all([gasto, devolucion, solicitud])
    session.commit()

    # El usuario consulta la situación económica.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    assert situacion.total_exigible == 0
    assert situacion.total_cobrado == 0
    assert situacion.saldo == 0

    # La solicitud existe, aunque su saldo sea cero.
    assert len(situacion.exigibles) == 1
    assert situacion.exigibles[0].importe == 0


def test_devolucion_bancaria_al_inquilino_cancela_saldo(
    session,
    contrato,
):
    """Una devolución pagada elimina el crédito del inquilino."""

    # El propietario registra un abono de agua de 30 euros.
    apunte = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 2),
        naturaleza="GASTO",
        categoria="GAS_AGUA",
        concepto="Devolución de agua",
        tratamiento="REPERCUTIR",
        base=3000,
        iva_importe=0,
        retencion_importe=0,
        total=3000,
        importe_negativo=True,
    )

    # El usuario envía una solicitud negativa al inquilino.
    solicitud = SolicitudReembolso(
        contrato=contrato,
        fecha_envio=date(2026, 10, 3),
    )

    solicitud.lineas.append(
        SolicitudReembolsoLinea(
            apunte=apunte,
            concepto="Devolución de agua",
            importe=3000,
        )
    )

    # La devolución genera un movimiento previsto de GASTO.
    previsto = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        solicitud_reembolso=solicitud,
        naturaleza="GASTO",
        concepto="Devolución al inquilino",
        importe_esperado=3000,
        fecha_prevista_desde=date(2026, 10, 5),
        estado="CONCILIADO",
    )

    # El usuario importa la transferencia bancaria realizada.
    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="GASTO",
        importe=3000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Devolución al inquilino",
        huella_importacion="TEST-DEVOLUCION-INQUILINO",
        estado="CONCILIADO",
    )

    # El usuario concilia el pago con la devolución prevista.
    conciliacion = Conciliacion(
        movimiento_bancario=bancario,
        movimiento_previsto=previsto,
        importe_asociado=3000,
    )

    session.add_all([
        apunte,
        solicitud,
        previsto,
        bancario,
        conciliacion,
    ])
    session.commit()

    # El usuario consulta la situación después de la devolución.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    # La obligación negativa sigue siendo histórica.
    assert situacion.total_exigible == -3000

    # El pago realizado se representa como cobro negativo.
    assert situacion.total_cobrado == -3000

    # Ya no queda crédito pendiente a favor del inquilino.
    assert situacion.saldo == 0

    assert len(situacion.cobros) == 1
    assert situacion.cobros[0].fecha == date(2026, 10, 5)
    assert situacion.cobros[0].importe == -3000


def test_devolucion_manual_al_inquilino(
    session,
    contrato,
):
    """Una devolución manual cancela el crédito del inquilino."""

    # El propietario registra una devolución de agua
    # por un importe de 40 euros.
    apunte = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_AGUA",
        concepto="Devolución de agua",
        tratamiento="REPERCUTIR",
        base=4000,
        iva_importe=0,
        retencion_importe=0,
        total=4000,
        importe_negativo=True,
    )

    # El usuario envía una solicitud de reembolso negativa.
    solicitud = SolicitudReembolso(
        contrato=contrato,
        fecha_envio=date(2026, 10, 2),
    )

    solicitud.lineas.append(
        SolicitudReembolsoLinea(
            apunte=apunte,
            concepto="Devolución de agua",
            importe=4000,
        )
    )

    # El propietario devuelve los 40 euros en efectivo.
    # El usuario concilia manualmente el pago previsto,
    # sin generar ningún movimiento bancario.
    previsto = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        solicitud_reembolso=solicitud,
        naturaleza="GASTO",
        concepto="Devolución de agua en efectivo",
        importe_esperado=4000,
        fecha_prevista_desde=date(2026, 10, 5),
        estado="CONCILIADO",
        metodo_conciliacion="MANUAL",
        notas="Entregado en efectivo al inquilino",
    )

    session.add_all([apunte, solicitud, previsto])
    session.commit()

    # El usuario consulta el contrato antes de devolver
    # el dinero: debe existir un crédito de 40 euros.
    situacion_anterior = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 4),
    )

    assert situacion_anterior.total_exigible == -4000
    assert situacion_anterior.total_cobrado == 0
    assert situacion_anterior.saldo == -4000

    # El usuario consulta nuevamente el contrato
    # después de realizar la devolución.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    assert situacion.total_exigible == -4000
    assert situacion.total_cobrado == -4000
    assert situacion.saldo == 0

    # La devolución se presenta con signo negativo
    # y con la fecha prevista acordada.
    assert len(situacion.cobros) == 1
    assert situacion.cobros[0].fecha == date(2026, 10, 5)
    assert situacion.cobros[0].importe == -4000


def test_apunte_negativo_de_alquiler_reduce_exigible(
    session,
    contrato,
):
    """Una corrección negativa reduce la obligación del inquilino."""

    # El usuario tiene un contrato sin emisión de facturas.
    contrato.genera_factura = False

    # El usuario contabiliza el alquiler de octubre:
    # 1.000 euros exigibles.
    alquiler = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler octubre 2026",
        base=100000,
        iva_importe=0,
        retencion_importe=0,
        total=100000,
    )

    previsto_alquiler = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        apunte=alquiler,
        naturaleza="INGRESO",
        concepto="Alquiler octubre 2026",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    # El usuario registra una corrección del alquiler
    # por 50 euros a favor del inquilino.
    correccion = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 3),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Corrección alquiler octubre",
        base=5000,
        iva_importe=0,
        retencion_importe=0,
        total=5000,
        importe_negativo=True,
    )

    # Por ser un ingreso contable negativo,
    # el movimiento bancario previsto es de GASTO.
    previsto_correccion = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        apunte=correccion,
        naturaleza="GASTO",
        concepto="Corrección alquiler octubre",
        importe_esperado=5000,
        estado="PENDIENTE",
    )

    session.add_all([
        alquiler,
        previsto_alquiler,
        correccion,
        previsto_correccion,
    ])
    session.commit()

    # El usuario consulta la situación económica
    # antes de que se haya realizado ningún cobro.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    # El importe exigible debe incluir la corrección.
    assert situacion.total_exigible == 95000
    assert situacion.total_cobrado == 0
    assert situacion.saldo == 95000

    # La pantalla debe mostrar los dos conceptos,
    # conservando el signo negativo de la corrección.
    assert len(situacion.exigibles) == 2

    assert situacion.exigibles[0].importe == 100000
    assert situacion.exigibles[1].importe == -5000

    assert situacion.exigibles[1].fecha == date(2026, 10, 3)


def test_devolucion_de_alquiler_negativo_cancela_credito(
    session,
    contrato,
):
    """Una devolución de alquiler elimina el crédito del inquilino."""

    # El usuario utiliza un contrato sin emisión de facturas.
    contrato.genera_factura = False

    # El usuario contabiliza un alquiler de 1.000 euros.
    alquiler = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler octubre",
        base=100000,
        iva_importe=0,
        retencion_importe=0,
        total=100000,
    )

    previsto_alquiler = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        apunte=alquiler,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    session.add_all([alquiler, previsto_alquiler])
    session.flush()

    # El inquilino paga el alquiler completo
    # mediante transferencia bancaria.
    registrar_cobro(
        session,
        previsto_alquiler,
        fecha=date(2026, 10, 2),
        importe=100000,
        referencia="ALQUILER-COMPLETO",
    )

    # El usuario registra una corrección de 50 euros
    # a favor del inquilino.
    correccion = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 3),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Corrección alquiler octubre",
        base=5000,
        iva_importe=0,
        retencion_importe=0,
        total=5000,
        importe_negativo=True,
    )

    previsto_devolucion = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        apunte=correccion,
        naturaleza="GASTO",
        concepto="Devolución de alquiler",
        importe_esperado=5000,
        fecha_prevista_desde=date(2026, 10, 5),
        estado="CONCILIADO",
    )

    # El propietario devuelve los 50 euros
    # mediante transferencia bancaria.
    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="GASTO",
        importe=5000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Devolución alquiler",
        huella_importacion="TEST-DEVOLUCION-ALQUILER",
        estado="CONCILIADO",
    )

    # El usuario concilia la devolución con
    # el movimiento previsto correspondiente.
    conciliacion = Conciliacion(
        movimiento_bancario=bancario,
        movimiento_previsto=previsto_devolucion,
        importe_asociado=5000,
    )

    session.add_all([
        correccion,
        previsto_devolucion,
        bancario,
        conciliacion,
    ])
    session.commit()

    # El usuario consulta el saldo después de registrar
    # la corrección, pero antes de devolver el dinero.
    situacion_anterior = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 4),
    )

    assert situacion_anterior.total_exigible == 95000
    assert situacion_anterior.total_cobrado == 100000
    assert situacion_anterior.saldo == -5000

    # El usuario consulta nuevamente el contrato
    # después de realizar la devolución bancaria.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    # La corrección reduce el importe exigible.
    assert situacion.total_exigible == 95000

    # El importe neto cobrado incluye la devolución.
    assert situacion.total_cobrado == 95000

    # El inquilino ya no tiene deuda ni crédito.
    assert situacion.saldo == 0

    # Hay un cobro positivo y una devolución negativa.
    assert len(situacion.cobros) == 2

    assert situacion.cobros[0].importe == 100000
    assert situacion.cobros[0].fecha == date(2026, 10, 2)

    assert situacion.cobros[1].importe == -5000
    assert situacion.cobros[1].fecha == date(2026, 10, 5)


def test_devolucion_manual_de_alquiler_negativo_cancela_credito(
    session,
    contrato,
):
    """Una devolución manual de alquiler cancela el crédito."""

    # El usuario tiene un contrato sin emisión de facturas.
    contrato.genera_factura = False

    # El usuario contabiliza un alquiler de 1.000 euros.
    alquiler = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler octubre",
        base=100000,
        iva_importe=0,
        retencion_importe=0,
        total=100000,
    )

    previsto_alquiler = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        apunte=alquiler,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        fecha_prevista_desde=date(2026, 10, 2),
        estado="CONCILIADO",
        metodo_conciliacion="MANUAL",
        notas="Alquiler cobrado en efectivo",
    )

    session.add_all([alquiler, previsto_alquiler])
    session.flush()

    # El usuario registra una corrección de 50 euros
    # a favor del inquilino.
    correccion = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 10, 3),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Corrección alquiler octubre",
        base=5000,
        iva_importe=0,
        retencion_importe=0,
        total=5000,
        importe_negativo=True,
    )

    previsto_devolucion = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        apunte=correccion,
        naturaleza="GASTO",
        concepto="Devolución de alquiler",
        importe_esperado=5000,
        fecha_prevista_desde=date(2026, 10, 5),
        estado="CONCILIADO",
        metodo_conciliacion="MANUAL",
        notas="Devolución entregada en efectivo",
    )

    session.add_all([correccion, previsto_devolucion])
    session.commit()

    # El usuario consulta el saldo antes de la devolución.
    situacion_anterior = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 4),
    )

    assert situacion_anterior.total_exigible == 95000
    assert situacion_anterior.total_cobrado == 95000
    assert situacion_anterior.saldo == 0

    # El usuario consulta el saldo después de entregar
    # los 50 euros al inquilino.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    # La corrección reduce el exigible a 950 euros.
    assert situacion.total_exigible == 95000

    # El cobro neto descuenta los 50 euros devueltos.
    assert situacion.total_cobrado == 95000
    assert situacion.saldo == 0

    # El detalle conserva ambos movimientos
    # con sus respectivas fechas e importes.
    assert len(situacion.cobros) == 2

    assert situacion.cobros[0].fecha == date(2026, 10, 1)
    assert situacion.cobros[0].importe == 100000

    assert situacion.cobros[1].fecha == date(2026, 10, 3)
    assert situacion.cobros[1].importe == -5000


def test_contratos_sucesivos_no_comparten_deudas(
    session,
    inmueble,
    contrato,
):
    """Cada contrato conserva sus propias obligaciones y cobros."""

    # El contrato de la fixture será el nuevo,
    # que comienza el 1 de julio de 2026.
    contrato.fecha_inicio = date(2026, 7, 1)
    contrato.fecha_inicio_facturacion = date(2026, 7, 1)
    session.flush()

    # El usuario registra el contrato anterior
    # del mismo inmueble, finalizado el 30 de junio.
    contrato_anterior = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2025, 1, 1),
        fecha_vencimiento=date(2026, 6, 30),
        fecha_fin=date(2026, 6, 30),
        genera_factura=True,
        fecha_inicio_facturacion=date(2025, 1, 1),
        fianza=100000,
        direccion_facturacion="Dirección anterior",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler anterior",
    )

    session.add(contrato_anterior)
    session.flush()

    # El usuario había emitido una factura de 1.000 euros
    # al inquilino anterior.
    _, previsto_anterior = crear_factura_prueba(
        session,
        contrato_anterior,
        numero=20,
        fecha=date(2026, 6, 1),
        importe=100000,
    )

    # El antiguo inquilino solamente pagó 800 euros.
    registrar_cobro(
        session,
        previsto_anterior,
        fecha=date(2026, 6, 5),
        importe=80000,
        referencia="CONTRATO-ANTERIOR",
    )

    # El usuario emite una factura de 1.050 euros
    # correspondiente al nuevo inquilino.
    _, previsto_nuevo = crear_factura_prueba(
        session,
        contrato,
        numero=21,
        fecha=date(2026, 7, 1),
        importe=105000,
    )

    # El nuevo inquilino paga la factura completa.
    registrar_cobro(
        session,
        previsto_nuevo,
        fecha=date(2026, 7, 5),
        importe=105000,
        referencia="CONTRATO-NUEVO",
    )

    session.commit()

    # El usuario consulta el contrato anterior.
    situacion_anterior = calcular_situacion_contrato(
        session,
        contrato_anterior.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    assert situacion_anterior.total_exigible == 100000
    assert situacion_anterior.total_cobrado == 80000
    assert situacion_anterior.saldo == 20000

    assert len(situacion_anterior.exigibles) == 1
    assert len(situacion_anterior.cobros) == 1

    # El usuario consulta el nuevo contrato
    # desde el inicio de su vigencia.
    situacion_nueva = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 7, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    # La deuda anterior pertenece exclusivamente
    # al antiguo inquilino.
    assert situacion_nueva.saldo_anterior == 0

    # El nuevo contrato solamente muestra sus
    # propias obligaciones y cobros.
    assert situacion_nueva.total_exigible == 105000
    assert situacion_nueva.total_cobrado == 105000
    assert situacion_nueva.saldo == 0

    assert len(situacion_nueva.exigibles) == 1
    assert len(situacion_nueva.cobros) == 1

    assert situacion_nueva.exigibles[0].importe == 105000
    assert situacion_nueva.cobros[0].importe == 105000

    # El usuario amplía la consulta del contrato nuevo
    # al principio del año.
    #
    # Aunque ambos contratos pertenecen al mismo inmueble,
    # tampoco deben mezclarse sus movimientos históricos.
    situacion_anual = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    assert situacion_anual.saldo_anterior == 0
    assert situacion_anual.total_exigible == 105000
    assert situacion_anual.total_cobrado == 105000
    assert situacion_anual.saldo == 0

    assert len(situacion_anual.exigibles) == 1
    assert len(situacion_anual.cobros) == 1


def test_cobro_manual_utiliza_fecha_del_apunte(
    session,
    contrato,
):
    """La fecha del apunte prevalece sobre la fecha prevista."""

    # El usuario emite una factura el 1 de octubre
    # por un importe de 1.000 euros.
    _, previsto = crear_factura_prueba(
        session,
        contrato,
        numero=40,
        fecha=date(2026, 10, 1),
        importe=100000,
    )

    # La fecha prevista del cobro es el 5 de octubre,
    # pero el usuario confirma manualmente el cobro.
    previsto.fecha_prevista_desde = date(2026, 10, 5)
    previsto.estado = "CONCILIADO"
    previsto.metodo_conciliacion = "MANUAL"
    previsto.notas = "Cobrado fuera de la cuenta bancaria"

    session.commit()

    # Se comprueba el cálculo a 3 de octubre.
    # Debe utilizar la fecha contable del 1 de octubre,
    # no la fecha prevista del día 5.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 3),
    )

    assert situacion.total_exigible == 100000
    assert situacion.total_cobrado == 100000
    assert situacion.saldo == 0

    assert len(situacion.cobros) == 1
    assert situacion.cobros[0].fecha == date(2026, 10, 1)
    assert situacion.cobros[0].importe == 100000


def test_cobro_manual_sin_fecha_prevista(
    session,
    contrato,
):
    """Un cobro manual sin fecha prevista utiliza la del apunte."""

    # El usuario emite una factura de 850 euros
    # con fecha contable de 2 de octubre.
    _, previsto = crear_factura_prueba(
        session,
        contrato,
        numero=41,
        fecha=date(2026, 10, 2),
        importe=85000,
    )

    # El usuario confirma manualmente el cobro
    # aunque no existe ninguna fecha prevista.
    previsto.fecha_prevista_desde = None
    previsto.fecha_prevista_hasta = None
    previsto.estado = "CONCILIADO"
    previsto.metodo_conciliacion = "MANUAL"
    previsto.notas = "Cobrado en efectivo"

    session.commit()

    # Se consulta la situación económica del contrato.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    # El cobro confirmado no debe desaparecer
    # por carecer de fecha prevista.
    assert situacion.total_exigible == 85000
    assert situacion.total_cobrado == 85000
    assert situacion.saldo == 0

    assert len(situacion.cobros) == 1
    assert situacion.cobros[0].fecha == date(2026, 10, 2)
    assert situacion.cobros[0].importe == 85000


def test_cobro_manual_sin_ninguna_fecha(
    session,
    contrato,
):
    """Un cobro manual sin fechas conocidas se incluye en el saldo."""

    # El propietario registra un gasto de agua de 130 euros.
    gasto = ApunteContable(
        inmueble=contrato.inmueble,
        fecha=date(2026, 9, 20),
        naturaleza="GASTO",
        categoria="GAS_AGUA",
        concepto="Agua julio-septiembre",
        tratamiento="REPERCUTIR",
        base=13000,
        iva_importe=0,
        retencion_importe=0,
        total=13000,
    )

    # El usuario envía una solicitud de reembolso
    # al inquilino el 1 de octubre.
    solicitud = SolicitudReembolso(
        contrato=contrato,
        fecha_envio=date(2026, 10, 1),
    )

    solicitud.lineas.append(
        SolicitudReembolsoLinea(
            apunte=gasto,
            concepto="Agua julio-septiembre",
            importe=13000,
        )
    )

    # El usuario confirma que el inquilino ha pagado
    # los 130 euros, pero el movimiento previsto no
    # tiene fecha ni apunte contable asociado.
    previsto = MovimientoPrevisto(
        inmueble=contrato.inmueble,
        contrato=contrato,
        solicitud_reembolso=solicitud,
        naturaleza="INGRESO",
        concepto="Reembolso de agua",
        importe_esperado=13000,
        fecha_prevista_desde=None,
        fecha_prevista_hasta=None,
        estado="CONCILIADO",
        metodo_conciliacion="MANUAL",
        notas="Cobrado en efectivo",
    )

    session.add_all([gasto, solicitud, previsto])
    session.commit()

    # El usuario consulta la situación actual.
    # El movimiento está confirmado y debe incluirse,
    # aunque desconozcamos su fecha exacta.
    situacion = calcular_situacion_contrato(
        session,
        contrato.id,
        fecha_desde=date(2026, 1, 1),
        fecha_hasta=date(2026, 10, 6),
    )

    assert situacion.total_exigible == 13000
    assert situacion.total_cobrado == 13000
    assert situacion.saldo == 0

    # El cobro aparece en el detalle sin una fecha
    # inventada, que la interfaz mostrará como
    # "Fecha desconocida".
    assert len(situacion.cobros) == 1
    assert situacion.cobros[0].fecha is None
    assert situacion.cobros[0].importe == 13000


"""Pruebas de la lógica de negocio de conciliación."""

import pytest

from datetime import date
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from contab.config import CategoriaContable
from contab.models import (
    Conciliacion,
    Contrato,
    Inmueble,
    MovimientoBancario,
    MovimientoPrevisto,
)
from contab.contabilidad.services import crear_apunte_contable
import contab.conciliacion.services as servicios_conciliacion
from contab.conciliacion.services import (
    ConciliacionError,
    PropuestaConciliacion,
    _seleccionar_propuestas_agrupadas,
    actualizar_estado_movimiento_bancario,
    actualizar_estado_movimiento_previsto,
    asociar_movimientos,
    buscar_candidatos_conciliacion,
    buscar_propuestas_agrupadas,
    buscar_propuestas_conciliacion,
    cancelar_movimiento_previsto,
    clasificar_movimiento_bancario,
    clasificar_movimientos_bancarios,
    conciliar_movimiento_previsto_manualmente,
    confirmar_conciliacion,
    confirmar_grupo_conciliacion,
    confirmar_propuesta_conciliacion,
    crear_movimiento_desde_apunte,
    crear_movimiento_previsto,
    descartar_movimiento_bancario,
    deshacer_asociacion_bancaria,
    deshacer_conciliacion_manual,
    diagnosticar_emparejamiento,
    preparar_asociaciones_cronologicas,
    proponer_conciliacion,
    puntuar_candidato_conciliacion,
    restaurar_movimiento_bancario,
    restaurar_movimiento_previsto,
    saldo_movimiento_bancario,
    saldo_movimiento_previsto,
    validar_asociacion,
)




def _escenario_propuestas_en_competencia(
    inmueble,
    *,
    descripcion_individual,
    descripcion_grupo,
):
    """Crea una alternativa 1:1 y otra 1:2 para el mismo alquiler."""

    previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    def bancario(importe, descripcion, referencia):
        return MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=importe,
            tipo_original="TRANSFERENCIA",
            descripcion_original=descripcion,
            referencia_bancaria="",
            huella_importacion=referencia,
            estado="PENDIENTE",
        )

    individual = bancario(
        100000,
        descripcion_individual,
        "competencia-individual",
    )

    primero = bancario(
        60000,
        descripcion_grupo,
        "competencia-grupo-1",
    )

    segundo = bancario(
        40000,
        descripcion_grupo,
        "competencia-grupo-2",
    )

    return previsto, individual, primero, segundo


def _previsto_para_confirmar(inmueble, concepto, importe):
    return crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto=concepto,
        importe_esperado=importe,
    )


def _bancario_para_confirmar(referencia, importe):
    return MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=importe,
        tipo_original="TRANSFERENCIA",
        descripcion_original=referencia,
        referencia_bancaria="",
        huella_importacion=referencia,
        estado="PENDIENTE",
    )


def _movimiento_bancario_para_diferencias(
    importe: int,
    descripcion: str,
    referencia: str,
) -> MovimientoBancario:
    """Construye un movimiento bancario para probar propuestas."""

    return MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=importe,
        tipo_original="TRANSFERENCIA",
        descripcion_original=descripcion,
        referencia_bancaria="",
        huella_importacion=referencia,
        estado="PENDIENTE",
    )


def _contrato_para_cierre_agrupado(inmueble):
    return Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2026, 1, 1),
        fecha_vencimiento=date(2035, 12, 31),
        genera_factura=True,
        fecha_inicio_facturacion=date(2026, 1, 1),
        fianza=0,
        direccion_facturacion="Dirección de prueba",
        poblacion_facturacion="Madrid",
        provincia_facturacion="Madrid",
        concepto_factura="Alquiler",
    )




def test_crear_movimiento_previsto(inmueble) -> None:
    movimiento = crear_movimiento_previsto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 5),
        naturaleza=" gasto ",
        concepto="  Recibo de agua  ",
        importe_esperado=5432,
        contraparte="  Empresa de aguas  ",
        notas="  Cargo domiciliado  ",
    )

    assert movimiento.inmueble is inmueble
    assert movimiento.fecha_prevista_desde == date(2026, 9, 5)
    assert movimiento.fecha_prevista_hasta is None
    assert movimiento.naturaleza == "GASTO"
    assert movimiento.concepto == "Recibo de agua"
    assert movimiento.importe_esperado == 5432
    assert movimiento.contraparte == "Empresa de aguas"
    assert movimiento.estado == "PENDIENTE"
    assert movimiento.notas == "Cargo domiciliado"
    assert movimiento.apunte is None
    assert movimiento.contrato is None


def test_movimiento_previsto_rechaza_metodo_conciliacion_invalido(
    session,
    inmueble,
) -> None:
    movimiento = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Movimiento de prueba",
        importe_esperado=10000,
        estado="PENDIENTE",
        metodo_conciliacion="OTRO",
    )

    session.add(movimiento)

    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    ("naturaleza", "concepto", "importe", "mensaje"),
    [
        ("OTRA", "Movimiento", 1000, "naturaleza"),
        ("GASTO", "", 1000, "concepto"),
        ("GASTO", "Movimiento", 0, "mayor que cero"),
        ("GASTO", "Movimiento", -1, "mayor que cero"),
    ],
)
def test_crear_movimiento_previsto_rechaza_datos_invalidos(
    inmueble,
    naturaleza: str,
    concepto: str,
    importe: int,
    mensaje: str,
) -> None:
    with pytest.raises(
        ConciliacionError,
        match=mensaje,
    ):
        crear_movimiento_previsto(
            inmueble=inmueble,
            fecha_prevista_desde=date(2026, 9, 5),
            naturaleza=naturaleza,
            concepto=concepto,
            importe_esperado=importe,
        )


def test_crear_movimiento_previsto_vinculado_a_apunte(
    session,
    inmueble,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=12500,
    )

    movimiento = crear_movimiento_previsto(
        inmueble=inmueble,
        apunte=apunte,
        fecha_prevista_desde=date(2026, 9, 5),
        naturaleza="GASTO",
        concepto="Cuota de comunidad",
        importe_esperado=12500,
        contraparte="Comunidad de propietarios",
    )

    session.add_all([apunte, movimiento])
    session.commit()

    movimiento_id = movimiento.id

    session.expire_all()

    guardado = session.get(
        MovimientoPrevisto,
        movimiento_id,
    )

    assert guardado is not None
    assert guardado.apunte_id == apunte.id
    assert guardado.inmueble_id == inmueble.id
    assert guardado.naturaleza == "GASTO"
    assert guardado.importe_esperado == 12500
    assert guardado.estado == "PENDIENTE"


def test_movimiento_y_apunte_deben_tener_misma_naturaleza(
    inmueble,
) -> None:
    categorias = {
        "ING_ALQUILERES": CategoriaContable(
            codigo="ING_ALQUILERES",
            naturaleza="INGRESO",
            nombre="Alquileres",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto="Alquiler de septiembre",
        base=100000,
    )

    with pytest.raises(
        ConciliacionError,
        match="misma naturaleza",
    ):
        crear_movimiento_previsto(
            inmueble=inmueble,
            apunte=apunte,
            fecha_prevista_desde=date(2026, 9, 5),
            naturaleza="GASTO",
            concepto="Movimiento incorrecto",
            importe_esperado=100000,
        )


def test_crear_movimiento_desde_apunte_reutiliza_datos(
    inmueble,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota de comunidad",
        base=12500,
        tercero_nombre="Comunidad de propietarios",
    )

    movimiento = crear_movimiento_desde_apunte(
        apunte=apunte,
        fecha_prevista_desde=date(2026, 9, 5),
    )

    assert movimiento.apunte is apunte
    assert movimiento.inmueble is inmueble
    assert movimiento.fecha_prevista_desde == date(2026, 9, 5)
    assert movimiento.fecha_prevista_hasta is None
    assert movimiento.naturaleza == "GASTO"
    assert movimiento.concepto == "Cuota de comunidad"
    assert movimiento.importe_esperado == 12500
    assert movimiento.contraparte == "Comunidad de propietarios"
    assert movimiento.estado == "PENDIENTE"


def test_crear_movimiento_desde_apunte_admite_correcciones(
    inmueble,
) -> None:
    categorias = {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=categorias,
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Cuota trimestral",
        base=30000,
    )

    movimiento = crear_movimiento_desde_apunte(
        apunte=apunte,
        fecha_prevista_desde=date(2026, 9, 5),
        importe_esperado=10000,
        concepto="Primer plazo",
        contraparte="Comunidad",
    )

    assert movimiento.importe_esperado == 10000
    assert movimiento.concepto == "Primer plazo"
    assert movimiento.contraparte == "Comunidad"


def test_descartar_y_restaurar_movimiento_bancario() -> None:
    """Permite descartar un movimiento y bancario y restaurarlo."""

    movimiento = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="GASTO",
        importe=10000,
        tipo_original="TARJETA VISA",
        descripcion_original="Compra particular",
        referencia_bancaria="",
        huella_importacion="a" * 64,
        estado="PENDIENTE",
    )

    descartar_movimiento_bancario(
        movimiento
    )

    assert movimiento.estado == "DESCARTADO"

    restaurar_movimiento_bancario(
        movimiento
    )

    assert movimiento.estado == "PENDIENTE"


def test_no_permite_descartar_movimiento_conciliado() -> None:
    """Un movimiento conciliado no puede descartarse."""

    movimiento = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="INGRESO",
        importe=10000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Alquiler",
        referencia_bancaria="",
        huella_importacion="b" * 64,
        estado="CONCILIADO",
    )

    with pytest.raises(
        ConciliacionError,
        match="conciliado",
    ):
        descartar_movimiento_bancario(
            movimiento
        )


def test_crear_movimiento_previsto_admite_fechas_vacias(
    inmueble,
) -> None:
    """Permite una previsión sin intervalo fiable."""

    movimiento = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Recibo pendiente",
        importe_esperado=10000,
    )

    assert movimiento.fecha_prevista_desde is None
    assert movimiento.fecha_prevista_hasta is None


@pytest.mark.parametrize(
    (
        "fecha_desde",
        "fecha_hasta",
        "mensaje",
    ),
    [
        (
            None,
            date(2026, 9, 20),
            "sin indicar la fecha prevista desde",
        ),
        (
            date(2026, 9, 20),
            date(2026, 9, 15),
            "no puede ser anterior",
        ),
    ],
)


def test_crear_movimiento_previsto_rechaza_intervalo_invalido(
    inmueble,
    fecha_desde,
    fecha_hasta,
    mensaje,
) -> None:
    """Rechaza combinaciones incoherentes del intervalo."""

    with pytest.raises(
        ConciliacionError,
        match=mensaje,
    ):
        crear_movimiento_previsto(
            inmueble=inmueble,
            naturaleza="GASTO",
            concepto="Recibo",
            importe_esperado=10000,
            fecha_prevista_desde=fecha_desde,
            fecha_prevista_hasta=fecha_hasta,
        )


def test_cancelar_y_restaurar_movimiento_previsto(
    inmueble,
) -> None:
    """Cancela una previsión pendiente y permite restaurarla."""

    movimiento = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 15),
        fecha_prevista_hasta=date(2026, 9, 20),
        naturaleza="GASTO",
        concepto="Recibo de gas",
        importe_esperado=12500,
        contraparte="Comercializadora",
        estado="PENDIENTE",
    )

    cancelar_movimiento_previsto(
        movimiento
    )

    assert movimiento.estado == "CANCELADO"

    restaurar_movimiento_previsto(
        movimiento
    )

    assert movimiento.estado == "PENDIENTE"


@pytest.mark.parametrize(
    "estado",
    [
        "PARCIAL",
        "CONCILIADO",
    ],
)
def test_no_permite_cancelar_movimiento_previsto_utilizado(
    inmueble,
    estado: str,
) -> None:
    """No cancela una previsión parcial o totalmente conciliada."""

    movimiento = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        contraparte="Inquilino",
        estado=estado,
    )

    with pytest.raises(
        ConciliacionError,
        match="pendiente",
    ):
        cancelar_movimiento_previsto(
            movimiento
        )

    assert movimiento.estado == estado


def test_no_permite_restaurar_movimiento_previsto_no_cancelado(
    inmueble,
) -> None:
    """Sólo permite restaurar una previsión cancelada."""

    movimiento = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Recibo de comunidad",
        importe_esperado=10000,
        contraparte="Comunidad",
        estado="PENDIENTE",
    )

    with pytest.raises(
        ConciliacionError,
        match="cancelado",
    ):
        restaurar_movimiento_previsto(
            movimiento
        )

    assert movimiento.estado == "PENDIENTE"


def test_puntuar_candidato_conciliacion(
    inmueble,
) -> None:
    """Valora importe exacto y fecha prevista."""

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="INGRESO",
        importe=112116,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Alquiler",
        referencia_bancaria="",
        huella_importacion="c" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 1),
        fecha_prevista_hasta=date(2026, 9, 5),
        naturaleza="INGRESO",
        concepto="Alquiler septiembre",
        importe_esperado=112116,
        contraparte="Inquilino",
        estado="PENDIENTE",
    )

    puntuacion = puntuar_candidato_conciliacion(
        bancario,
        previsto,
    )

    assert puntuacion == 120


def test_buscar_candidatos_conciliacion(
    inmueble,
) -> None:
    """Ordena las previsiones pendientes compatibles."""

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="INGRESO",
        importe=112116,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Alquiler",
        referencia_bancaria="",
        huella_importacion="d" * 64,
        estado="PENDIENTE",
    )

    importe_exacto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler exacto",
        importe_esperado=112116,
        estado="PENDIENTE",
    )

    fecha_compatible = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 1),
        fecha_prevista_hasta=date(2026, 9, 5),
        naturaleza="INGRESO",
        concepto="Alquiler con otro importe",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    sin_coincidencias = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Otro alquiler",
        importe_esperado=80000,
        estado="PENDIENTE",
    )

    cancelado = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Cancelado",
        importe_esperado=112116,
        estado="CANCELADO",
    )

    gasto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Recibo",
        importe_esperado=112116,
        estado="PENDIENTE",
    )

    candidatos = buscar_candidatos_conciliacion(
        bancario,
        [
            sin_coincidencias,
            fecha_compatible,
            cancelado,
            gasto,
            importe_exacto,
        ],
    )

    assert candidatos == [
        (importe_exacto, 100),
        (fecha_compatible, 20),
        (sin_coincidencias, 0),
    ]


def test_puntuar_candidato_por_contraparte(
    inmueble,
) -> None:
    """Reconoce la contraparte aunque cambien mayúsculas y tildes."""

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="INGRESO",
        importe=160000,
        tipo_original="TRANSFERENCIA OTRA ENTIDAD",
        descripcion_original=(
            "BARBARA BONITA BARCENAS 11222333Y "
            "Piso septiembre"
        ),
        referencia_bancaria="",
        huella_importacion="e" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler septiembre",
        importe_esperado=150000,
        contraparte="Bárbara Bonita Barcenas",
        estado="PENDIENTE",
    )

    puntuacion = puntuar_candidato_conciliacion(
        bancario,
        previsto,
    )

    assert puntuacion == 50


def test_contraparte_vacia_no_puntua(
    inmueble,
) -> None:
    """Una contraparte vacía no coincide con cualquier texto."""

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="INGRESO",
        importe=10000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="PAGO",
        referencia_bancaria="",
        huella_importacion="f" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Ingreso",
        importe_esperado=20000,
        contraparte="",
        estado="PENDIENTE",
    )

    puntuacion = puntuar_candidato_conciliacion(
        bancario,
        previsto,
    )

    assert puntuacion == 0


def test_puntuar_candidato_suma_alias_bancario() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 10),
        naturaleza="GASTO",
        importe=9999,
        tipo_original="RECIBO",
        descripcion_original="C.P. AV. LOGROÑ SEPTIEMBRE",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Comunidad Septiembre",
        importe_esperado=15436,
        contraparte="Comunidad de propietarios",
        estado="PENDIENTE",
    )

    puntuacion = puntuar_candidato_conciliacion(
        bancario,
        previsto,
        aliases=[
            "C.P. AV. LOGROÑ",
        ],
    )

    assert puntuacion == 40


def test_puntuar_candidato_suma_alias_una_sola_vez() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 10),
        naturaleza="GASTO",
        importe=9999,
        tipo_original="C.P. AV. LOGROÑ",
        descripcion_original="CP.AV.LOGROÑO",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Comunidad Septiembre",
        importe_esperado=15436,
        contraparte="",
        estado="PENDIENTE",
    )

    puntuacion = puntuar_candidato_conciliacion(
        bancario,
        previsto,
        aliases=[
            "C.P. AV. LOGROÑ",
            "CP.AV.LOGROÑO",
        ],
    )

    assert puntuacion == 40


def test_puntuar_candidato_busca_alias_en_referencia_bancaria() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 10),
        naturaleza="GASTO",
        importe=9999,
        tipo_original="RECIBO",
        descripcion_original="CUOTA",
        referencia_bancaria="C.P. AV. LOGROÑ",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Comunidad Septiembre",
        importe_esperado=15436,
        contraparte="",
        estado="PENDIENTE",
    )

    assert puntuar_candidato_conciliacion(
        bancario,
        previsto,
        aliases=["C.P. AV. LOGROÑ"],
    ) == 40


def test_buscar_candidatos_aplica_alias_por_inmueble_y_tipo() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 8),
        naturaleza="GASTO",
        importe=9999,
        tipo_original="RECIBO",
        descripcion_original="C.P. AV. LOGROÑ",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    comunidad = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Comunidad Septiembre",
        importe_esperado=15436,
        contraparte="",
        estado="PENDIENTE",
    )

    seguro = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Seguro Septiembre",
        importe_esperado=10338,
        contraparte="",
        estado="PENDIENTE",
    )

    candidatos = buscar_candidatos_conciliacion(
        bancario,
        [
            seguro,
            comunidad,
        ],
        aliases_configurados=[
            (
                "COMUNIDAD",
                "AVLOGRO",
                "C.P. AV. LOGROÑ",
            ),
            (
                "SEGURO",
                "AVLOGRO",
                "ASEGURADORA",
            ),
        ],
    )

    assert candidatos == [
        (comunidad, 40),
        (seguro, 0),
    ]


def test_buscar_candidatos_no_aplica_alias_de_otro_inmueble() -> None:
    inmueble = Inmueble(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="A1",
        descripcion="Local 1",
        direccion="Dirección 1",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 10),
        naturaleza="GASTO",
        importe=9999,
        tipo_original="RECIBO",
        descripcion_original="C.P. AV. LOGROÑ",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Comunidad Septiembre",
        importe_esperado=15436,
        contraparte="",
        estado="PENDIENTE",
    )

    candidatos = buscar_candidatos_conciliacion(
        bancario,
        [previsto],
        aliases_configurados=[
            (
                "COMUNIDAD",
                "OTRO_INMUEBLE",
                "C.P. AV. LOGROÑ",
            ),
        ],
    )

    assert candidatos == [
        (previsto, 0),
    ]


def test_buscar_candidatos_no_aplica_alias_de_otro_tipo() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 8),
        naturaleza="GASTO",
        importe=9999,
        tipo_original="RECIBO",
        descripcion_original="C.P. AV. LOGROÑ",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Comunidad Septiembre",
        importe_esperado=15436,
        contraparte="",
        estado="PENDIENTE",
    )

    candidatos = buscar_candidatos_conciliacion(
        bancario,
        [previsto],
        aliases_configurados=[
            (
                "ALQUILER",
                "AVLOGRO",
                "C.P. AV. LOGROÑ",
            ),
        ],
    )

    assert candidatos == [
        (previsto, 0),
    ]


def test_proponer_conciliacion_elige_mejor_candidato() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 10),
        naturaleza="GASTO",
        importe=15436,
        tipo_original="RECIBO",
        descripcion_original="C.P. AV. LOGROÑ",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    mejor = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Comunidad Septiembre",
        importe_esperado=15436,
        contraparte="",
        estado="PENDIENTE",
    )

    peor = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Seguro Septiembre",
        importe_esperado=9999,
        contraparte="",
        estado="PENDIENTE",
    )

    propuesta = proponer_conciliacion(
        bancario,
        [peor, mejor],
        aliases_configurados=[
            (
                "COMUNIDAD",
                "AVLOGRO",
                "C.P. AV. LOGROÑ",
            ),
        ],
    )

    assert propuesta is mejor


def test_proponer_conciliacion_no_propone_candidato_sin_puntuacion() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 10),
        naturaleza="GASTO",
        importe=9999,
        tipo_original="RECIBO",
        descripcion_original="DESCONOCIDO",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Comunidad Septiembre",
        importe_esperado=15436,
        contraparte="",
        estado="PENDIENTE",
    )

    propuesta = proponer_conciliacion(
        bancario,
        [previsto],
    )

    assert propuesta is None


def test_proponer_conciliacion_no_decide_un_empate() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 10),
        naturaleza="GASTO",
        importe=15436,
        tipo_original="RECIBO",
        descripcion_original="",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    primero = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Comunidad septiembre",
        importe_esperado=15436,
        contraparte="",
        estado="PENDIENTE",
    )

    segundo = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Otro gasto",
        importe_esperado=15436,
        contraparte="",
        estado="PENDIENTE",
    )

    propuesta = proponer_conciliacion(
        bancario,
        [primero, segundo],
    )

    assert propuesta is None


def test_proponer_conciliacion_no_propone_solo_por_fecha() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 10),
        naturaleza="GASTO",
        importe=9999,
        tipo_original="RECIBO",
        descripcion_original="DESCONOCIDO",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 10),
        fecha_prevista_hasta=date(2026, 9, 10),
        naturaleza="GASTO",
        concepto="Suministro",
        importe_esperado=12345,
        contraparte="",
        estado="PENDIENTE",
    )

    propuesta = proponer_conciliacion(
        bancario,
        [previsto],
    )

    assert propuesta is None


def test_proponer_conciliacion_propone_solo_por_importe() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 20),
        naturaleza="GASTO",
        importe=12345,
        tipo_original="RECIBO ENERGIA",
        descripcion_original="COMERCIALIZADORA DESCONOCIDA",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 1),
        fecha_prevista_hasta=date(2026, 9, 5),
        naturaleza="GASTO",
        concepto="Electricidad septiembre",
        importe_esperado=12345,
        contraparte="",
        estado="PENDIENTE",
    )

    propuesta = proponer_conciliacion(
        bancario,
        [previsto],
    )

    assert propuesta is previsto


def test_buscar_candidatos_admite_movimiento_siete_dias_antes() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 8, 25),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="ALQUILER SEPTIEMBRE",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 1),
        fecha_prevista_hasta=date(2026, 9, 5),
        naturaleza="INGRESO",
        concepto="Alquiler septiembre",
        importe_esperado=100000,
        contraparte="",
        estado="PENDIENTE",
    )

    candidatos = buscar_candidatos_conciliacion(
        bancario,
        [previsto],
    )

    assert candidatos == [(previsto, 100)]


def test_buscar_candidatos_rechaza_movimiento_demasiado_anticipado() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 8, 24),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="ALQUILER SEPTIEMBRE",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 1),
        fecha_prevista_hasta=date(2026, 9, 5),
        naturaleza="INGRESO",
        concepto="Alquiler septiembre",
        importe_esperado=100000,
        contraparte="",
        estado="PENDIENTE",
    )

    candidatos = buscar_candidatos_conciliacion(
        bancario,
        [previsto],
    )

    assert candidatos == []


def test_buscar_candidatos_admite_movimiento_posterior_a_fecha_prevista() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 20),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="ALQUILER SEPTIEMBRE",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 1),
        fecha_prevista_hasta=date(2026, 9, 5),
        naturaleza="INGRESO",
        concepto="Alquiler septiembre",
        importe_esperado=100000,
        contraparte="",
        estado="PENDIENTE",
    )

    candidatos = buscar_candidatos_conciliacion(
        bancario,
        [previsto],
    )

    assert candidatos == [(previsto, 100)]


def test_clasificar_movimiento_propone_descarte_por_alias() -> None:
    bancario = MovimientoBancario(
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        importe=2350,
        tipo_original="PAGO TARJETA",
        descripcion_original="CAFETERIA EL MODE",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    clasificacion, propuesta = clasificar_movimiento_bancario(
        bancario,
        [],
        aliases_descartar=[
            "CAFETERIA EL MODE",
        ],
    )

    assert clasificacion == "DESCARTAR"
    assert propuesta is None


def test_clasificar_movimiento_sin_evidencia_queda_pendiente() -> None:
    bancario = MovimientoBancario(
        fecha=date(2026, 9, 1),
        naturaleza="GASTO",
        importe=2350,
        tipo_original="RECIBO",
        descripcion_original="DESCONOCIDO",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    clasificacion, propuesta = clasificar_movimiento_bancario(
        bancario,
        [],
        aliases_descartar=[
            "CAFETERIA EL MODE",
        ],
    )

    assert clasificacion == "PENDIENTE"
    assert propuesta is None


def test_clasificar_movimiento_prioriza_conciliacion() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="GASTO",
        importe=12345,
        tipo_original="RECIBO",
        descripcion_original="EMPRESA CONOCIDA",
        referencia_bancaria="",
        huella_importacion="bancario",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 1),
        fecha_prevista_hasta=date(2026, 9, 5),
        naturaleza="GASTO",
        concepto="Suministro septiembre",
        importe_esperado=12345,
        contraparte="",
        estado="PENDIENTE",
    )

    clasificacion, propuesta = clasificar_movimiento_bancario(
        bancario,
        [previsto],
        aliases_descartar=[
            "EMPRESA CONOCIDA",
        ],
    )

    assert clasificacion == "CONCILIAR"
    assert propuesta is previsto


def test_clasificar_movimientos_bancarios_agrupa_propuestas() -> None:
    inmueble = Inmueble(
        referencia="AVLOGRO",
        tipo="L",
        codigo_facturacion="AL",
        descripcion="Local",
        direccion="Avenida Logroño",
        poblacion="Madrid",
        provincia="Madrid",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 1),
        fecha_prevista_hasta=date(2026, 9, 5),
        naturaleza="INGRESO",
        concepto="Alquiler septiembre",
        importe_esperado=100000,
        contraparte="INQUILINO",
        estado="PENDIENTE",
    )

    conciliable = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="INQUILINO",
        referencia_bancaria="",
        huella_importacion="conciliable",
        estado="PENDIENTE",
    )

    descartable = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="GASTO",
        importe=2500,
        tipo_original="TARJETA",
        descripcion_original="CAFETERIA EL MODE",
        referencia_bancaria="",
        huella_importacion="descartable",
        estado="PENDIENTE",
    )

    pendiente = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="GASTO",
        importe=6789,
        tipo_original="RECIBO",
        descripcion_original="DESCONOCIDO",
        referencia_bancaria="",
        huella_importacion="pendiente",
        estado="PENDIENTE",
    )

    ya_descartado = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="GASTO",
        importe=1111,
        tipo_original="TARJETA",
        descripcion_original="CAFETERIA EL MODE",
        referencia_bancaria="",
        huella_importacion="ya-descartado",
        estado="DESCARTADO",
    )

    (
        a_conciliar,
        a_descartar,
        pendientes,
    ) = clasificar_movimientos_bancarios(
        [
            conciliable,
            descartable,
            pendiente,
            ya_descartado,
        ],
        [previsto],
        aliases_descartar=[
            "CAFETERIA EL MODE",
        ],
    )

    assert a_conciliar == [
        (conciliable, previsto),
    ]

    assert a_descartar == [
        descartable,
    ]

    assert pendientes == [
        pendiente,
    ]


def test_confirmar_conciliacion_completa() -> None:
    bancario = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="INGRESO",
        importe=160000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="BARBARA BONITA BARCENAS",
        referencia_bancaria="",
        huella_importacion="a" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=Inmueble(
            referencia="PISO-1",
            tipo="P",
            codigo_facturacion="P1",
            descripcion="Piso",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        ),
        naturaleza="INGRESO",
        concepto="Alquiler septiembre",
        importe_esperado=160000,
        contraparte="BARBARA BONITA BARCENAS",
        estado="PENDIENTE",
    )

    conciliacion = confirmar_conciliacion(
        bancario,
        previsto,
    )

    assert conciliacion.movimiento_bancario is bancario
    assert conciliacion.movimiento_previsto is previsto
    assert conciliacion.importe_asociado == 160000

    assert bancario.estado == "CONCILIADO"
    assert previsto.estado == "CONCILIADO"
    assert previsto.metodo_conciliacion == "INDIVIDUAL"


def test_confirmar_conciliacion_rechaza_importe_diferente() -> None:
    bancario = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="INGRESO",
        importe=160000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="BARBARA BONITA BARCENAS",
        referencia_bancaria="",
        huella_importacion="a" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=Inmueble(
            referencia="PISO-1",
            tipo="P",
            codigo_facturacion="P1",
            descripcion="Piso",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        ),
        naturaleza="INGRESO",
        concepto="Alquiler septiembre",
        importe_esperado=160500,
        contraparte="BARBARA BONITA BARCENAS",
        estado="PENDIENTE",
    )

    with pytest.raises(
        ConciliacionError,
    ):
        confirmar_conciliacion(
                bancario,
                previsto,
            )

    assert bancario.estado == "PENDIENTE"
    assert previsto.estado == "PENDIENTE"


def test_confirmar_conciliacion_rechaza_bancario_no_pendiente() -> None:
    bancario = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="INGRESO",
        importe=160000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="BARBARA BONITA BARCENAS",
        referencia_bancaria="",
        huella_importacion="a" * 64,
        estado="CONCILIADO",
    )

    previsto = MovimientoPrevisto(
        inmueble=Inmueble(
            referencia="PISO-1",
            tipo="P",
            codigo_facturacion="P1",
            descripcion="Piso",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        ),
        naturaleza="INGRESO",
        concepto="Alquiler septiembre",
        importe_esperado=160000,
        contraparte="BARBARA BONITA BARCENAS",
        estado="PENDIENTE",
    )

    with pytest.raises(
        ConciliacionError,
    ):
        confirmar_conciliacion(
                bancario,
                previsto,
            )

    assert bancario.estado == "CONCILIADO"
    assert previsto.estado == "PENDIENTE"


def test_confirmar_conciliacion_rechaza_previsto_no_pendiente() -> None:
    bancario = MovimientoBancario(
        fecha=date(2026, 9, 3),
        naturaleza="INGRESO",
        importe=160000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="BARBARA BONITA BARCENAS",
        referencia_bancaria="",
        huella_importacion="a" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=Inmueble(
            referencia="PISO-1",
            tipo="P",
            codigo_facturacion="P1",
            descripcion="Piso",
            direccion="Dirección",
            poblacion="Madrid",
            provincia="Madrid",
        ),
        naturaleza="INGRESO",
        concepto="Alquiler septiembre",
        importe_esperado=160000,
        contraparte="BARBARA BONITA BARCENAS",
        estado="CONCILIADO",
    )

    with pytest.raises(
        ConciliacionError,
    ):
        confirmar_conciliacion(
            bancario,
            previsto,
        )

    assert bancario.estado == "PENDIENTE"
    assert previsto.estado == "CONCILIADO"


def test_conciliar_movimiento_previsto_manualmente(
    inmueble,
) -> None:
    movimiento = crear_movimiento_previsto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 5),
        naturaleza="GASTO",
        concepto="IBI",
        importe_esperado=25000,
    )

    conciliar_movimiento_previsto_manualmente(
        movimiento,
        "  Incluido en los cargos agrupados del Ayuntamiento.  ",
    )

    assert movimiento.estado == "CONCILIADO"
    assert movimiento.metodo_conciliacion == "MANUAL"
    assert (
        movimiento.notas
        == "Incluido en los cargos agrupados del Ayuntamiento."
    )
    assert movimiento.conciliaciones == []


@pytest.mark.parametrize(
    "notas",
    [
        "",
        "   ",
    ],
)
def test_conciliar_movimiento_previsto_manualmente_rechaza_notas_vacias(
    inmueble,
    notas: str,
) -> None:
    movimiento = crear_movimiento_previsto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 5),
        naturaleza="GASTO",
        concepto="IBI",
        importe_esperado=25000,
    )

    with pytest.raises(
        ConciliacionError,
        match="requiere una explicación",
    ):
        conciliar_movimiento_previsto_manualmente(
            movimiento,
            notas,
        )

    assert movimiento.estado == "PENDIENTE"
    assert movimiento.metodo_conciliacion is None


@pytest.mark.parametrize(
    "estado",
    [
        "PARCIAL",
        "CONCILIADO",
        "CANCELADO",
    ],
)
def test_conciliar_movimiento_previsto_manualmente_requiere_pendiente(
    inmueble,
    estado: str,
) -> None:
    movimiento = crear_movimiento_previsto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 5),
        naturaleza="GASTO",
        concepto="IBI",
        importe_esperado=25000,
    )
    movimiento.estado = estado

    with pytest.raises(
        ConciliacionError,
        match="debe estar pendiente",
    ):
        conciliar_movimiento_previsto_manualmente(
            movimiento,
            "Incluido en los cargos agrupados del Ayuntamiento.",
        )

    assert movimiento.estado == estado
    assert movimiento.metodo_conciliacion is None


def test_deshacer_conciliacion_manual(
    inmueble,
) -> None:
    movimiento = crear_movimiento_previsto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 5),
        naturaleza="GASTO",
        concepto="IBI",
        importe_esperado=25000,
    )

    conciliar_movimiento_previsto_manualmente(
        movimiento,
        "Incluido en los cargos agrupados del Ayuntamiento.",
    )

    # El usuario deshace una conciliación manual realizada por error.
    deshacer_conciliacion_manual(
        movimiento,
    )

    assert movimiento.estado == "PENDIENTE"
    assert movimiento.metodo_conciliacion is None
    assert movimiento.notas is None
    assert movimiento.conciliaciones == []


def test_deshacer_conciliacion_manual_rechaza_individual(
    inmueble,
) -> None:
    previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 9, 5),
        naturaleza="GASTO",
        concepto="Comunidad",
        importe_esperado=10000,
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 9, 5),
        naturaleza="GASTO",
        importe=10000,
        tipo_original="RECIBO",
        descripcion_original="Comunidad",
        referencia_bancaria="",
        huella_importacion="a" * 64,
        estado="PENDIENTE",
    )

    confirmar_conciliacion(
        bancario,
        previsto,
    )

    # Una conciliación bancaria individual no se puede deshacer
    # mediante la operación reservada a conciliaciones manuales.
    with pytest.raises(
        ConciliacionError,
        match="debe estar conciliado manualmente",
    ):
        deshacer_conciliacion_manual(
            previsto,
        )

    assert previsto.estado == "CONCILIADO"
    assert previsto.metodo_conciliacion == "INDIVIDUAL"
    assert bancario.estado == "CONCILIADO"
    assert len(previsto.conciliaciones) == 1



def test_saldo_movimientos_sin_conciliaciones(
    session,
    inmueble,
) -> None:
    """Sin asociaciones, todo el importe permanece pendiente."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Alquiler octubre",
        referencia_bancaria="",
        huella_importacion="a" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        contraparte="Inquilino",
        estado="PENDIENTE",
    )

    session.add_all([bancario, previsto])
    session.commit()

    # Ninguno de los dos movimientos ha sido conciliado.
    assert saldo_movimiento_bancario(bancario) == (
        0,
        100000,
    )

    assert saldo_movimiento_previsto(previsto) == (
        0,
        100000,
    )



def test_saldo_bancario_con_varios_previstos(
    session,
    inmueble,
) -> None:
    """Suma las asociaciones de un banco con varios previstos."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=104500,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Alquiler y agua",
        referencia_bancaria="",
        huella_importacion="b" * 64,
        estado="CONCILIADO",
    )

    alquiler = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        contraparte="Inquilino",
        estado="CONCILIADO",
    )

    agua = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Reembolso de agua",
        importe_esperado=4500,
        contraparte="Inquilino",
        estado="CONCILIADO",
    )

    # El único movimiento bancario justifica dos cobros previstos.
    conciliaciones = [
        Conciliacion(
            movimiento_bancario=bancario,
            movimiento_previsto=alquiler,
            importe_asociado=100000,
        ),
        Conciliacion(
            movimiento_bancario=bancario,
            movimiento_previsto=agua,
            importe_asociado=4500,
        ),
    ]

    session.add_all(conciliaciones)
    session.commit()

    # El banco está totalmente asociado.
    assert saldo_movimiento_bancario(bancario) == (
        104500,
        0,
    )

    # Cada previsto tiene asociada su parte.
    assert saldo_movimiento_previsto(alquiler) == (
        100000,
        0,
    )

    assert saldo_movimiento_previsto(agua) == (
        4500,
        0,
    )



def test_saldo_previsto_con_varios_bancarios(
    session,
    inmueble,
) -> None:
    """Calcula el pendiente tras pagos sucesivos del mismo previsto."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        contraparte="Inquilino",
        estado="PARCIAL",
    )

    bancario_a = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=60000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Primer pago",
        referencia_bancaria="",
        huella_importacion="c" * 64,
        estado="CONCILIADO",
    )

    bancario_b = MovimientoBancario(
        fecha=date(2026, 10, 7),
        naturaleza="INGRESO",
        importe=40000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Segundo pago",
        referencia_bancaria="",
        huella_importacion="d" * 64,
        estado="PENDIENTE",
    )

    primera = Conciliacion(
        movimiento_bancario=bancario_a,
        movimiento_previsto=previsto,
        importe_asociado=60000,
    )

    session.add_all([
        primera,
        bancario_b,
    ])
    session.commit()

    # Después del primer ingreso faltan 400 euros.
    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )

    assert saldo_movimiento_bancario(bancario_a) == (
        60000,
        0,
    )

    assert saldo_movimiento_bancario(bancario_b) == (
        0,
        40000,
    )

    # El segundo ingreso completa el importe previsto.
    segunda = Conciliacion(
        movimiento_bancario=bancario_b,
        movimiento_previsto=previsto,
        importe_asociado=40000,
    )

    session.add(segunda)
    session.commit()

    assert saldo_movimiento_previsto(previsto) == (
        100000,
        0,
    )

    assert saldo_movimiento_bancario(bancario_b) == (
        40000,
        0,
    )



def test_validar_asociacion_completa(inmueble) -> None:
    """Acepta asociar dos movimientos pendientes por su importe total."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="v" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    # El usuario asocia exactamente 1.000 euros.
    assert validar_asociacion(
        bancario,
        previsto,
        100000,
    ) is None


def test_validar_asociacion_parcial(inmueble) -> None:
    """Permite asociar sólo parte del importe disponible."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=60000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="w" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    # Una transferencia de 600 euros paga parte de un alquiler.
    assert validar_asociacion(
        bancario,
        previsto,
        60000,
    ) is None


def test_validar_asociacion_rechaza_naturaleza_distinta(
    inmueble,
) -> None:
    """No relaciona un ingreso bancario con un gasto previsto."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=10000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="x" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Recibo de agua",
        importe_esperado=10000,
        estado="PENDIENTE",
    )

    with pytest.raises(
        ConciliacionError,
        match="naturaleza",
    ):
        validar_asociacion(
            bancario,
            previsto,
            10000,
        )


@pytest.mark.parametrize("importe", [0, -1, -100])
def test_validar_asociacion_rechaza_importe_no_positivo(
    inmueble,
    importe,
) -> None:
    """El importe asociado debe ser mayor que cero."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=10000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="y" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=10000,
        estado="PENDIENTE",
    )

    with pytest.raises(
        ConciliacionError,
        match="positivo",
    ):
        validar_asociacion(
            bancario,
            previsto,
            importe,
        )


@pytest.mark.parametrize(
    ("importe_bancario", "importe_previsto", "importe_asociado"),
    [
        (10000, 20000, 15000),
        (20000, 10000, 15000),
    ],
)
def test_validar_asociacion_rechaza_superar_importe_disponible(
    inmueble,
    importe_bancario,
    importe_previsto,
    importe_asociado,
) -> None:
    """No permite asociar más dinero del disponible en ningún lado."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=importe_bancario,
        tipo_original="TRANSFERENCIA",
        huella_importacion="z" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Cobro previsto",
        importe_esperado=importe_previsto,
        estado="PENDIENTE",
    )

    with pytest.raises(
        ConciliacionError,
        match="disponible",
    ):
        validar_asociacion(
            bancario,
            previsto,
            importe_asociado,
        )


@pytest.mark.parametrize(
    ("estado_bancario", "estado_previsto"),
    [
        ("DESCARTADO", "PENDIENTE"),
        ("CONCILIADO", "PENDIENTE"),
        ("PENDIENTE", "CANCELADO"),
        ("PENDIENTE", "CONCILIADO"),
    ],
)
def test_validar_asociacion_rechaza_estados_no_disponibles(
    inmueble,
    estado_bancario,
    estado_previsto,
) -> None:
    """Sólo admite movimientos pendientes o parcialmente conciliados."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=10000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="s" * 64,
        estado=estado_bancario,
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Cobro previsto",
        importe_esperado=10000,
        estado=estado_previsto,
    )

    with pytest.raises(
        ConciliacionError,
        match="estado",
    ):
        validar_asociacion(
            bancario,
            previsto,
            10000,
        )


def test_validar_asociacion_admite_previsto_parcial(
    inmueble,
) -> None:
    """Una previsión parcial puede recibir nuevas asociaciones."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=40000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="t" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        estado="PARCIAL",
    )

    # En la siguiente fase habrá asociaciones previas persistidas.
    # Aquí comprobamos únicamente que PARCIAL es un estado permitido.
    assert validar_asociacion(
        bancario,
        previsto,
        40000,
    ) is None



def test_validar_asociacion_respeta_saldo_bancario_restante(
    session,
    inmueble,
) -> None:
    """No permite gastar dos veces el importe de un movimiento bancario."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="u" * 64,
        estado="PENDIENTE",
    )

    primero = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=60000,
        estado="CONCILIADO",
    )

    segundo = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Agua",
        importe_esperado=50000,
        estado="PENDIENTE",
    )

    session.add_all([
        Conciliacion(
            movimiento_bancario=bancario,
            movimiento_previsto=primero,
            importe_asociado=60000,
        ),
        segundo,
    ])
    session.commit()

    # El banco tiene asociados 600 euros; sólo quedan 400.
    with pytest.raises(
        ConciliacionError,
        match="disponible",
    ):
        validar_asociacion(
            bancario,
            segundo,
            50000,
        )


def test_validar_asociacion_respeta_saldo_previsto_restante(
    session,
    inmueble,
) -> None:
    """No permite cobrar dos veces el importe de un movimiento previsto."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        estado="PARCIAL",
    )

    bancario_primero = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=60000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="q" * 64,
        estado="CONCILIADO",
    )

    bancario_segundo = MovimientoBancario(
        fecha=date(2026, 10, 7),
        naturaleza="INGRESO",
        importe=50000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="r" * 64,
        estado="PENDIENTE",
    )

    session.add_all([
        Conciliacion(
            movimiento_bancario=bancario_primero,
            movimiento_previsto=previsto,
            importe_asociado=60000,
        ),
        bancario_segundo,
    ])
    session.commit()

    # Al alquiler le quedan 400 euros por asociar, no 500.
    with pytest.raises(
        ConciliacionError,
        match="disponible",
    ):
        validar_asociacion(
            bancario_segundo,
            previsto,
            50000,
        )



def test_validar_asociacion_rechaza_pareja_duplicada(
    session,
    inmueble,
) -> None:
    """Una pareja ya asociada no puede asociarse de nuevo."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="j" * 64,
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        estado="PARCIAL",
    )

    session.add(
        Conciliacion(
            movimiento_bancario=bancario,
            movimiento_previsto=previsto,
            importe_asociado=40000,
        )
    )
    session.commit()

    # Aunque queden importes disponibles, la pareja ya existe.
    with pytest.raises(
        ConciliacionError,
        match="asociad",
    ):
        validar_asociacion(
            bancario,
            previsto,
            10000,
        )



def test_asociar_movimientos_crea_asociacion_parcial(
    session,
    inmueble,
) -> None:
    """Crea una asociación parcial y permite persistirla."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=60000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Pago parcial",
        huella_importacion="asociar-parcial",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    session.add_all([bancario, previsto])
    session.flush()

    # El usuario relaciona 600 euros de un alquiler de 1.000.
    conciliacion = asociar_movimientos(
        bancario,
        previsto,
        60000,
    )

    assert isinstance(conciliacion, Conciliacion)
    assert conciliacion.movimiento_bancario is bancario
    assert conciliacion.movimiento_previsto is previsto
    assert conciliacion.importe_asociado == 60000

    # La función no cambia los estados ni confirma la transacción.
    assert bancario.estado == "PENDIENTE"
    assert previsto.estado == "PENDIENTE"

    session.add(conciliacion)
    session.commit()

    session.expire_all()

    guardada = session.get(
        Conciliacion,
        conciliacion.id,
    )

    assert guardada is not None
    assert guardada.importe_asociado == 60000
    assert guardada.movimiento_bancario_id == bancario.id
    assert guardada.movimiento_previsto_id == previsto.id

    assert saldo_movimiento_bancario(bancario) == (
        60000,
        0,
    )
    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )



def test_asociar_movimientos_un_bancario_varios_previstos(
    session,
    inmueble,
) -> None:
    """Permite relacionar un ingreso bancario con dos previstos."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=104500,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Alquiler y agua",
        huella_importacion="asociar-agrupado",
        estado="PENDIENTE",
    )

    alquiler = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    agua = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Reembolso de agua",
        importe_esperado=4500,
        estado="PENDIENTE",
    )

    session.add_all([bancario, alquiler, agua])
    session.flush()

    primera = asociar_movimientos(
        bancario,
        alquiler,
        100000,
    )

    session.add(primera)
    session.flush()

    segunda = asociar_movimientos(
        bancario,
        agua,
        4500,
    )

    session.add(segunda)
    session.commit()

    assert primera.id != segunda.id

    assert saldo_movimiento_bancario(bancario) == (
        104500,
        0,
    )
    assert saldo_movimiento_previsto(alquiler) == (
        100000,
        0,
    )
    assert saldo_movimiento_previsto(agua) == (
        4500,
        0,
    )



def test_asociar_movimientos_un_previsto_varios_bancarios(
    session,
    inmueble,
) -> None:
    """Permite relacionar dos transferencias con un previsto."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    primero = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=60000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="asociar-pago-1",
        estado="PENDIENTE",
    )

    segundo = MovimientoBancario(
        fecha=date(2026, 10, 7),
        naturaleza="INGRESO",
        importe=40000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="asociar-pago-2",
        estado="PENDIENTE",
    )

    session.add_all([previsto, primero, segundo])
    session.flush()

    primera = asociar_movimientos(
        primero,
        previsto,
        60000,
    )

    session.add(primera)
    session.flush()

    segunda = asociar_movimientos(
        segundo,
        previsto,
        40000,
    )

    session.add(segunda)
    session.commit()

    assert primera.id != segunda.id

    assert saldo_movimiento_previsto(previsto) == (
        100000,
        0,
    )
    assert saldo_movimiento_bancario(primero) == (
        60000,
        0,
    )
    assert saldo_movimiento_bancario(segundo) == (
        40000,
        0,
    )



def test_asociar_movimientos_rechaza_importe_excesivo(
    session,
    inmueble,
) -> None:
    """Una asociación inválida no crea relaciones."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=50000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="asociar-exceso",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    session.add_all([bancario, previsto])
    session.flush()

    # Se intenta asociar 600 euros de un ingreso de sólo 500.
    with pytest.raises(
        ConciliacionError,
        match="disponible",
    ):
        asociar_movimientos(
            bancario,
            previsto,
            60000,
        )

    assert bancario.conciliaciones == []
    assert previsto.conciliaciones == []

    session.commit()

    assert session.query(Conciliacion).count() == 0



@pytest.mark.parametrize(
    ("importe_asociado", "estado_esperado"),
    [
        (0, "PENDIENTE"),
        (40000, "PARCIAL"),
        (100000, "CONCILIADO"),
    ],
)
def test_actualizar_estado_bancario_segun_asociaciones(
    inmueble,
    importe_asociado,
    estado_esperado,
) -> None:
    """El estado bancario depende del importe asociado."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="estado-bancario",
        estado="PENDIENTE",
    )

    if importe_asociado:
        previsto = MovimientoPrevisto(
            inmueble=inmueble,
            naturaleza="INGRESO",
            concepto="Alquiler",
            importe_esperado=100000,
            estado="PENDIENTE",
        )

        bancario.conciliaciones.append(
            Conciliacion(
                movimiento_previsto=previsto,
                importe_asociado=importe_asociado,
            )
        )

    # El usuario confirma una asociación bancaria.
    actualizar_estado_movimiento_bancario(bancario)

    assert bancario.estado == estado_esperado



@pytest.mark.parametrize(
    ("importe_asociado", "estado_esperado"),
    [
        (0, "PENDIENTE"),
        (40000, "PARCIAL"),
        (100000, "CONCILIADO"),
    ],
)
def test_actualizar_estado_previsto_segun_asociaciones(
    inmueble,
    importe_asociado,
    estado_esperado,
) -> None:
    """El estado previsto depende del importe asociado."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    if importe_asociado:
        bancario = MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=100000,
            tipo_original="TRANSFERENCIA",
            huella_importacion="estado-previsto",
            estado="PENDIENTE",
        )

        previsto.conciliaciones.append(
            Conciliacion(
                movimiento_bancario=bancario,
                importe_asociado=importe_asociado,
            )
        )

    # Se recalcula el estado después de asociar el cobro.
    actualizar_estado_movimiento_previsto(previsto)

    assert previsto.estado == estado_esperado

    if importe_asociado:
        assert previsto.metodo_conciliacion == "INDIVIDUAL"
    else:
        assert previsto.metodo_conciliacion is None



def test_actualizar_estado_previsto_respeta_conciliacion_manual(
    inmueble,
) -> None:
    """No convierte en pendiente un movimiento resuelto manualmente."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Gasto pagado en efectivo",
        importe_esperado=7500,
        estado="CONCILIADO",
        metodo_conciliacion="MANUAL",
        notas="Pagado en efectivo",
    )

    # No hay asociaciones bancarias, porque el pago fue en efectivo.
    actualizar_estado_movimiento_previsto(previsto)

    assert previsto.estado == "CONCILIADO"
    assert previsto.metodo_conciliacion == "MANUAL"
    assert previsto.notas == "Pagado en efectivo"



def test_actualizar_estados_tras_retirar_una_asociacion(
    inmueble,
) -> None:
    """Al retirar una asociación, se recuperan los estados correctos."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    bancario_a = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=60000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="estado-retirar-a",
        estado="PENDIENTE",
    )

    bancario_b = MovimientoBancario(
        fecha=date(2026, 10, 7),
        naturaleza="INGRESO",
        importe=40000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="estado-retirar-b",
        estado="PENDIENTE",
    )

    primera = Conciliacion(
        movimiento_bancario=bancario_a,
        importe_asociado=60000,
    )

    segunda = Conciliacion(
        movimiento_bancario=bancario_b,
        importe_asociado=40000,
    )

    previsto.conciliaciones.extend([primera, segunda])

    actualizar_estado_movimiento_previsto(previsto)
    actualizar_estado_movimiento_bancario(bancario_a)
    actualizar_estado_movimiento_bancario(bancario_b)

    assert previsto.estado == "CONCILIADO"
    assert bancario_a.estado == "CONCILIADO"
    assert bancario_b.estado == "CONCILIADO"

    # Se descubre que la segunda transferencia se asoció por error.
    previsto.conciliaciones.remove(segunda)
    bancario_b.conciliaciones.remove(segunda)

    actualizar_estado_movimiento_previsto(previsto)
    actualizar_estado_movimiento_bancario(bancario_b)

    assert previsto.estado == "PARCIAL"
    assert bancario_a.estado == "CONCILIADO"
    assert bancario_b.estado == "PENDIENTE"



def test_movimiento_bancario_permite_estado_parcial(
    session,
) -> None:
    """La base de datos admite un movimiento parcialmente conciliado."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="estado-parcial-sqlite",
        estado="PARCIAL",
    )

    session.add(bancario)
    session.commit()

    session.expire_all()

    guardado = session.get(
        MovimientoBancario,
        bancario.id,
    )

    assert guardado is not None
    assert guardado.estado == "PARCIAL"



def test_confirmar_grupo_un_bancario_dos_previstos(
    session,
    inmueble,
) -> None:
    """Confirma conjuntamente un alquiler y un reembolso."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=104500,
        tipo_original="TRANSFERENCIA",
        huella_importacion="grupo-bancario",
        estado="PENDIENTE",
    )

    alquiler = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    agua = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Reembolso de agua",
        importe_esperado=4500,
        estado="PENDIENTE",
    )

    session.add_all([bancario, alquiler, agua])
    session.flush()

    # El usuario confirma dos obligaciones contra un ingreso.
    conciliaciones = confirmar_grupo_conciliacion([
        (bancario, alquiler, 100000),
        (bancario, agua, 4500),
    ])

    assert len(conciliaciones) == 2
    assert [c.importe_asociado for c in conciliaciones] == [
        100000,
        4500,
    ]

    assert bancario.estado == "CONCILIADO"
    assert alquiler.estado == "CONCILIADO"
    assert agua.estado == "CONCILIADO"

    assert alquiler.metodo_conciliacion == "INDIVIDUAL"
    assert agua.metodo_conciliacion == "INDIVIDUAL"

    session.add_all(conciliaciones)
    session.commit()

    assert saldo_movimiento_bancario(bancario) == (
        104500,
        0,
    )
    assert saldo_movimiento_previsto(alquiler) == (
        100000,
        0,
    )
    assert saldo_movimiento_previsto(agua) == (
        4500,
        0,
    )



def test_confirmar_grupo_dos_bancarios_un_previsto(
    session,
    inmueble,
) -> None:
    """Confirma dos transferencias contra un único alquiler."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    primero = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=60000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="grupo-transferencia-1",
        estado="PENDIENTE",
    )

    segundo = MovimientoBancario(
        fecha=date(2026, 10, 7),
        naturaleza="INGRESO",
        importe=40000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="grupo-transferencia-2",
        estado="PENDIENTE",
    )

    session.add_all([previsto, primero, segundo])
    session.flush()

    conciliaciones = confirmar_grupo_conciliacion([
        (primero, previsto, 60000),
        (segundo, previsto, 40000),
    ])

    assert len(conciliaciones) == 2

    assert primero.estado == "CONCILIADO"
    assert segundo.estado == "CONCILIADO"
    assert previsto.estado == "CONCILIADO"
    assert previsto.metodo_conciliacion == "INDIVIDUAL"

    session.add_all(conciliaciones)
    session.commit()

    assert saldo_movimiento_previsto(previsto) == (
        100000,
        0,
    )



def test_confirmar_grupo_admite_asociacion_parcial(
    session,
    inmueble,
) -> None:
    """La confirmación puede dejar saldo pendiente en ambos lados."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=80000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="grupo-parcial",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    session.add_all([bancario, previsto])
    session.flush()

    conciliaciones = confirmar_grupo_conciliacion([
        (bancario, previsto, 60000),
    ])

    assert len(conciliaciones) == 1
    assert conciliaciones[0].importe_asociado == 60000

    assert bancario.estado == "PARCIAL"
    assert previsto.estado == "PARCIAL"
    assert previsto.metodo_conciliacion == "INDIVIDUAL"

    session.add_all(conciliaciones)
    session.commit()

    assert saldo_movimiento_bancario(bancario) == (
        60000,
        20000,
    )
    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )



def test_confirmar_grupo_rechaza_exceso_sin_modificar_nada(
    session,
    inmueble,
) -> None:
    """Si el grupo supera el importe disponible, no aplica nada."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="grupo-exceso",
        estado="PENDIENTE",
    )

    primero = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=70000,
        estado="PENDIENTE",
    )

    segundo = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Otros gastos",
        importe_esperado=40000,
        estado="PENDIENTE",
    )

    session.add_all([bancario, primero, segundo])
    session.flush()

    # Cada asociación cabe por separado, pero juntas suman 1.100 €.
    with pytest.raises(ConciliacionError):
        confirmar_grupo_conciliacion([
            (bancario, primero, 70000),
            (bancario, segundo, 40000),
        ])

    assert bancario.estado == "PENDIENTE"
    assert primero.estado == "PENDIENTE"
    assert segundo.estado == "PENDIENTE"

    assert bancario.conciliaciones == []
    assert primero.conciliaciones == []
    assert segundo.conciliaciones == []

    session.flush()

    assert session.query(Conciliacion).count() == 0



def test_confirmar_grupo_rechaza_naturaleza_sin_efectos(
    session,
    inmueble,
) -> None:
    """Un error en la segunda asociación invalida el grupo entero."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="grupo-naturaleza",
        estado="PENDIENTE",
    )

    alquiler = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=60000,
        estado="PENDIENTE",
    )

    gasto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Recibo de agua",
        importe_esperado=40000,
        estado="PENDIENTE",
    )

    session.add_all([bancario, alquiler, gasto])
    session.flush()

    with pytest.raises(
        ConciliacionError,
        match="naturaleza",
    ):
        confirmar_grupo_conciliacion([
            (bancario, alquiler, 60000),
            (bancario, gasto, 40000),
        ])

    assert bancario.estado == "PENDIENTE"
    assert alquiler.estado == "PENDIENTE"
    assert gasto.estado == "PENDIENTE"

    assert bancario.conciliaciones == []
    assert alquiler.conciliaciones == []
    assert gasto.conciliaciones == []

    session.flush()

    assert session.query(Conciliacion).count() == 0



def test_confirmar_grupo_rechaza_pareja_repetida(
    session,
    inmueble,
) -> None:
    """No admite dos asociaciones para la misma pareja en un grupo."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="grupo-duplicado",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    session.add_all([bancario, previsto])
    session.flush()

    with pytest.raises(ConciliacionError):
        confirmar_grupo_conciliacion([
            (bancario, previsto, 40000),
            (bancario, previsto, 60000),
        ])

    assert bancario.estado == "PENDIENTE"
    assert previsto.estado == "PENDIENTE"

    assert bancario.conciliaciones == []
    assert previsto.conciliaciones == []

    session.flush()

    assert session.query(Conciliacion).count() == 0



def test_confirmar_grupo_rechaza_grupo_vacio() -> None:
    """Una confirmación necesita al menos una asociación."""

    with pytest.raises(ConciliacionError):
        confirmar_grupo_conciliacion([])



def test_confirmar_grupo_completa_previsto_parcial(
    session,
    inmueble,
) -> None:
    """Completa un previsto parcial sin perder su conciliación anterior."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        estado="PARCIAL",
        metodo_conciliacion="INDIVIDUAL",
    )

    primer_bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=60000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="completar-previsto-1",
        estado="CONCILIADO",
    )

    segundo_bancario = MovimientoBancario(
        fecha=date(2026, 10, 7),
        naturaleza="INGRESO",
        importe=40000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="completar-previsto-2",
        estado="PENDIENTE",
    )

    primera = Conciliacion(
        movimiento_bancario=primer_bancario,
        movimiento_previsto=previsto,
        importe_asociado=60000,
    )

    session.add_all([primera, segundo_bancario])
    session.commit()

    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )

    # El usuario confirma el segundo ingreso.
    conciliaciones = confirmar_grupo_conciliacion([
        (segundo_bancario, previsto, 40000),
    ])

    assert len(conciliaciones) == 1

    # Los estados deben actualizarse antes de guardar.
    assert previsto.estado == "CONCILIADO"
    assert segundo_bancario.estado == "CONCILIADO"
    assert primer_bancario.estado == "CONCILIADO"

    session.add_all(conciliaciones)
    session.commit()

    session.expire_all()

    # Se conservan las dos asociaciones.
    assert saldo_movimiento_previsto(previsto) == (
        100000,
        0,
    )

    assert len(previsto.conciliaciones) == 2
    assert sorted(
        c.importe_asociado
        for c in previsto.conciliaciones
    ) == [40000, 60000]

    assert previsto.estado == "CONCILIADO"
    assert previsto.metodo_conciliacion == "INDIVIDUAL"



def test_confirmar_grupo_completa_bancario_parcial(
    session,
    inmueble,
) -> None:
    """Completa un bancario parcial conservando su asociación previa."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=104500,
        tipo_original="TRANSFERENCIA",
        huella_importacion="completar-bancario",
        estado="PARCIAL",
    )

    alquiler = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        estado="CONCILIADO",
        metodo_conciliacion="INDIVIDUAL",
    )

    agua = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Reembolso de agua",
        importe_esperado=4500,
        estado="PENDIENTE",
    )

    primera = Conciliacion(
        movimiento_bancario=bancario,
        movimiento_previsto=alquiler,
        importe_asociado=100000,
    )

    session.add_all([primera, agua])
    session.commit()

    assert saldo_movimiento_bancario(bancario) == (
        100000,
        4500,
    )

    # El usuario incorpora el reembolso pendiente.
    conciliaciones = confirmar_grupo_conciliacion([
        (bancario, agua, 4500),
    ])

    assert len(conciliaciones) == 1

    # La confirmación debe recalcular ambos estados inmediatamente.
    assert bancario.estado == "CONCILIADO"
    assert agua.estado == "CONCILIADO"
    assert alquiler.estado == "CONCILIADO"

    session.add_all(conciliaciones)
    session.commit()

    session.expire_all()

    assert saldo_movimiento_bancario(bancario) == (
        104500,
        0,
    )

    assert len(bancario.conciliaciones) == 2
    assert sorted(
        c.importe_asociado
        for c in bancario.conciliaciones
    ) == [4500, 100000]

    assert bancario.estado == "CONCILIADO"
    assert agua.estado == "CONCILIADO"
    assert agua.metodo_conciliacion == "INDIVIDUAL"



def test_confirmar_grupo_actualiza_estados_antes_de_persistir(
    session,
    inmueble,
) -> None:
    """Los estados reflejan las asociaciones sin esperar al commit."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=80000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="estados-sin-commit",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    session.add_all([bancario, previsto])
    session.flush()

    conciliaciones = confirmar_grupo_conciliacion([
        (bancario, previsto, 60000),
    ])

    # Todavía no hemos añadido la conciliación a la sesión.
    assert conciliaciones[0] not in session

    # Ambos movimientos deben reflejar los 600 euros asociados.
    assert bancario.estado == "PARCIAL"
    assert previsto.estado == "PARCIAL"
    assert previsto.metodo_conciliacion == "INDIVIDUAL"

    session.add_all(conciliaciones)
    session.commit()

    session.expire_all()

    assert bancario.estado == "PARCIAL"
    assert previsto.estado == "PARCIAL"

    assert saldo_movimiento_bancario(bancario) == (
        60000,
        20000,
    )
    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )



def test_deshacer_asociacion_bancaria_individual(
    session,
    inmueble,
) -> None:
    """Deshace una conciliación 1:1 y restaura ambos movimientos."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="deshacer-individual",
        estado="CONCILIADO",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        estado="CONCILIADO",
        metodo_conciliacion="INDIVIDUAL",
    )

    conciliacion = Conciliacion(
        movimiento_bancario=bancario,
        movimiento_previsto=previsto,
        importe_asociado=100000,
    )

    session.add(conciliacion)
    session.commit()

    conciliacion_id = conciliacion.id

    # El usuario deshace la asociación que confirmó por error.
    deshacer_asociacion_bancaria(conciliacion)

    assert bancario.estado == "PENDIENTE"
    assert previsto.estado == "PENDIENTE"
    assert previsto.metodo_conciliacion is None

    assert saldo_movimiento_bancario(bancario) == (
        0,
        100000,
    )
    assert saldo_movimiento_previsto(previsto) == (
        0,
        100000,
    )

    session.commit()
    session.expire_all()

    assert session.get(Conciliacion, conciliacion_id) is None
    assert bancario.estado == "PENDIENTE"
    assert previsto.estado == "PENDIENTE"



def test_deshacer_asociacion_conserva_otros_previstos(
    session,
    inmueble,
) -> None:
    """Retira una asociación y conserva las demás del mismo banco."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=104500,
        tipo_original="TRANSFERENCIA",
        huella_importacion="deshacer-banco-grupo",
        estado="CONCILIADO",
    )

    alquiler = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        estado="CONCILIADO",
        metodo_conciliacion="INDIVIDUAL",
    )

    agua = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Agua",
        importe_esperado=4500,
        estado="CONCILIADO",
        metodo_conciliacion="INDIVIDUAL",
    )

    primera = Conciliacion(
        movimiento_bancario=bancario,
        movimiento_previsto=alquiler,
        importe_asociado=100000,
    )

    segunda = Conciliacion(
        movimiento_bancario=bancario,
        movimiento_previsto=agua,
        importe_asociado=4500,
    )

    session.add_all([primera, segunda])
    session.commit()

    primera_id = primera.id
    segunda_id = segunda.id

    # Sólo se retira el reembolso de agua.
    deshacer_asociacion_bancaria(segunda)

    assert bancario.estado == "PARCIAL"
    assert alquiler.estado == "CONCILIADO"
    assert agua.estado == "PENDIENTE"
    assert agua.metodo_conciliacion is None

    assert saldo_movimiento_bancario(bancario) == (
        100000,
        4500,
    )

    session.commit()
    session.expire_all()

    assert session.get(Conciliacion, primera_id) is not None
    assert session.get(Conciliacion, segunda_id) is None

    assert saldo_movimiento_previsto(alquiler) == (
        100000,
        0,
    )
    assert saldo_movimiento_previsto(agua) == (
        0,
        4500,
    )



def test_deshacer_asociacion_conserva_otros_bancarios(
    session,
    inmueble,
) -> None:
    """Al retirar una transferencia, el previsto vuelve a parcial."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        estado="CONCILIADO",
        metodo_conciliacion="INDIVIDUAL",
    )

    primero = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=60000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="deshacer-transferencia-1",
        estado="CONCILIADO",
    )

    segundo = MovimientoBancario(
        fecha=date(2026, 10, 7),
        naturaleza="INGRESO",
        importe=40000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="deshacer-transferencia-2",
        estado="CONCILIADO",
    )

    primera = Conciliacion(
        movimiento_bancario=primero,
        movimiento_previsto=previsto,
        importe_asociado=60000,
    )

    segunda = Conciliacion(
        movimiento_bancario=segundo,
        movimiento_previsto=previsto,
        importe_asociado=40000,
    )

    session.add_all([primera, segunda])
    session.commit()

    primera_id = primera.id
    segunda_id = segunda.id

    # Se descubre que la segunda transferencia era de otro concepto.
    deshacer_asociacion_bancaria(segunda)

    assert primero.estado == "CONCILIADO"
    assert segundo.estado == "PENDIENTE"
    assert previsto.estado == "PARCIAL"
    assert previsto.metodo_conciliacion == "INDIVIDUAL"

    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )

    session.commit()
    session.expire_all()

    assert session.get(Conciliacion, primera_id) is not None
    assert session.get(Conciliacion, segunda_id) is None

    assert len(previsto.conciliaciones) == 1
    assert saldo_movimiento_bancario(primero) == (
        60000,
        0,
    )
    assert saldo_movimiento_bancario(segundo) == (
        0,
        40000,
    )




def test_deshacer_asociacion_rechaza_no_persistida(
    session,
    inmueble,
) -> None:
    """No permite deshacer una asociación todavía no guardada."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        huella_importacion="deshacer-no-persistida",
        estado="PENDIENTE",
    )

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler",
        importe_esperado=100000,
        estado="PENDIENTE",
    )

    session.add_all([bancario, previsto])
    session.commit()

    # Los movimientos están guardados, pero la asociación no.
    conciliacion = Conciliacion(
        movimiento_bancario=bancario,
        movimiento_previsto=previsto,
        importe_asociado=100000,
    )

    with pytest.raises(
        ConciliacionError,
        match="guardad|persistid",
    ):
        deshacer_asociacion_bancaria(conciliacion)

    assert bancario.estado == "PENDIENTE"
    assert previsto.estado == "PENDIENTE"

    # La operación rechazada no debe haber persistido la asociación.
    assert session.scalars(select(Conciliacion)).all() == []



def test_proponer_grupo_un_previsto_dos_bancarios(inmueble):
    """Detecta dos ingresos bancarios que completan un previsto."""

    previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler de octubre",
        importe_esperado=100000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    bancario_1 = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=60000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Juan Pérez alquiler",
        referencia_bancaria="",
        huella_importacion="grupo-1n-1",
        estado="PENDIENTE",
    )

    bancario_2 = MovimientoBancario(
        fecha=date(2026, 10, 7),
        naturaleza="INGRESO",
        importe=40000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Juan Pérez alquiler",
        referencia_bancaria="",
        huella_importacion="grupo-1n-2",
        estado="PENDIENTE",
    )

    propuestas = buscar_propuestas_agrupadas(
        [bancario_1, bancario_2],
        [previsto],
    )

    assert len(propuestas) == 1

    propuesta = propuestas[0]

    assert propuesta.previstos == [previsto]
    assert propuesta.bancarios == [bancario_1, bancario_2]
    assert propuesta.puntuacion > 0
    assert propuesta.motivos

    assert previsto.estado == "PENDIENTE"
    assert bancario_1.estado == "PENDIENTE"
    assert bancario_2.estado == "PENDIENTE"


def test_proponer_grupo_dos_previstos_un_bancario(inmueble):
    """Detecta un ingreso que cubre dos movimientos previstos."""

    alquiler = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler de octubre",
        importe_esperado=90000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    agua = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Reembolso de agua",
        importe_esperado=4500,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=94500,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Juan Pérez alquiler y agua",
        referencia_bancaria="",
        huella_importacion="grupo-m1-1",
        estado="PENDIENTE",
    )

    propuestas = buscar_propuestas_agrupadas(
        [bancario],
        [alquiler, agua],
    )

    assert len(propuestas) == 1

    propuesta = propuestas[0]

    assert propuesta.previstos == [alquiler, agua]
    assert propuesta.bancarios == [bancario]
    assert propuesta.puntuacion > 0
    assert propuesta.motivos

    assert alquiler.estado == "PENDIENTE"
    assert agua.estado == "PENDIENTE"
    assert bancario.estado == "PENDIENTE"



def test_proponer_grupo_con_previsto_parcial(
    session,
    inmueble,
) -> None:
    """Propone dos bancarios para completar un previsto parcial."""

    previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler de octubre",
        importe_esperado=100000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    bancario_anterior = MovimientoBancario(
        fecha=date(2026, 10, 3),
        naturaleza="INGRESO",
        importe=60000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Juan Pérez primer pago",
        referencia_bancaria="",
        huella_importacion="parcial-previsto-anterior",
        estado="PENDIENTE",
    )

    bancario_1 = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=25000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Juan Pérez segundo pago",
        referencia_bancaria="",
        huella_importacion="parcial-previsto-1",
        estado="PENDIENTE",
    )

    bancario_2 = MovimientoBancario(
        fecha=date(2026, 10, 7),
        naturaleza="INGRESO",
        importe=15000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Juan Pérez tercer pago",
        referencia_bancaria="",
        huella_importacion="parcial-previsto-2",
        estado="PENDIENTE",
    )

    session.add_all([
        previsto,
        bancario_anterior,
        bancario_1,
        bancario_2,
    ])
    session.flush()

    conciliaciones = confirmar_grupo_conciliacion([
        (bancario_anterior, previsto, 60000),
    ])
    session.add_all(conciliaciones)
    session.commit()

    assert previsto.estado == "PARCIAL"
    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )

    propuestas = buscar_propuestas_agrupadas(
        [bancario_1, bancario_2],
        [previsto],
    )

    assert len(propuestas) == 1

    propuesta = propuestas[0]

    assert propuesta.previstos == [previsto]
    assert propuesta.bancarios == [bancario_1, bancario_2]
    assert propuesta.puntuacion > 0
    assert propuesta.motivos

    # Buscar propuestas no altera las asociaciones existentes.
    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )
    assert previsto.estado == "PARCIAL"
    assert bancario_1.estado == "PENDIENTE"
    assert bancario_2.estado == "PENDIENTE"



def test_proponer_grupo_con_bancario_parcial(
    session,
    inmueble,
) -> None:
    """Propone dos previstos para completar un bancario parcial."""

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=100000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Juan Pérez varios conceptos",
        referencia_bancaria="",
        huella_importacion="parcial-bancario",
        estado="PENDIENTE",
    )

    previsto_anterior = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler pendiente",
        importe_esperado=60000,
        contraparte="Juan Pérez",
    )

    previsto_1 = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Reembolso de agua",
        importe_esperado=25000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    previsto_2 = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Reembolso de comunidad",
        importe_esperado=15000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    session.add_all([
        bancario,
        previsto_anterior,
        previsto_1,
        previsto_2,
    ])
    session.flush()

    conciliaciones = confirmar_grupo_conciliacion([
        (bancario, previsto_anterior, 60000),
    ])
    session.add_all(conciliaciones)
    session.commit()

    assert bancario.estado == "PARCIAL"
    assert saldo_movimiento_bancario(bancario) == (
        60000,
        40000,
    )

    propuestas = buscar_propuestas_agrupadas(
        [bancario],
        [previsto_1, previsto_2],
    )

    assert len(propuestas) == 1

    propuesta = propuestas[0]

    assert propuesta.bancarios == [bancario]
    assert propuesta.previstos == [previsto_1, previsto_2]
    assert propuesta.puntuacion > 0
    assert propuesta.motivos

    # La búsqueda no modifica el movimiento ya parcialmente conciliado.
    assert saldo_movimiento_bancario(bancario) == (
        60000,
        40000,
    )
    assert bancario.estado == "PARCIAL"
    assert previsto_1.estado == "PENDIENTE"
    assert previsto_2.estado == "PENDIENTE"



def test_proponer_grupo_descarta_ambiguedad_por_empate(
    inmueble,
) -> None:
    """No recomienda grupos incompatibles con igual puntuación."""

    previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    def transferencia(importe, referencia):
        return MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=importe,
            tipo_original="TRANSFERENCIA",
            descripcion_original="Juan Pérez alquiler",
            referencia_bancaria="",
            huella_importacion=referencia,
            estado="PENDIENTE",
        )

    bancario_600 = transferencia(
        60000,
        "ambiguo-600",
    )
    bancario_400_a = transferencia(
        40000,
        "ambiguo-400-a",
    )
    bancario_400_b = transferencia(
        40000,
        "ambiguo-400-b",
    )

    propuestas = buscar_propuestas_agrupadas(
        [bancario_600, bancario_400_a, bancario_400_b],
        [previsto],
    )

    assert propuestas == []

    # La detección no altera los movimientos.
    assert previsto.estado == "PENDIENTE"
    assert bancario_600.estado == "PENDIENTE"
    assert bancario_400_a.estado == "PENDIENTE"
    assert bancario_400_b.estado == "PENDIENTE"



def test_proponer_grupo_prefiere_mejor_puntuacion(
    inmueble,
) -> None:
    """Elige el mejor grupo cuando comparte movimientos con otro."""

    previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    bancario_600 = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="INGRESO",
        importe=60000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Juan Pérez primer pago",
        referencia_bancaria="",
        huella_importacion="mejor-600",
        estado="PENDIENTE",
    )

    bancario_400_bueno = MovimientoBancario(
        fecha=date(2026, 10, 6),
        naturaleza="INGRESO",
        importe=40000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Juan Pérez segundo pago",
        referencia_bancaria="",
        huella_importacion="mejor-400-bueno",
        estado="PENDIENTE",
    )

    bancario_400_peor = MovimientoBancario(
        fecha=date(2026, 10, 6),
        naturaleza="INGRESO",
        importe=40000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Ingreso sin identificar",
        referencia_bancaria="",
        huella_importacion="mejor-400-peor",
        estado="PENDIENTE",
    )

    propuestas = buscar_propuestas_agrupadas(
        [
            bancario_600,
            bancario_400_peor,
            bancario_400_bueno,
        ],
        [previsto],
    )

    assert len(propuestas) == 1

    propuesta = propuestas[0]

    assert propuesta.previstos == [previsto]
    assert propuesta.bancarios == [
        bancario_600,
        bancario_400_bueno,
    ]
    assert propuesta.puntuacion > 0

    assert previsto.estado == "PENDIENTE"
    assert bancario_600.estado == "PENDIENTE"
    assert bancario_400_bueno.estado == "PENDIENTE"
    assert bancario_400_peor.estado == "PENDIENTE"



def test_seleccionar_varias_propuestas_compatibles(inmueble):
    """Conserva propuestas compatibles aunque exista un conflicto intermedio."""

    def previsto(concepto, importe):
        return crear_movimiento_previsto(
            inmueble=inmueble,
            naturaleza="INGRESO",
            concepto=concepto,
            importe_esperado=importe,
        )

    def bancario(referencia, importe):
        return MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=importe,
            tipo_original="TRANSFERENCIA",
            descripcion_original=referencia,
            referencia_bancaria="",
            huella_importacion=referencia,
            estado="PENDIENTE",
        )

    p1 = previsto("Alquiler A", 10000)
    p2 = previsto("Alquiler B", 10000)

    b1 = bancario("transferencia-1", 6000)
    b2 = bancario("transferencia-2", 4000)
    b3 = bancario("transferencia-3", 6000)
    b4 = bancario("transferencia-4", 4000)

    # A y C no comparten ningún movimiento.
    propuesta_a = PropuestaConciliacion(
        previstos=[p1],
        bancarios=[b1, b2],
        puntuacion=150,
        motivos=["Suma exacta"],
    )

    # B entra en conflicto con A y con C.
    propuesta_b = PropuestaConciliacion(
        previstos=[p1, p2],
        bancarios=[b2, b3],
        puntuacion=180,
        motivos=["Alternativa"],
    )

    propuesta_c = PropuestaConciliacion(
        previstos=[p2],
        bancarios=[b3, b4],
        puntuacion=150,
        motivos=["Suma exacta"],
    )

    seleccionadas = _seleccionar_propuestas_agrupadas([
        propuesta_a,
        propuesta_b,
        propuesta_c,
    ])

    assert len(seleccionadas) == 2
    assert any(
        propuesta is propuesta_a
        for propuesta in seleccionadas
    )
    assert any(
        propuesta is propuesta_c
        for propuesta in seleccionadas
    )
    assert all(
        propuesta is not propuesta_b
        for propuesta in seleccionadas
    )



def test_seleccionar_propuestas_independientes(inmueble):
    """Mantiene todas las propuestas que no comparten movimientos."""

    previstos = [
        crear_movimiento_previsto(
            inmueble=inmueble,
            naturaleza="INGRESO",
            concepto=f"Alquiler {indice}",
            importe_esperado=10000,
        )
        for indice in range(2)
    ]

    bancarios = [
        MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=10000,
            tipo_original="TRANSFERENCIA",
            descripcion_original=f"Pago {indice}",
            referencia_bancaria="",
            huella_importacion=f"independiente-{indice}",
            estado="PENDIENTE",
        )
        for indice in range(2)
    ]

    propuestas = [
        PropuestaConciliacion(
            previstos=[previsto],
            bancarios=[bancario],
            puntuacion=puntuacion,
            motivos=["Coincidencia"],
        )
        for previsto, bancario, puntuacion in zip(
            previstos,
            bancarios,
            [120, 150],
        )
    ]

    seleccionadas = _seleccionar_propuestas_agrupadas(
        propuestas
    )

    assert len(seleccionadas) == 2
    assert seleccionadas == [
        propuestas[1],
        propuestas[0],
    ]



def test_proponer_grupo_acota_por_contraparte(
    inmueble,
    monkeypatch,
) -> None:
    """Evita generar grupos con transferencias de otras contrapartes."""

    previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    def transferencia(importe, nombre, referencia):
        return MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=importe,
            tipo_original="TRANSFERENCIA",
            descripcion_original=f"{nombre} alquiler",
            referencia_bancaria="",
            huella_importacion=referencia,
            estado="PENDIENTE",
        )

    primero = transferencia(
        60000, "Juan Pérez", "juan-600"
    )
    segundo = transferencia(
        40000, "Juan Pérez", "juan-400"
    )

    otros = [
        transferencia(
            40000,
            f"Inquilino distinto {indice}",
            f"otro-{indice}",
        )
        for indice in range(20)
    ]

    # Inspeccionamos las propuestas generadas antes de
    # ejecutar la selección combinatoria.
    propuestas_generadas = []

    def seleccionar_controlado(propuestas):
        propuestas_generadas.extend(propuestas)
        return propuestas

    monkeypatch.setattr(
        servicios_conciliacion,
        "_seleccionar_propuestas_agrupadas",
        seleccionar_controlado,
    )

    propuestas = buscar_propuestas_agrupadas(
        [primero, segundo, *otros],
        [previsto],
    )

    assert len(propuestas_generadas) == 1
    assert len(propuestas) == 1
    assert propuestas[0].bancarios == [
        primero,
        segundo,
    ]
    assert propuestas[0].previstos == [previsto]



def test_proponer_grupo_limita_ambiguedad_numerosa(
    inmueble,
    monkeypatch,
) -> None:
    """No envía una cantidad excesiva de alternativas al selector."""

    previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    def transferencia(importe, referencia):
        return MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=importe,
            tipo_original="TRANSFERENCIA",
            descripcion_original="Juan Pérez alquiler",
            referencia_bancaria="",
            huella_importacion=referencia,
            estado="PENDIENTE",
        )

    primero = transferencia(
        60000,
        "ambiguo-masivo-600",
    )

    alternativas = [
        transferencia(
            40000,
            f"ambiguo-masivo-{indice}",
        )
        for indice in range(20)
    ]

    def seleccionar_controlado(propuestas):
        assert len(propuestas) <= 8
        return []

    # Evita ejecutar la búsqueda exponencial durante
    # el propio test.
    monkeypatch.setattr(
        servicios_conciliacion,
        "_seleccionar_propuestas_agrupadas",
        seleccionar_controlado,
    )

    propuestas = buscar_propuestas_agrupadas(
        [primero, *alternativas],
        [previsto],
    )

    assert propuestas == []



def test_proponer_grupo_sin_contraparte_identificable(
    inmueble,
) -> None:
    """Permite un grupo exacto aunque el banco no informe del pagador."""

    previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    bancarios = [
        MovimientoBancario(
            fecha=date(2026, 10, 5 + indice),
            naturaleza="INGRESO",
            importe=importe,
            tipo_original="TRANSFERENCIA",
            descripcion_original="Ingreso recibido",
            referencia_bancaria="",
            huella_importacion=f"sin-nombre-{indice}",
            estado="PENDIENTE",
        )
        for indice, importe in enumerate(
            [60000, 40000]
        )
    ]

    propuestas = buscar_propuestas_agrupadas(
        bancarios,
        [previsto],
    )

    assert len(propuestas) == 1
    assert propuestas[0].previstos == [previsto]
    assert propuestas[0].bancarios == bancarios



def test_seleccionar_descarta_componente_con_cinco_alternativas(
    inmueble,
) -> None:
    """No selecciona propuestas de un conflicto excesivamente grande."""

    previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=10000,
    )

    propuestas = []

    for indice in range(5):
        bancario = MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=10000,
            tipo_original="TRANSFERENCIA",
            descripcion_original=f"Alternativa {indice}",
            referencia_bancaria="",
            huella_importacion=f"limite-{indice}",
            estado="PENDIENTE",
        )

        propuestas.append(
            PropuestaConciliacion(
                bancarios=[bancario],
                previstos=[previsto],
                puntuacion=200 - indice,
                motivos=["Coincidencia"],
            )
        )

    seleccionadas = _seleccionar_propuestas_agrupadas(
        propuestas
    )

    assert seleccionadas == []


def test_seleccionar_conserva_independientes_ante_limite(
    inmueble,
) -> None:
    """Descarta el conflicto grande, no las propuestas independientes."""

    previsto_ambiguo = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler ambiguo",
        importe_esperado=10000,
    )

    alternativas = []

    for indice in range(5):
        bancario = MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=10000,
            tipo_original="TRANSFERENCIA",
            descripcion_original=f"Alternativa {indice}",
            referencia_bancaria="",
            huella_importacion=f"conflicto-{indice}",
            estado="PENDIENTE",
        )

        alternativas.append(
            PropuestaConciliacion(
                bancarios=[bancario],
                previstos=[previsto_ambiguo],
                puntuacion=200 - indice,
                motivos=["Coincidencia"],
            )
        )

    previsto_independiente = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler independiente",
        importe_esperado=50000,
    )

    bancario_independiente = MovimientoBancario(
        fecha=date(2026, 10, 6),
        naturaleza="INGRESO",
        importe=50000,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Pago identificado",
        referencia_bancaria="",
        huella_importacion="independiente-limite",
        estado="PENDIENTE",
    )

    independiente = PropuestaConciliacion(
        bancarios=[bancario_independiente],
        previstos=[previsto_independiente],
        puntuacion=150,
        motivos=["Coincidencia"],
    )

    seleccionadas = _seleccionar_propuestas_agrupadas(
        [*alternativas, independiente]
    )

    assert len(seleccionadas) == 1
    assert seleccionadas[0] is independiente



def test_propuestas_integradas_prefieren_individual_mejor_identificada(
    inmueble,
) -> None:
    """Prefiere 1:1 cuando sus indicios son mejores que los del grupo."""

    previsto, individual, primero, segundo = (
        _escenario_propuestas_en_competencia(
            inmueble,
            descripcion_individual="Juan Pérez alquiler octubre",
            descripcion_grupo="Ingreso sin identificar",
        )
    )

    propuestas = buscar_propuestas_conciliacion(
        [individual, primero, segundo],
        [previsto],
    )

    assert len(propuestas) == 1
    assert propuestas[0].previstos == [previsto]
    assert propuestas[0].bancarios == [individual]

    assert previsto.estado == "PENDIENTE"
    assert individual.estado == "PENDIENTE"
    assert primero.estado == "PENDIENTE"
    assert segundo.estado == "PENDIENTE"



def test_propuestas_integradas_prefieren_grupo_mejor_identificado(
    inmueble,
) -> None:
    """Prefiere 1:2 cuando tiene mejores indicios que 1:1."""

    previsto, individual, primero, segundo = (
        _escenario_propuestas_en_competencia(
            inmueble,
            descripcion_individual="Ingreso sin identificar",
            descripcion_grupo="Juan Pérez alquiler octubre",
        )
    )

    propuestas = buscar_propuestas_conciliacion(
        [individual, primero, segundo],
        [previsto],
    )

    assert len(propuestas) == 1
    assert propuestas[0].previstos == [previsto]
    assert propuestas[0].bancarios == [
        primero,
        segundo,
    ]

    assert previsto.estado == "PENDIENTE"
    assert individual.estado == "PENDIENTE"
    assert primero.estado == "PENDIENTE"
    assert segundo.estado == "PENDIENTE"



def test_propuestas_integradas_conservan_independientes(
    inmueble,
) -> None:
    """Resuelve un conflicto sin perder otras propuestas válidas."""

    previsto, individual, primero, segundo = (
        _escenario_propuestas_en_competencia(
            inmueble,
            descripcion_individual="Juan Pérez alquiler octubre",
            descripcion_grupo="Ingreso sin identificar",
        )
    )

    otro_previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Seguro octubre",
        importe_esperado=25000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Aseguradora Central",
    )

    otro_bancario = MovimientoBancario(
        fecha=date(2026, 10, 6),
        naturaleza="GASTO",
        importe=25000,
        tipo_original="RECIBO",
        descripcion_original="Aseguradora Central",
        referencia_bancaria="",
        huella_importacion="integrada-independiente",
        estado="PENDIENTE",
    )

    propuestas = buscar_propuestas_conciliacion(
        [individual, primero, segundo, otro_bancario],
        [previsto, otro_previsto],
    )

    assert len(propuestas) == 2

    assert any(
        propuesta.previstos == [previsto]
        and propuesta.bancarios == [individual]
        for propuesta in propuestas
    )

    assert any(
        propuesta.previstos == [otro_previsto]
        and propuesta.bancarios == [otro_bancario]
        for propuesta in propuestas
    )

    assert all(
        primero not in propuesta.bancarios
        and segundo not in propuesta.bancarios
        for propuesta in propuestas
    )



def test_propuestas_integradas_seleccionan_mejor_combinacion_global(
    inmueble,
) -> None:
    """No descarta grupos antes de compararlos con propuestas 1:1."""

    alquiler = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="Juan Pérez",
    )

    reembolso = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="INGRESO",
        concepto="Reembolso de agua",
        importe_esperado=40000,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        contraparte="María López",
    )

    def transferencia(importe, descripcion, referencia):
        return MovimientoBancario(
            fecha=date(2026, 10, 5),
            naturaleza="INGRESO",
            importe=importe,
            tipo_original="TRANSFERENCIA",
            descripcion_original=descripcion,
            referencia_bancaria="",
            huella_importacion=referencia,
            estado="PENDIENTE",
        )

    bancario_600 = transferencia(
        60000,
        "Juan Pérez primer pago",
        "global-600",
    )

    bancario_400_a = transferencia(
        40000,
        "Juan Pérez María López PAGO ESPECIAL",
        "global-400-a",
    )

    bancario_400_b = transferencia(
        40000,
        "Juan Pérez segundo pago",
        "global-400-b",
    )

    aliases = [
        (
            "ALQUILER",
            inmueble.referencia,
            "PAGO ESPECIAL",
        ),
    ]

    propuestas = buscar_propuestas_conciliacion(
        [
            bancario_600,
            bancario_400_a,
            bancario_400_b,
        ],
        [alquiler, reembolso],
        aliases_configurados=aliases,
    )

    assert len(propuestas) == 2

    # El alquiler se cubre con los bancarios 600 y 400 B.
    assert any(
        propuesta.previstos == [alquiler]
        and propuesta.bancarios == [
            bancario_600,
            bancario_400_b,
        ]
        for propuesta in propuestas
    )

    # El bancario 400 A queda disponible para el reembolso.
    assert any(
        propuesta.previstos == [reembolso]
        and propuesta.bancarios == [bancario_400_a]
        for propuesta in propuestas
    )

    # No hay movimientos compartidos entre propuestas.
    bancarios_seleccionados = [
        bancario
        for propuesta in propuestas
        for bancario in propuesta.bancarios
    ]

    previstos_seleccionados = [
        previsto
        for propuesta in propuestas
        for previsto in propuesta.previstos
    ]

    assert len({
        id(bancario)
        for bancario in bancarios_seleccionados
    }) == len(bancarios_seleccionados)

    assert len({
        id(previsto)
        for previsto in previstos_seleccionados
    }) == len(previstos_seleccionados)

    assert alquiler.estado == "PENDIENTE"
    assert reembolso.estado == "PENDIENTE"
    assert all(
        bancario.estado == "PENDIENTE"
        for bancario in [
            bancario_600,
            bancario_400_a,
            bancario_400_b,
        ]
    )



def test_confirmar_propuesta_individual(
    session,
    inmueble,
) -> None:
    """Confirma una propuesta individual sin hacer commit."""

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )

    bancario = _bancario_para_confirmar(
        "confirmar-individual",
        100000,
    )

    session.add_all([previsto, bancario])
    session.flush()

    propuesta = PropuestaConciliacion(
        bancarios=[bancario],
        previstos=[previsto],
        puntuacion=150,
        motivos=["Importe y contraparte coincidentes"],
    )

    conciliaciones = confirmar_propuesta_conciliacion(
        propuesta
    )

    assert len(conciliaciones) == 1

    conciliacion = conciliaciones[0]

    assert conciliacion.movimiento_bancario is bancario
    assert conciliacion.movimiento_previsto is previsto
    assert conciliacion.importe_asociado == 100000

    assert bancario.estado == "CONCILIADO"
    assert previsto.estado == "CONCILIADO"
    assert previsto.metodo_conciliacion == "INDIVIDUAL"

    assert conciliacion.id is None

    session.add_all(conciliaciones)
    session.commit()

    assert conciliacion.id is not None



def test_confirmar_propuesta_un_previsto_dos_bancarios(
    session,
    inmueble,
) -> None:
    """Confirma una propuesta 1:2 con sus importes individuales."""

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )

    primero = _bancario_para_confirmar(
        "confirmar-1n-600",
        60000,
    )

    segundo = _bancario_para_confirmar(
        "confirmar-1n-400",
        40000,
    )

    session.add_all([previsto, primero, segundo])
    session.flush()

    propuesta = PropuestaConciliacion(
        bancarios=[primero, segundo],
        previstos=[previsto],
        puntuacion=150,
        motivos=["Suma exacta"],
    )

    conciliaciones = confirmar_propuesta_conciliacion(
        propuesta
    )

    assert len(conciliaciones) == 2

    assert [
        (
            conciliacion.movimiento_bancario,
            conciliacion.movimiento_previsto,
            conciliacion.importe_asociado,
        )
        for conciliacion in conciliaciones
    ] == [
        (primero, previsto, 60000),
        (segundo, previsto, 40000),
    ]

    assert previsto.estado == "CONCILIADO"
    assert primero.estado == "CONCILIADO"
    assert segundo.estado == "CONCILIADO"

    session.add_all(conciliaciones)
    session.commit()

    assert saldo_movimiento_previsto(previsto) == (
        100000,
        0,
    )



def test_confirmar_propuesta_dos_previstos_un_bancario(
    session,
    inmueble,
) -> None:
    """Confirma una propuesta 2:1 distribuyendo el ingreso."""

    alquiler = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        90000,
    )

    agua = _previsto_para_confirmar(
        inmueble,
        "Reembolso de agua",
        4500,
    )

    bancario = _bancario_para_confirmar(
        "confirmar-m1",
        94500,
    )

    session.add_all([alquiler, agua, bancario])
    session.flush()

    propuesta = PropuestaConciliacion(
        bancarios=[bancario],
        previstos=[alquiler, agua],
        puntuacion=150,
        motivos=["Suma exacta"],
    )

    conciliaciones = confirmar_propuesta_conciliacion(
        propuesta
    )

    assert len(conciliaciones) == 2

    assert [
        (
            conciliacion.movimiento_bancario,
            conciliacion.movimiento_previsto,
            conciliacion.importe_asociado,
        )
        for conciliacion in conciliaciones
    ] == [
        (bancario, alquiler, 90000),
        (bancario, agua, 4500),
    ]

    assert bancario.estado == "CONCILIADO"
    assert alquiler.estado == "CONCILIADO"
    assert agua.estado == "CONCILIADO"

    session.add_all(conciliaciones)
    session.commit()

    assert saldo_movimiento_bancario(bancario) == (
        94500,
        0,
    )



def test_confirmar_propuesta_con_previsto_parcial(
    session,
    inmueble,
) -> None:
    """Completa un previsto parcial sin duplicar su asociación anterior."""

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )

    anterior = _bancario_para_confirmar(
        "confirmar-parcial-anterior",
        60000,
    )

    primero = _bancario_para_confirmar(
        "confirmar-parcial-250",
        25000,
    )

    segundo = _bancario_para_confirmar(
        "confirmar-parcial-150",
        15000,
    )

    session.add_all([
        previsto,
        anterior,
        primero,
        segundo,
    ])
    session.flush()

    asociaciones_anteriores = confirmar_grupo_conciliacion([
        (anterior, previsto, 60000),
    ])

    session.add_all(asociaciones_anteriores)
    session.commit()

    assert previsto.estado == "PARCIAL"
    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )

    propuesta = PropuestaConciliacion(
        bancarios=[primero, segundo],
        previstos=[previsto],
        puntuacion=150,
        motivos=["Saldos pendientes coincidentes"],
    )

    conciliaciones = confirmar_propuesta_conciliacion(
        propuesta
    )

    assert len(conciliaciones) == 2

    assert [
        conciliacion.importe_asociado
        for conciliacion in conciliaciones
    ] == [
        25000,
        15000,
    ]

    assert previsto.estado == "CONCILIADO"
    assert anterior.estado == "CONCILIADO"
    assert primero.estado == "CONCILIADO"
    assert segundo.estado == "CONCILIADO"

    session.add_all(conciliaciones)
    session.commit()

    assert saldo_movimiento_previsto(previsto) == (
        100000,
        0,
    )

    assert len(previsto.conciliaciones) == 3



def test_confirmar_propuesta_rechaza_saldos_obsoletos(
    session,
    inmueble,
) -> None:
    """Rechaza una propuesta cuyos saldos cambiaron."""

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )

    bancario = _bancario_para_confirmar(
        "obsoleto-propuesto",
        100000,
    )

    anterior = _bancario_para_confirmar(
        "obsoleto-anterior",
        60000,
    )

    session.add_all([previsto, bancario, anterior])
    session.flush()

    propuesta = PropuestaConciliacion(
        bancarios=[bancario],
        previstos=[previsto],
        puntuacion=150,
        motivos=["Importes coincidentes"],
    )

    # Otra operación concilia parte del alquiler.
    conciliaciones = confirmar_grupo_conciliacion([
        (anterior, previsto, 60000),
    ])
    session.add_all(conciliaciones)
    session.commit()

    assert previsto.estado == "PARCIAL"

    with pytest.raises(
        ConciliacionError,
        match="saldos pendientes",
    ):
        confirmar_propuesta_conciliacion(propuesta)

    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )
    assert saldo_movimiento_bancario(bancario) == (
        0,
        100000,
    )
    assert previsto.estado == "PARCIAL"
    assert bancario.estado == "PENDIENTE"
    assert len(previsto.conciliaciones) == 1
    assert len(bancario.conciliaciones) == 0



def test_confirmar_propuesta_rechaza_movimiento_conciliado(
    session,
    inmueble,
) -> None:
    """No permite confirmar dos veces la misma propuesta."""

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )

    bancario = _bancario_para_confirmar(
        "repetido-individual",
        100000,
    )

    session.add_all([previsto, bancario])
    session.flush()

    propuesta = PropuestaConciliacion(
        bancarios=[bancario],
        previstos=[previsto],
        puntuacion=150,
        motivos=["Coincidencia exacta"],
    )

    conciliaciones = confirmar_propuesta_conciliacion(
        propuesta
    )
    session.add_all(conciliaciones)
    session.commit()

    with pytest.raises(ConciliacionError):
        confirmar_propuesta_conciliacion(propuesta)

    assert previsto.estado == "CONCILIADO"
    assert bancario.estado == "CONCILIADO"
    assert saldo_movimiento_previsto(previsto) == (
        100000,
        0,
    )
    assert saldo_movimiento_bancario(bancario) == (
        100000,
        0,
    )
    assert len(previsto.conciliaciones) == 1
    assert len(bancario.conciliaciones) == 1



def test_confirmar_propuesta_rechaza_naturalezas_distintas(
    session,
    inmueble,
) -> None:
    """Rechaza asociar un ingreso bancario con un gasto previsto."""

    previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza="GASTO",
        concepto="Recibo de comunidad",
        importe_esperado=25000,
    )

    bancario = _bancario_para_confirmar(
        "naturaleza-incompatible",
        25000,
    )

    session.add_all([previsto, bancario])
    session.flush()

    propuesta = PropuestaConciliacion(
        bancarios=[bancario],
        previstos=[previsto],
        puntuacion=150,
        motivos=["Importes coincidentes"],
    )

    with pytest.raises(
        ConciliacionError,
        match="misma naturaleza",
    ):
        confirmar_propuesta_conciliacion(propuesta)

    assert previsto.estado == "PENDIENTE"
    assert bancario.estado == "PENDIENTE"
    assert previsto.conciliaciones == []
    assert bancario.conciliaciones == []



def test_confirmar_propuesta_rechaza_grupo_m_n(
    session,
    inmueble,
) -> None:
    """Rechaza grupos m:n cuya distribución no está definida."""

    previstos = [
        _previsto_para_confirmar(
            inmueble,
            "Alquiler",
            60000,
        ),
        _previsto_para_confirmar(
            inmueble,
            "Reembolso de agua",
            40000,
        ),
    ]

    bancarios = [
        _bancario_para_confirmar(
            "mn-primero",
            70000,
        ),
        _bancario_para_confirmar(
            "mn-segundo",
            30000,
        ),
    ]

    session.add_all([*previstos, *bancarios])
    session.flush()

    propuesta = PropuestaConciliacion(
        bancarios=bancarios,
        previstos=previstos,
        puntuacion=150,
        motivos=["Suma exacta"],
    )

    with pytest.raises(
        ConciliacionError,
        match="m:n",
    ):
        confirmar_propuesta_conciliacion(propuesta)

    assert all(
        previsto.estado == "PENDIENTE"
        and previsto.conciliaciones == []
        for previsto in previstos
    )

    assert all(
        bancario.estado == "PENDIENTE"
        and bancario.conciliaciones == []
        for bancario in bancarios
    )



def test_propuesta_exacta_prevalece_sobre_diferencia(
    inmueble,
) -> None:
    """Prefiere la correspondencia exacta frente a una aproximada."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=92000,
        contraparte="ANA PEREZ",
        estado="PENDIENTE",
    )

    bancario_exacto = _movimiento_bancario_para_diferencias(
        92000,
        "TRANSFERENCIA ANA PEREZ",
        "prioridad-exacto",
    )

    bancario_diferente = _movimiento_bancario_para_diferencias(
        90000,
        "TRANSFERENCIA ANA PEREZ",
        "prioridad-diferente",
    )

    propuestas = buscar_propuestas_conciliacion(
        [bancario_diferente, bancario_exacto],
        [previsto],
    )

    assert len(propuestas) == 1

    assert propuestas[0].bancarios == [bancario_exacto]
    assert propuestas[0].previstos == [previsto]

    # El movimiento diferente queda libre.
    assert all(
        bancario_diferente not in propuesta.bancarios
        for propuesta in propuestas
    )



def test_no_proponer_diferencia_sin_identificar_contraparte(
    inmueble,
) -> None:
    """No propone diferencias basándose únicamente en la fecha."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=92000,
        contraparte="ANA PEREZ",
        estado="PENDIENTE",
    )

    bancario = _movimiento_bancario_para_diferencias(
        90000,
        "TRANSFERENCIA SIN IDENTIFICAR",
        "diferencia-sin-contraparte",
    )

    propuestas = buscar_propuestas_conciliacion(
        [bancario],
        [previsto],
    )

    assert propuestas == []



def test_no_proponer_diferencia_ambigua(
    inmueble,
) -> None:
    """No elige entre dos previstos plausibles para un bancario."""

    previsto_1 = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        naturaleza="INGRESO",
        concepto="Alquiler local A",
        importe_esperado=92000,
        contraparte="ANA PEREZ",
        estado="PENDIENTE",
    )

    previsto_2 = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        naturaleza="INGRESO",
        concepto="Alquiler local B",
        importe_esperado=93000,
        contraparte="ANA PEREZ",
        estado="PENDIENTE",
    )

    bancario = _movimiento_bancario_para_diferencias(
        90000,
        "INGRESO ANA PEREZ",
        "diferencia-ambigua",
    )

    propuestas = buscar_propuestas_conciliacion(
        [bancario],
        [previsto_1, previsto_2],
    )

    assert propuestas == []



@pytest.mark.parametrize(
    ("importe_bancario", "debe_proponer"),
    [
        (100000, True),  # Exacto.
        (99500, True),   # Diferencia del 0,5 %.
        (95000, True),   # Diferencia del 5 %.
        (94999, False),  # Supera el 5 %.
        (105000, True),  # Exceso del 5 %.
        (105001, False), # Supera el 5 %.
        (12500, False),  # Diferencia desproporcionada.
    ],
)
def test_limite_diferencia_propuesta_automatica(
    inmueble,
    importe_bancario,
    debe_proponer,
) -> None:
    """Sólo sugiere diferencias de hasta el 5 %."""

    previsto = MovimientoPrevisto(
        inmueble=inmueble,
        fecha_prevista_desde=date(2026, 10, 1),
        fecha_prevista_hasta=date(2026, 10, 10),
        naturaleza="INGRESO",
        concepto="Alquiler octubre",
        importe_esperado=100000,
        contraparte="ANA PEREZ",
        estado="PENDIENTE",
    )

    bancario = _movimiento_bancario_para_diferencias(
        importe_bancario,
        "TRANSFERENCIA ANA PEREZ",
        f"limite-diferencia-{importe_bancario}",
    )

    propuestas = buscar_propuestas_conciliacion(
        [bancario],
        [previsto],
    )

    if debe_proponer:
        assert len(propuestas) == 1
        assert propuestas[0].bancarios == [bancario]
        assert propuestas[0].previstos == [previsto]
    else:
        assert propuestas == []

    # El selector nunca modifica los movimientos.
    assert bancario.estado == "PENDIENTE"
    assert previsto.estado == "PENDIENTE"



def test_progresiva_conserva_saldo_disponible(
    session,
    inmueble,
) -> None:
    """Un pago parcial no cierra la factura."""

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler enero",
        100000,
    )
    bancario = _bancario_para_confirmar(
        "progresiva-600",
        60000,
    )

    session.add_all([previsto, bancario])
    session.flush()

    asociaciones = confirmar_grupo_conciliacion([
        (bancario, previsto, 60000),
    ])

    session.add_all(asociaciones)
    session.commit()

    assert bancario.estado == "CONCILIADO"
    assert previsto.estado == "PARCIAL"

    assert saldo_movimiento_bancario(bancario) == (60000, 0)
    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )



def test_cerrar_conciliacion_con_defecto(
    session,
    inmueble,
) -> None:
    """Acepta 995 € contra 1.000 €, conservando la diferencia."""

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler febrero",
        100000,
    )
    bancario = _bancario_para_confirmar(
        "diferencia-defecto",
        99500,
    )

    session.add_all([previsto, bancario])
    session.flush()

    asociaciones = confirmar_grupo_conciliacion(
        [(bancario, previsto, 99500)],
        cerrar_diferencia=True,
    )

    session.add_all(asociaciones)
    session.commit()

    assert len(asociaciones) == 1
    assert asociaciones[0].importe_asociado == 99500

    assert bancario.estado == "CONCILIADO"
    assert previsto.estado == "CONCILIADO"

    # Los saldos aritméticos permanecen intactos.
    assert saldo_movimiento_bancario(bancario) == (
        99500,
        0,
    )
    assert saldo_movimiento_previsto(previsto) == (
        99500,
        500,
    )

    assert bancario.importe == 99500
    assert previsto.importe_esperado == 100000

    # El cierre debe sobrevivir a una nueva carga
    # y al recálculo posterior de estados.
    session.expire_all()

    actualizar_estado_movimiento_previsto(previsto)
    actualizar_estado_movimiento_bancario(bancario)

    assert previsto.estado == "CONCILIADO"
    assert bancario.estado == "CONCILIADO"



def test_cerrar_conciliacion_con_exceso(
    session,
    inmueble,
) -> None:
    """Acepta 1.005 € contra 1.000 €, conservando el exceso."""

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler marzo",
        100000,
    )
    bancario = _bancario_para_confirmar(
        "diferencia-exceso",
        100500,
    )

    session.add_all([previsto, bancario])
    session.flush()

    asociaciones = confirmar_grupo_conciliacion(
        [(bancario, previsto, 100000)],
        cerrar_diferencia=True,
    )

    session.add_all(asociaciones)
    session.commit()

    assert len(asociaciones) == 1
    assert asociaciones[0].importe_asociado == 100000

    assert previsto.estado == "CONCILIADO"
    assert bancario.estado == "CONCILIADO"

    assert saldo_movimiento_previsto(previsto) == (
        100000,
        0,
    )
    assert saldo_movimiento_bancario(bancario) == (
        100000,
        500,
    )

    assert previsto.importe_esperado == 100000
    assert bancario.importe == 100500

    session.expire_all()

    actualizar_estado_movimiento_previsto(previsto)
    actualizar_estado_movimiento_bancario(bancario)

    assert previsto.estado == "CONCILIADO"
    assert bancario.estado == "CONCILIADO"



def test_cerrar_diferencia_tras_conciliacion_parcial(
    session,
    inmueble,
) -> None:
    """Permite cerrar una factura tras varios ingresos."""

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler abril",
        100000,
    )

    primero = _bancario_para_confirmar(
        "parcial-primero-600",
        60000,
    )
    segundo = _bancario_para_confirmar(
        "parcial-segundo-395",
        39500,
    )

    session.add_all([previsto, primero, segundo])
    session.flush()

    # Primera operación: se concilian 600 €,
    # dejando 400 € pendientes.
    primera = confirmar_grupo_conciliacion([
        (primero, previsto, 60000),
    ])

    session.add_all(primera)
    session.commit()

    assert primero.estado == "CONCILIADO"
    assert previsto.estado == "PARCIAL"
    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )

    # Segunda operación: llegan 395 €.
    # El usuario acepta cerrar los 5 € restantes.
    segunda = confirmar_grupo_conciliacion(
        [(segundo, previsto, 39500)],
        cerrar_diferencia=True,
    )

    session.add_all(segunda)
    session.commit()

    assert primero.estado == "CONCILIADO"
    assert segundo.estado == "CONCILIADO"
    assert previsto.estado == "CONCILIADO"

    # Deben conservarse ambas asociaciones.
    assert len(previsto.conciliaciones) == 2

    assert saldo_movimiento_previsto(previsto) == (
        99500,
        500,
    )

    session.expire_all()

    actualizar_estado_movimiento_previsto(previsto)

    assert previsto.estado == "CONCILIADO"



def test_deshacer_cierre_con_diferencia_conserva_asociaciones(
    session,
    inmueble,
) -> None:
    """Deshacer el último cierre conserva las asociaciones anteriores."""

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler mayo",
        100000,
    )

    primero = _bancario_para_confirmar(
        "deshacer-parcial-600",
        60000,
    )
    segundo = _bancario_para_confirmar(
        "deshacer-cierre-395",
        39500,
    )

    session.add_all([previsto, primero, segundo])
    session.flush()

    primera = confirmar_grupo_conciliacion([
        (primero, previsto, 60000),
    ])

    session.add_all(primera)
    session.commit()

    segunda = confirmar_grupo_conciliacion(
        [(segundo, previsto, 39500)],
        cerrar_diferencia=True,
    )

    session.add_all(segunda)
    session.commit()

    assert previsto.estado == "CONCILIADO"

    # Se deshace únicamente la segunda asociación.
    deshacer_asociacion_bancaria(segunda[0])
    session.commit()

    assert previsto.estado == "PARCIAL"
    assert primero.estado == "CONCILIADO"
    assert segundo.estado == "PENDIENTE"

    assert saldo_movimiento_previsto(previsto) == (
        60000,
        40000,
    )

    assert saldo_movimiento_bancario(segundo) == (
        0,
        39500,
    )

    # Sólo debe permanecer la asociación de 600 €.
    asociaciones = session.scalars(
        select(Conciliacion)
    ).all()

    assert len(asociaciones) == 1

    assert asociaciones[0].movimiento_bancario_id == primero.id
    assert asociaciones[0].movimiento_previsto_id == previsto.id
    assert asociaciones[0].importe_asociado == 60000



def test_deshacer_asociacion_anterior_conserva_cierre_posterior(
    session,
    inmueble,
) -> None:
    """Eliminar una asociación anterior no elimina el cierre posterior."""

    previsto = _previsto_para_confirmar(
        inmueble, "Alquiler junio", 100000
    )
    primero = _bancario_para_confirmar(
        "cierre-anterior-600", 60000
    )
    segundo = _bancario_para_confirmar(
        "cierre-posterior-395", 39500
    )

    session.add_all([previsto, primero, segundo])
    session.flush()

    primera = confirmar_grupo_conciliacion([
        (primero, previsto, 60000),
    ])
    session.add_all(primera)
    session.commit()

    segunda = confirmar_grupo_conciliacion(
        [(segundo, previsto, 39500)],
        cerrar_diferencia=True,
    )
    session.add_all(segunda)
    session.commit()

    assert segunda[0].cierra_previsto is True
    assert previsto.estado == "CONCILIADO"

    # Se retira la primera asociación, no la que cerró
    # expresamente el saldo restante.
    deshacer_asociacion_bancaria(primera[0])
    session.commit()
    session.expire_all()

    assert previsto.estado == "CONCILIADO"
    assert segundo.estado == "CONCILIADO"
    assert primero.estado == "PENDIENTE"

    assert saldo_movimiento_previsto(previsto) == (
        39500, 60500
    )

    assert len(previsto.conciliaciones) == 1
    assert previsto.conciliaciones[0].cierra_previsto is True



def test_cierre_diferencia_exige_agotar_lado_menor(
    session,
    inmueble,
) -> None:
    """No permite cerrar importes elegidos arbitrariamente."""

    previsto = _previsto_para_confirmar(
        inmueble, "Alquiler julio", 100000
    )
    bancario = _bancario_para_confirmar(
        "cierre-arbitrario-600", 60000
    )

    session.add_all([previsto, bancario])
    session.flush()

    with pytest.raises(
        ConciliacionError,
        match="un único movimiento con saldo sin asociar",
    ):
        confirmar_grupo_conciliacion(
            [(bancario, previsto, 10000)],
            cerrar_diferencia=True,
        )

    assert previsto.estado == "PENDIENTE"
    assert bancario.estado == "PENDIENTE"
    assert previsto.conciliaciones == []
    assert bancario.conciliaciones == []

    assert saldo_movimiento_previsto(previsto) == (
        0, 100000
    )
    assert saldo_movimiento_bancario(bancario) == (
        0, 60000
    )



def test_confirmar_grupo_invalido_no_modifica_movimientos(
    session,
    inmueble,
) -> None:
    """El grupo completo se valida antes de crear asociaciones."""

    previsto = _previsto_para_confirmar(
        inmueble, "Alquiler agosto", 100000
    )
    primero = _bancario_para_confirmar(
        "grupo-atomico-600", 60000
    )
    segundo = _bancario_para_confirmar(
        "grupo-atomico-500", 50000
    )

    session.add_all([previsto, primero, segundo])
    session.flush()

    # Aunque cada pareja sea individualmente válida,
    # el conjunto intenta asociar 1.100 € a una factura de 1.000 €.
    with pytest.raises(
        ConciliacionError,
        match="supera el saldo disponible",
    ):
        confirmar_grupo_conciliacion([
            (primero, previsto, 60000),
            (segundo, previsto, 50000),
        ])

    assert previsto.estado == "PENDIENTE"
    assert primero.estado == "PENDIENTE"
    assert segundo.estado == "PENDIENTE"

    assert previsto.conciliaciones == []
    assert primero.conciliaciones == []
    assert segundo.conciliaciones == []

    assert session.scalars(
        select(Conciliacion)
    ).all() == []


@pytest.mark.parametrize(
    "cardinalidad",
    ["uno_a_varios", "varios_a_uno"],
)
def test_conciliacion_agrupada_parcial_con_diferencia(
    session,
    inmueble,
    cardinalidad,
) -> None:
    """Una diferencia puede mantenerse disponible para otro día."""

    if cardinalidad == "uno_a_varios":
        previsto = _previsto_para_confirmar(
            inmueble, "Alquiler junio", 120000
        )
        primero = _bancario_para_confirmar(
            "agrupada-parcial-1n-1", 60000
        )
        segundo = _bancario_para_confirmar(
            "agrupada-parcial-1n-2", 59962
        )

        movimientos = [previsto, primero, segundo]
        asociaciones = [
            (primero, previsto, 60000),
            (segundo, previsto, 59962),
        ]

        movimiento_parcial = previsto
        movimientos_conciliados = [primero, segundo]

    else:
        primero = _previsto_para_confirmar(
            inmueble, "Alquiler junio", 100000
        )
        segundo = _previsto_para_confirmar(
            inmueble, "Recibo agua", 20000
        )
        bancario = _bancario_para_confirmar(
            "agrupada-parcial-n1", 119962
        )

        movimientos = [primero, segundo, bancario]
        asociaciones = [
            (bancario, primero, 100000),
            (bancario, segundo, 19962),
        ]

        movimiento_parcial = segundo
        movimientos_conciliados = [primero, bancario]

    session.add_all(movimientos)
    session.flush()

    conciliaciones = confirmar_grupo_conciliacion(
        asociaciones,
        cerrar_diferencia=False,
    )

    session.add_all(conciliaciones)
    session.commit()

    assert len(conciliaciones) == 2
    assert movimiento_parcial.estado == "PARCIAL"

    for movimiento in movimientos_conciliados:
        assert movimiento.estado == "CONCILIADO"

    assert sum(
        conciliacion.importe_asociado
        for conciliacion in conciliaciones
    ) == 119962

    assert all(
        not conciliacion.cierra_bancario
        and not conciliacion.cierra_previsto
        for conciliacion in conciliaciones
    )

    if cardinalidad == "uno_a_varios":
        assert saldo_movimiento_previsto(
            movimiento_parcial
        ) == (119962, 38)
    else:
        assert saldo_movimiento_previsto(
            movimiento_parcial
        ) == (19962, 38)



@pytest.mark.parametrize(
    ("cardinalidad", "importe_bancario", "cierre_esperado"),
    [
        ("uno_a_varios", 119962, "previsto"),
        ("uno_a_varios", 120038, "bancario"),
        ("varios_a_uno", 119962, "previsto"),
        ("varios_a_uno", 120038, "bancario"),
    ],
)
def test_cierre_diferencia_agrupada(
    session,
    inmueble,
    cardinalidad,
    importe_bancario,
    cierre_esperado,
) -> None:
    """Cierra una diferencia agrupada sin alterar importes reales."""

    if cardinalidad == "uno_a_varios":
        previsto = _previsto_para_confirmar(
            inmueble, "Alquiler agrupado", 120000
        )

        primero = _bancario_para_confirmar(
            f"agrupada-1n-{importe_bancario}-1",
            60000,
        )
        segundo = _bancario_para_confirmar(
            f"agrupada-1n-{importe_bancario}-2",
            importe_bancario - 60000,
        )

        movimientos = [previsto, primero, segundo]

        asociaciones = [
            (primero, previsto, 60000),
            (
                segundo,
                previsto,
                min(60000, importe_bancario - 60000),
            ),
        ]

        movimiento_con_cierre = (
            previsto
            if cierre_esperado == "previsto"
            else segundo
        )

    else:
        primero = _previsto_para_confirmar(
            inmueble, "Alquiler agrupado", 100000
        )
        segundo = _previsto_para_confirmar(
            inmueble, "Agua agrupada", 20000
        )

        contrato = _contrato_para_cierre_agrupado(inmueble)
        primero.contrato = contrato
        segundo.contrato = contrato

        bancario = _bancario_para_confirmar(
            f"agrupada-n1-{importe_bancario}",
            importe_bancario,
        )

        movimientos = [primero, segundo, bancario]
        session.add(contrato)

        asociaciones = [
            (bancario, primero, 100000),
            (
                bancario,
                segundo,
                min(20000, importe_bancario - 100000),
            ),
        ]

        movimiento_con_cierre = (
            segundo
            if cierre_esperado == "previsto"
            else bancario
        )

    session.add_all(movimientos)
    session.flush()

    conciliaciones = confirmar_grupo_conciliacion(
        asociaciones,
        cerrar_diferencia=True,
    )

    session.add_all(conciliaciones)
    session.commit()

    assert len(conciliaciones) == 2

    assert sum(
        conciliacion.importe_asociado
        for conciliacion in conciliaciones
    ) == min(120000, importe_bancario)

    assert all(
        movimiento.estado == "CONCILIADO"
        for movimiento in movimientos
    )

    # El cierre sólo se registra donde realmente
    # existe saldo aritmético sin asociar.
    cierres_previstos = [
        conciliacion
        for conciliacion in conciliaciones
        if conciliacion.cierra_previsto
    ]

    cierres_bancarios = [
        conciliacion
        for conciliacion in conciliaciones
        if conciliacion.cierra_bancario
    ]

    if cierre_esperado == "previsto":
        assert len(cierres_previstos) == 1
        assert cierres_bancarios == []
    else:
        assert len(cierres_bancarios) == 1
        assert cierres_previstos == []

    # La decisión de cierre debe seguir vigente
    # al recuperar y recalcular los estados.
    session.expire_all()

    if isinstance(movimiento_con_cierre, MovimientoPrevisto):
        actualizar_estado_movimiento_previsto(
            movimiento_con_cierre
        )
    else:
        actualizar_estado_movimiento_bancario(
            movimiento_con_cierre
        )

    assert movimiento_con_cierre.estado == "CONCILIADO"


def test_cierre_agrupado_no_asocia_dinero_inexistente(
    session,
    inmueble,
) -> None:
    """Aceptar una diferencia no permite asociar más de lo ingresado."""

    alquiler = _previsto_para_confirmar(
        inmueble, "Alquiler julio", 100000
    )
    agua = _previsto_para_confirmar(
        inmueble, "Agua julio", 20000
    )
    bancario = _bancario_para_confirmar(
        "agrupado-supera-banco", 119962
    )

    session.add_all([alquiler, agua, bancario])
    session.flush()

    with pytest.raises(ConciliacionError):
        confirmar_grupo_conciliacion(
            [
                (bancario, alquiler, 100000),
                (bancario, agua, 20000),
            ],
            cerrar_diferencia=True,
        )

    assert alquiler.estado == "PENDIENTE"
    assert agua.estado == "PENDIENTE"
    assert bancario.estado == "PENDIENTE"

    assert alquiler.conciliaciones == []
    assert agua.conciliaciones == []
    assert bancario.conciliaciones == []



def test_distribucion_cronologica_varios_previstos_un_bancario(
    session,
    inmueble,
) -> None:
    """Los cobros se aplican primero al previsto más antiguo."""

    antiguo = _previsto_para_confirmar(
        inmueble, "Alquiler septiembre", 100000
    )
    reciente = _previsto_para_confirmar(
        inmueble, "Agua octubre", 20000
    )

    antiguo.fecha_prevista_desde = date(2026, 9, 1)
    reciente.fecha_prevista_desde = date(2026, 10, 1)

    bancario = _bancario_para_confirmar(
        "distribucion-cronologica-n1", 119962
    )

    session.add_all([antiguo, reciente, bancario])
    session.flush()

    # Se entregan en orden inverso deliberadamente.
    asociaciones = preparar_asociaciones_cronologicas(
        [bancario],
        [reciente, antiguo],
    )

    assert asociaciones == [
        (bancario, antiguo, 100000),
        (bancario, reciente, 19962),
    ]

    # Preparar no confirma nada.
    assert antiguo.estado == "PENDIENTE"
    assert reciente.estado == "PENDIENTE"
    assert bancario.estado == "PENDIENTE"
    assert antiguo.conciliaciones == []
    assert reciente.conciliaciones == []



def test_distribucion_cronologica_un_previsto_varios_bancarios(
    session,
    inmueble,
) -> None:
    """Los ingresos se aplican por fecha y no por orden de selección."""

    previsto = _previsto_para_confirmar(
        inmueble, "Alquiler octubre", 120000
    )

    antiguo = _bancario_para_confirmar(
        "distribucion-cronologica-1n-antiguo",
        60000,
    )
    reciente = _bancario_para_confirmar(
        "distribucion-cronologica-1n-reciente",
        59962,
    )

    antiguo.fecha = date(2026, 10, 3)
    reciente.fecha = date(2026, 10, 9)

    session.add_all([previsto, antiguo, reciente])
    session.flush()

    asociaciones = preparar_asociaciones_cronologicas(
        [reciente, antiguo],
        [previsto],
    )

    assert asociaciones == [
        (antiguo, previsto, 60000),
        (reciente, previsto, 59962),
    ]

    assert sum(
        importe for _, _, importe in asociaciones
    ) == 119962



def test_distribucion_cronologica_desempata_por_id(
    session,
    inmueble,
) -> None:
    """La distribución es reproducible aunque coincidan las fechas."""

    primero = _previsto_para_confirmar(
        inmueble, "Recibo A", 10000
    )
    segundo = _previsto_para_confirmar(
        inmueble, "Recibo B", 10000
    )

    primero.fecha_prevista_desde = date(2026, 10, 1)
    segundo.fecha_prevista_desde = date(2026, 10, 1)

    bancario = _bancario_para_confirmar(
        "distribucion-misma-fecha", 19962
    )

    session.add_all([primero, segundo, bancario])
    session.flush()

    assert primero.id < segundo.id

    asociaciones = preparar_asociaciones_cronologicas(
        [bancario],
        [segundo, primero],
    )

    assert asociaciones == [
        (bancario, primero, 10000),
        (bancario, segundo, 9962),
    ]


def test_distribucion_cronologica_respeta_saldos_parciales(
    session,
    inmueble,
) -> None:
    """Utiliza únicamente el saldo todavía disponible."""

    previsto = _previsto_para_confirmar(
        inmueble, "Alquiler noviembre", 100000
    )

    anterior = _bancario_para_confirmar(
        "distribucion-pago-anterior", 60000
    )
    nuevo = _bancario_para_confirmar(
        "distribucion-pago-nuevo", 39500
    )

    session.add_all([previsto, anterior, nuevo])
    session.flush()

    primera = confirmar_grupo_conciliacion([
        (anterior, previsto, 60000),
    ])

    session.add_all(primera)
    session.commit()

    assert previsto.estado == "PARCIAL"
    assert saldo_movimiento_previsto(previsto) == (
        60000, 40000
    )

    asociaciones = preparar_asociaciones_cronologicas(
        [nuevo],
        [previsto],
    )

    assert asociaciones == [
        (nuevo, previsto, 39500),
    ]

    # Los 600 € ya conciliados siguen intactos.
    assert saldo_movimiento_previsto(previsto) == (
        60000, 40000
    )


def test_distribucion_rechaza_movimientos_sin_asociacion(
    session,
    inmueble,
) -> None:
    """No confirma una selección que deja un previsto sin aplicar."""

    enero = _previsto_para_confirmar(
        inmueble, "Alquiler enero", 100000
    )
    febrero = _previsto_para_confirmar(
        inmueble, "Alquiler febrero", 20000
    )

    enero.fecha_prevista_desde = date(2026, 1, 1)
    febrero.fecha_prevista_desde = date(2026, 2, 1)

    ingreso = _bancario_para_confirmar(
        "ingreso-insuficiente-seleccion", 60000
    )

    session.add_all([enero, febrero, ingreso])
    session.flush()

    # Los 600 € sólo alcanzan parcialmente enero.
    # Febrero no puede considerarse revisado.
    with pytest.raises(
        ConciliacionError,
        match="sin asociación",
    ):
        preparar_asociaciones_cronologicas(
            [ingreso],
            [febrero, enero],
        )

    assert enero.estado == "PENDIENTE"
    assert febrero.estado == "PENDIENTE"
    assert ingreso.estado == "PENDIENTE"

    assert enero.conciliaciones == []
    assert febrero.conciliaciones == []
    assert ingreso.conciliaciones == []


def test_cierre_agrupado_respeta_orden_y_se_puede_deshacer(
    session,
    inmueble,
) -> None:
    """La diferencia queda en el previsto más reciente y es reversible."""

    antiguo = _previsto_para_confirmar(
        inmueble, "Alquiler septiembre", 100000
    )
    reciente = _previsto_para_confirmar(
        inmueble, "Agua octubre", 20000
    )

    antiguo.fecha_prevista_desde = date(2026, 9, 1)
    reciente.fecha_prevista_desde = date(2026, 10, 1)

    contrato = _contrato_para_cierre_agrupado(inmueble)
    antiguo.contrato = contrato
    reciente.contrato = contrato

    ingreso = _bancario_para_confirmar(
        "cierre-cronologico-reversible", 119962
    )

    session.add(contrato)
    session.add_all([antiguo, reciente, ingreso])
    session.flush()

    # La selección llega en orden inverso.
    asociaciones_preparadas = preparar_asociaciones_cronologicas(
        [ingreso],
        [reciente, antiguo],
    )

    assert asociaciones_preparadas == [
        (ingreso, antiguo, 100000),
        (ingreso, reciente, 19962),
    ]

    conciliaciones = confirmar_grupo_conciliacion(
        asociaciones_preparadas,
        cerrar_diferencia=True,
    )

    session.add_all(conciliaciones)
    session.commit()

    primera, segunda = conciliaciones

    assert primera.cierra_previsto is False
    assert segunda.cierra_previsto is True
    assert primera.cierra_bancario is False
    assert segunda.cierra_bancario is False

    assert antiguo.estado == "CONCILIADO"
    assert reciente.estado == "CONCILIADO"
    assert ingreso.estado == "CONCILIADO"

    assert saldo_movimiento_previsto(reciente) == (
        19962, 38
    )

    # Deshacer la asociación que cerró los 38 céntimos.
    deshacer_asociacion_bancaria(segunda)
    session.commit()
    session.expire_all()

    assert antiguo.estado == "CONCILIADO"
    assert reciente.estado == "PENDIENTE"
    assert ingreso.estado == "PARCIAL"

    assert saldo_movimiento_previsto(reciente) == (
        0, 20000
    )
    assert saldo_movimiento_bancario(ingreso) == (
        100000, 19962
    )

    asociaciones_restantes = session.scalars(
        select(Conciliacion)
    ).all()

    assert len(asociaciones_restantes) == 1
    assert asociaciones_restantes[0].id == primera.id
    assert asociaciones_restantes[0].cierra_previsto is False


@pytest.mark.parametrize(
    "importe_bancario",
    [119962, 120038],
)
def test_cierre_diferencia_agrupada_rechaza_contratos_distintos(
    session,
    inmueble,
    importe_bancario,
) -> None:
    """No atribuye diferencias entre contratos diferentes."""

    contrato_a = _contrato_para_cierre_agrupado(inmueble)
    contrato_b = _contrato_para_cierre_agrupado(inmueble)

    alquiler = _previsto_para_confirmar(
        inmueble, "Alquiler contrato A", 100000
    )
    agua = _previsto_para_confirmar(
        inmueble, "Agua contrato B", 20000
    )

    alquiler.contrato = contrato_a
    agua.contrato = contrato_b

    alquiler.fecha_prevista_desde = date(2026, 9, 1)
    agua.fecha_prevista_desde = date(2026, 10, 1)

    bancario = _bancario_para_confirmar(
        f"contratos-distintos-{importe_bancario}",
        importe_bancario,
    )

    session.add_all([
        contrato_a,
        contrato_b,
        alquiler,
        agua,
        bancario,
    ])
    session.flush()

    asociaciones = preparar_asociaciones_cronologicas(
        [bancario],
        [alquiler, agua],
    )

    assert len(asociaciones) == 2

    with pytest.raises(
        ConciliacionError,
        match="contratos distintos",
    ):
        confirmar_grupo_conciliacion(
            asociaciones,
            cerrar_diferencia=True,
        )

    # El rechazo no debe modificar ningún movimiento.
    assert alquiler.estado == "PENDIENTE"
    assert agua.estado == "PENDIENTE"
    assert bancario.estado == "PENDIENTE"

    assert alquiler.conciliaciones == []
    assert agua.conciliaciones == []
    assert bancario.conciliaciones == []


def test_cierre_diferencia_agrupada_permite_mismo_contrato(
    session,
    inmueble,
) -> None:
    """Permite cerrar la diferencia si hay un contrato inequívoco."""

    contrato = _contrato_para_cierre_agrupado(inmueble)

    alquiler = _previsto_para_confirmar(
        inmueble, "Alquiler", 167214
    )
    agua = _previsto_para_confirmar(
        inmueble, "Reembolso. Agua", 2045
    )

    alquiler.contrato = contrato
    agua.contrato = contrato

    alquiler.fecha_prevista_desde = date(2026, 9, 1)
    agua.fecha_prevista_desde = date(2026, 10, 1)

    bancario = _bancario_para_confirmar(
        "mismo-contrato-169290",
        169290,
    )

    session.add_all([
        contrato,
        alquiler,
        agua,
        bancario,
    ])
    session.flush()

    asociaciones = preparar_asociaciones_cronologicas(
        [bancario],
        [agua, alquiler],
    )

    assert asociaciones == [
        (bancario, alquiler, 167214),
        (bancario, agua, 2045),
    ]

    conciliaciones = confirmar_grupo_conciliacion(
        asociaciones,
        cerrar_diferencia=True,
    )

    session.add_all(conciliaciones)
    session.commit()

    assert alquiler.estado == "CONCILIADO"
    assert agua.estado == "CONCILIADO"
    assert bancario.estado == "CONCILIADO"

    assert sum(
        c.importe_asociado for c in conciliaciones
    ) == 169259

    assert sum(
        c.cierra_bancario for c in conciliaciones
    ) == 1

    assert not any(
        c.cierra_previsto for c in conciliaciones
    )


def test_conciliacion_agrupada_parcial_permite_contratos_distintos(
    session,
    inmueble,
) -> None:
    """La imputación explícita no supone aceptar una diferencia."""

    contrato_a = _contrato_para_cierre_agrupado(inmueble)
    contrato_b = _contrato_para_cierre_agrupado(inmueble)

    primero = _previsto_para_confirmar(
        inmueble, "Previsto contrato A", 100000
    )
    segundo = _previsto_para_confirmar(
        inmueble, "Previsto contrato B", 20000
    )

    primero.contrato = contrato_a
    segundo.contrato = contrato_b

    primero.fecha_prevista_desde = date(2026, 9, 1)
    segundo.fecha_prevista_desde = date(2026, 10, 1)

    bancario = _bancario_para_confirmar(
        "parcial-distintos-119962", 119962
    )

    session.add_all([
        contrato_a,
        contrato_b,
        primero,
        segundo,
        bancario,
    ])
    session.flush()

    asociaciones = preparar_asociaciones_cronologicas(
        [bancario],
        [primero, segundo],
    )

    conciliaciones = confirmar_grupo_conciliacion(
        asociaciones,
        cerrar_diferencia=False,
    )

    session.add_all(conciliaciones)
    session.commit()

    assert primero.estado == "CONCILIADO"
    assert segundo.estado == "PARCIAL"
    assert bancario.estado == "CONCILIADO"

    assert saldo_movimiento_previsto(segundo) == (
        19962, 38
    )

    assert not any(
        c.cierra_previsto or c.cierra_bancario
        for c in conciliaciones
    )


@pytest.mark.parametrize(
    ("contratos_asignados", "importe_bancario"),
    [
        ("uno_identificado", 119962),
        ("uno_identificado", 120038),
    ],
)
def test_cierre_diferencia_agrupada_exige_contrato_identificado(
    session,
    inmueble,
    contratos_asignados,
    importe_bancario,
) -> None:
    """No cierra diferencias con contratos desconocidos."""

    contrato = _contrato_para_cierre_agrupado(inmueble)

    alquiler = _previsto_para_confirmar(
        inmueble, "Alquiler", 100000
    )
    agua = _previsto_para_confirmar(
        inmueble, "Agua", 20000
    )

    if contratos_asignados == "uno_identificado":
        alquiler.contrato = contrato

    alquiler.fecha_prevista_desde = date(2026, 9, 1)
    agua.fecha_prevista_desde = date(2026, 10, 1)

    bancario = _bancario_para_confirmar(
        f"contrato-desconocido-"
        f"{contratos_asignados}-{importe_bancario}",
        importe_bancario,
    )

    session.add_all([
        contrato,
        alquiler,
        agua,
        bancario,
    ])
    session.flush()

    asociaciones = preparar_asociaciones_cronologicas(
        [bancario],
        [agua, alquiler],
    )

    assert len(asociaciones) == 2

    with pytest.raises(
        ConciliacionError,
        match="contrato",
    ):
        confirmar_grupo_conciliacion(
            asociaciones,
            cerrar_diferencia=True,
        )

    # El rechazo no modifica movimientos ni crea relaciones.
    assert alquiler.estado == "PENDIENTE"
    assert agua.estado == "PENDIENTE"
    assert bancario.estado == "PENDIENTE"

    assert alquiler.conciliaciones == []
    assert agua.conciliaciones == []
    assert bancario.conciliaciones == []


@pytest.mark.parametrize(
    "importe_bancario",
    [119962, 120038],
)
def test_cierre_diferencia_agrupada_sin_contrato_mismo_inmueble(
    session,
    inmueble,
    importe_bancario,
) -> None:
    """Permite cerrar diferencias sin contrato en un mismo inmueble."""

    alquiler = _previsto_para_confirmar(
        inmueble, "Alquiler", 100000
    )
    agua = _previsto_para_confirmar(
        inmueble, "Agua", 20000
    )

    # Ninguno de los previstos tiene contrato.
    assert alquiler.contrato_id is None
    assert agua.contrato_id is None

    alquiler.fecha_prevista_desde = date(2026, 9, 1)
    agua.fecha_prevista_desde = date(2026, 10, 1)

    bancario = _bancario_para_confirmar(
        f"sin-contrato-mismo-inmueble-{importe_bancario}",
        importe_bancario,
    )

    session.add_all([alquiler, agua, bancario])
    session.flush()

    asociaciones_preparadas = preparar_asociaciones_cronologicas(
        [bancario],
        [agua, alquiler],
    )

    assert len(asociaciones_preparadas) == 2

    asociaciones = confirmar_grupo_conciliacion(
        asociaciones_preparadas,
        cerrar_diferencia=True,
    )

    assert len(asociaciones) == 2

    assert sum(
        asociacion.importe_asociado
        for asociacion in asociaciones
    ) == min(120000, importe_bancario)

    assert sum(
        bool(
            asociacion.cierra_bancario
            or asociacion.cierra_previsto
        )
        for asociacion in asociaciones
    ) == 1

    assert alquiler.estado == "CONCILIADO"
    assert agua.estado == "CONCILIADO"
    assert bancario.estado == "CONCILIADO"


def test_conciliacion_parcial_agrupada_permite_contrato_desconocido(
    session,
    inmueble,
) -> None:
    """La conciliación progresiva no exige cerrar deuda."""

    contrato = _contrato_para_cierre_agrupado(inmueble)

    alquiler = _previsto_para_confirmar(
        inmueble, "Alquiler", 100000
    )
    agua = _previsto_para_confirmar(
        inmueble, "Agua", 20000
    )

    alquiler.contrato = contrato
    # El segundo previsto todavía no tiene contrato.
    assert agua.contrato is None

    alquiler.fecha_prevista_desde = date(2026, 9, 1)
    agua.fecha_prevista_desde = date(2026, 10, 1)

    bancario = _bancario_para_confirmar(
        "parcial-contrato-desconocido", 119962
    )

    session.add_all([
        contrato,
        alquiler,
        agua,
        bancario,
    ])
    session.flush()

    asociaciones = preparar_asociaciones_cronologicas(
        [bancario],
        [alquiler, agua],
    )

    conciliaciones = confirmar_grupo_conciliacion(
        asociaciones,
        cerrar_diferencia=False,
    )

    session.add_all(conciliaciones)
    session.commit()

    assert alquiler.estado == "CONCILIADO"
    assert agua.estado == "PARCIAL"
    assert bancario.estado == "CONCILIADO"

    assert saldo_movimiento_previsto(agua) == (
        19962, 38
    )

    assert not any(
        c.cierra_previsto or c.cierra_bancario
        for c in conciliaciones
    )


@pytest.mark.parametrize(
    (
        "importe_bancario",
        "naturaleza_bancario",
        "fecha_bancaria",
        "descripcion",
        "tipo_esperado",
        "motivos_esperados",
    ),
    [
        # Importe exacto: no exige identificar contraparte.
        (
            100000,
            "INGRESO",
            date(2026, 10, 5),
            "TRANSFERENCIA DESCONOCIDA",
            "EXACTA",
            [],
        ),
        # Diferencia del 3 %, contraparte reconocida.
        (
            97000,
            "INGRESO",
            date(2026, 10, 5),
            "PAGO JUAN PEREZ",
            "DIFERENCIA",
            [],
        ),
        # Diferencia superior al 5 %.
        (
            94000,
            "INGRESO",
            date(2026, 10, 5),
            "PAGO JUAN PEREZ",
            "DESCARTADA",
            ["IMPORTE"],
        ),
        # Naturaleza incompatible.
        (
            97000,
            "GASTO",
            date(2026, 10, 5),
            "PAGO JUAN PEREZ",
            "DESCARTADA",
            ["NATURALEZA"],
        ),
        # Más de siete días antes de la fecha prevista.
        (
            97000,
            "INGRESO",
            date(2026, 9, 20),
            "PAGO JUAN PEREZ",
            "DESCARTADA",
            ["FECHA"],
        ),
        # Diferencia pequeña, pero contraparte desconocida.
        (
            97000,
            "INGRESO",
            date(2026, 10, 5),
            "TRANSFERENCIA DESCONOCIDA",
            "DESCARTADA",
            ["CONTRAPARTE"],
        ),
    ],
)
def test_diagnosticar_emparejamiento_examina_filtros(
    inmueble,
    importe_bancario,
    naturaleza_bancario,
    fecha_bancaria,
    descripcion,
    tipo_esperado,
    motivos_esperados,
) -> None:
    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )
    previsto.fecha_prevista_desde = date(2026, 10, 1)
    previsto.contraparte = "Juan Pérez"

    bancario = _bancario_para_confirmar(
        "debug-filtros",
        importe_bancario,
    )
    bancario.naturaleza = naturaleza_bancario
    bancario.fecha = fecha_bancaria
    bancario.descripcion_original = descripcion

    diagnostico = (
        servicios_conciliacion.diagnosticar_emparejamiento(
            bancario,
            previsto,
            aliases_configurados=[],
        )
    )

    assert diagnostico.tipo == tipo_esperado
    assert diagnostico.motivos_descarte == motivos_esperados

    assert diagnostico.importe_compatible is (
        "IMPORTE" not in motivos_esperados
    )
    assert diagnostico.naturaleza_compatible is (
        "NATURALEZA" not in motivos_esperados
    )
    assert diagnostico.fecha_compatible is (
        "FECHA" not in motivos_esperados
    )

    # La coincidencia exacta no exige contraparte,
    # pero el diagnóstico igualmente informa sobre ella.
    assert diagnostico.contraparte_identificada is (
        "JUAN PEREZ" in descripcion
    )


@pytest.mark.parametrize(
    (
        "aliases",
        "descripcion",
        "aplicables",
        "coincidentes",
        "tipo_esperado",
    ),
    [
        (
            [
                ("ALQUILER", "LOCAL-DEBUG", "PAGO LOCAL 17"),
            ],
            "TRANSFERENCIA PAGO LOCAL 17",
            ["PAGO LOCAL 17"],
            ["PAGO LOCAL 17"],
            "DIFERENCIA",
        ),
        (
            [
                ("ALQUILER", "LOCAL-DEBUG", "PAGO LOCAL 17"),
            ],
            "TRANSFERENCIA SIN REFERENCIA",
            ["PAGO LOCAL 17"],
            [],
            "DESCARTADA",
        ),
        (
            [
                ("AGUA", "LOCAL-DEBUG", "PAGO LOCAL 17"),
            ],
            "TRANSFERENCIA PAGO LOCAL 17",
            [],
            [],
            "DESCARTADA",
        ),
        (
            [
                ("ALQUILER", "OTRO-LOCAL", "PAGO LOCAL 17"),
            ],
            "TRANSFERENCIA PAGO LOCAL 17",
            [],
            [],
            "DESCARTADA",
        ),
    ],
)
def test_diagnosticar_emparejamiento_explica_aliases(
    inmueble,
    aliases,
    descripcion,
    aplicables,
    coincidentes,
    tipo_esperado,
) -> None:
    inmueble.referencia = "LOCAL-DEBUG"

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )
    previsto.fecha_prevista_desde = date(2026, 10, 1)
    previsto.contraparte = "Juan Pérez"

    bancario = _bancario_para_confirmar(
        "debug-aliases",
        99500,
    )
    bancario.descripcion_original = descripcion

    diagnostico = (
        servicios_conciliacion.diagnosticar_emparejamiento(
            bancario,
            previsto,
            aliases_configurados=aliases,
        )
    )

    assert diagnostico.tipo == tipo_esperado
    assert diagnostico.aliases_aplicables == aplicables
    assert diagnostico.aliases_coincidentes == coincidentes

    assert diagnostico.contraparte_identificada is bool(
        coincidentes
    )

    if tipo_esperado == "DESCARTADA":
        assert "CONTRAPARTE" in diagnostico.motivos_descarte
    else:
        assert diagnostico.motivos_descarte == []


@pytest.mark.parametrize(
    ("importe_bancario", "tipo_esperado"),
    [
        (95000, "DIFERENCIA"),
        (105000, "DIFERENCIA"),
        (94999, "DESCARTADA"),
        (105001, "DESCARTADA"),
    ],
)
def test_diagnosticar_emparejamiento_limite_cinco_por_ciento(
    inmueble,
    importe_bancario,
    tipo_esperado,
) -> None:
    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )
    previsto.fecha_prevista_desde = date(2026, 10, 1)
    previsto.contraparte = "Juan Pérez"

    bancario = _bancario_para_confirmar(
        f"debug-limite-{importe_bancario}",
        importe_bancario,
    )
    bancario.descripcion_original = "PAGO JUAN PEREZ"

    diagnostico = (
        servicios_conciliacion.diagnosticar_emparejamiento(
            bancario,
            previsto,
            aliases_configurados=[],
        )
    )

    assert diagnostico.tipo == tipo_esperado

    if tipo_esperado == "DESCARTADA":
        assert diagnostico.motivos_descarte == ["IMPORTE"]
    else:
        assert diagnostico.motivos_descarte == []


@pytest.mark.parametrize(
    ("estado_bancario", "estado_previsto", "motivos"),
    [
        ("PENDIENTE", "PENDIENTE", []),
        ("PARCIAL", "PARCIAL", []),
        ("CONCILIADO", "PENDIENTE", ["ESTADO_BANCARIO"]),
        ("DESCARTADO", "PENDIENTE", ["ESTADO_BANCARIO"]),
        ("PENDIENTE", "CONCILIADO", ["ESTADO_PREVISTO"]),
        ("PENDIENTE", "CANCELADO", ["ESTADO_PREVISTO"]),
        (
            "DESCARTADO",
            "CANCELADO",
            ["ESTADO_BANCARIO", "ESTADO_PREVISTO"],
        ),
    ],
)
def test_diagnosticar_emparejamiento_comprueba_estados(
    inmueble,
    estado_bancario,
    estado_previsto,
    motivos,
) -> None:
    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )
    previsto.fecha_prevista_desde = date(2026, 10, 1)
    previsto.contraparte = "Juan Pérez"
    previsto.estado = estado_previsto

    bancario = _bancario_para_confirmar(
        "debug-estados",
        100000,
    )
    bancario.fecha = date(2026, 10, 1)
    bancario.descripcion_original = "PAGO JUAN PEREZ"
    bancario.estado = estado_bancario

    diagnostico = (
        servicios_conciliacion.diagnosticar_emparejamiento(
            bancario,
            previsto,
            aliases_configurados=[],
        )
    )

    assert diagnostico.estado_bancario_valido is (
        estado_bancario in {"PENDIENTE", "PARCIAL"}
    )
    assert diagnostico.estado_previsto_valido is (
        estado_previsto in {"PENDIENTE", "PARCIAL"}
    )

    assert diagnostico.motivos_descarte == motivos

    if motivos:
        assert diagnostico.tipo == "DESCARTADA"
    else:
        assert diagnostico.tipo == "EXACTA"


@pytest.mark.parametrize(
    (
        "fecha_bancaria",
        "fecha_hasta",
        "descripcion",
        "aliases",
        "puntos_fecha",
        "puntos_contraparte",
        "puntos_alias",
    ),
    [
        # Fecha exacta y contraparte reconocida.
        (
            date(2026, 10, 1),
            None,
            "PAGO JUAN PEREZ",
            [],
            20,
            50,
            0,
        ),
        # Fecha compatible, pero sin puntos por fecha.
        (
            date(2026, 10, 5),
            None,
            "TRANSFERENCIA DESCONOCIDA",
            [],
            0,
            0,
            0,
        ),
        # Fecha dentro de un intervalo previsto.
        (
            date(2026, 10, 5),
            date(2026, 10, 10),
            "PAGO JUAN PEREZ",
            [],
            20,
            50,
            0,
        ),
        # Sólo se reconoce un alias.
        (
            date(2026, 10, 1),
            None,
            "TRANSFERENCIA REF LOCAL 17",
            ["REF LOCAL 17"],
            20,
            0,
            40,
        ),
        # Se reconoce la contraparte y un alias distinto.
        (
            date(2026, 10, 1),
            None,
            "JUAN PEREZ REF LOCAL 17",
            ["REF LOCAL 17"],
            20,
            50,
            40,
        ),
        # Alias idéntico a la contraparte: no duplica puntos.
        (
            date(2026, 10, 1),
            None,
            "JUAN PEREZ",
            ["Juan Pérez"],
            20,
            50,
            0,
        ),
    ],
)
def test_diagnosticar_emparejamiento_desglosa_puntuacion(
    inmueble,
    fecha_bancaria,
    fecha_hasta,
    descripcion,
    aliases,
    puntos_fecha,
    puntos_contraparte,
    puntos_alias,
) -> None:
    inmueble.referencia = "LOCAL-DEBUG"

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )
    previsto.fecha_prevista_desde = date(2026, 10, 1)
    previsto.fecha_prevista_hasta = fecha_hasta
    previsto.contraparte = "Juan Pérez"

    bancario = _bancario_para_confirmar(
        "debug-puntuacion",
        100000,
    )
    bancario.fecha = fecha_bancaria
    bancario.descripcion_original = descripcion

    aliases_configurados = [
        ("ALQUILER", "LOCAL-DEBUG", alias)
        for alias in aliases
    ]

    diagnostico = (
        servicios_conciliacion.diagnosticar_emparejamiento(
            bancario,
            previsto,
            aliases_configurados=aliases_configurados,
        )
    )

    assert diagnostico.tipo == "EXACTA"
    assert diagnostico.puntos_base == 100
    assert diagnostico.puntos_fecha == puntos_fecha
    assert diagnostico.puntos_contraparte == puntos_contraparte
    assert diagnostico.puntos_alias == puntos_alias

    assert diagnostico.puntuacion_total == (
        100
        + puntos_fecha
        + puntos_contraparte
        + puntos_alias
    )

    # Comparamos contra el algoritmo real de scoring,
    # para que ambos resultados no puedan divergir.
    propuesta = servicios_conciliacion.PropuestaConciliacion(
        bancarios=[bancario],
        previstos=[previsto],
        puntuacion=0,
    )

    puntuacion_real = (
        servicios_conciliacion._puntuar_calidad_propuesta(
            propuesta,
            aliases_configurados,
        )
    )

    assert diagnostico.puntuacion_total == puntuacion_real


@pytest.mark.parametrize(
    ("importe_bancario", "importe_previsto"),
    [
        (0, 100000),
        (100000, 0),
        (0, 0),
    ],
)
def test_diagnosticar_emparejamiento_rechaza_saldo_agotado(
    inmueble,
    monkeypatch,
    importe_bancario,
    importe_previsto,
) -> None:
    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )
    previsto.fecha_prevista_desde = date(2026, 10, 1)
    previsto.contraparte = "Juan Pérez"

    bancario = _bancario_para_confirmar(
        "debug-saldo-agotado",
        100000,
    )
    bancario.fecha = date(2026, 10, 1)
    bancario.descripcion_original = "PAGO JUAN PEREZ"

    saldo_original_bancario = (
        servicios_conciliacion.saldo_movimiento_bancario
    )
    saldo_original_previsto = (
        servicios_conciliacion.saldo_movimiento_previsto
    )

    def saldo_bancario(movimiento):
        if movimiento is bancario:
            return (
                100000 - importe_bancario,
                importe_bancario,
            )
        return saldo_original_bancario(movimiento)

    def saldo_previsto(movimiento):
        if movimiento is previsto:
            return (
                100000 - importe_previsto,
                importe_previsto,
            )
        return saldo_original_previsto(movimiento)

    monkeypatch.setattr(
        servicios_conciliacion,
        "saldo_movimiento_bancario",
        saldo_bancario,
    )
    monkeypatch.setattr(
        servicios_conciliacion,
        "saldo_movimiento_previsto",
        saldo_previsto,
    )

    diagnostico = (
        servicios_conciliacion.diagnosticar_emparejamiento(
            bancario,
            previsto,
            aliases_configurados=[],
        )
    )

    assert diagnostico.tipo == "DESCARTADA"
    assert "SALDO_AGOTADO" in diagnostico.motivos_descarte


def test_puntuacion_agrupada_usa_media_de_parejas(
    inmueble,
) -> None:
    """El grupo no recibe puntos adicionales por su tamaño."""

    primero = _previsto_para_confirmar(
        inmueble, "Alquiler", 60000
    )
    segundo = _previsto_para_confirmar(
        inmueble, "Agua", 40000
    )

    primero.fecha_prevista_desde = date(2026, 10, 1)
    segundo.fecha_prevista_desde = date(2026, 10, 1)

    primero.contraparte = "Juan Pérez"
    segundo.contraparte = "Otra persona"

    bancario = _bancario_para_confirmar(
        "debug-puntuacion-grupo", 100000
    )
    bancario.fecha = date(2026, 10, 1)
    bancario.descripcion_original = "PAGO JUAN PEREZ"

    propuesta = PropuestaConciliacion(
        bancarios=[bancario],
        previstos=[primero, segundo],
        puntuacion=0,
    )

    puntuacion = (
        servicios_conciliacion._puntuar_calidad_propuesta(
            propuesta,
            [],
        )
    )

    # Pareja 1: fecha 20 + contraparte 50 = 70.
    # Pareja 2: fecha 20 + contraparte 0 = 20.
    # Grupo: 100 + (70 + 20) // 2 = 145.
    assert puntuacion == 145


@pytest.mark.parametrize(
    (
        "contraparte",
        "descripcion",
        "aliases",
        "identificada",
        "aplicables",
        "coincidentes",
    ),
    [
        (
            "Juan Pérez",
            "TRANSFERENCIA JUAN PEREZ",
            [],
            True,
            [],
            [],
        ),
        (
            "Juan Pérez",
            "TRANSFERENCIA J. PEREZ",
            [("ALQUILER", "LOCAL-DEBUG", "J. PEREZ")],
            True,
            ["J. PEREZ"],
            ["J. PEREZ"],
        ),
        (
            "Juan Pérez",
            "PAGO LOCAL 17",
            [("AGUA", "LOCAL-DEBUG", "PAGO LOCAL 17")],
            False,
            [],
            [],
        ),
        (
            "Juan Pérez",
            "PAGO LOCAL 17",
            [("ALQUILER", "OTRO-LOCAL", "PAGO LOCAL 17")],
            False,
            [],
            [],
        ),
        (
            "Juan Pérez",
            "TRANSFERENCIA DESCONOCIDA",
            [("ALQUILER", "LOCAL-DEBUG", "J. PEREZ")],
            False,
            ["J. PEREZ"],
            [],
        ),
        (
            "José Núñez",
            "INGRESO JOSE NUNEZ",
            [],
            True,
            [],
            [],
        ),
        (
            "",
            "TRANSFERENCIA DESCONOCIDA",
            [],
            False,
            [],
            [],
        ),
    ],
)
def test_identificacion_contraparte_coincide_con_diagnostico(
    inmueble,
    contraparte,
    descripcion,
    aliases,
    identificada,
    aplicables,
    coincidentes,
) -> None:
    inmueble.referencia = "LOCAL-DEBUG"

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )
    previsto.contraparte = contraparte
    previsto.fecha_prevista_desde = date(2026, 10, 1)

    bancario = _bancario_para_confirmar(
        "debug-identificacion",
        97000,
    )
    bancario.fecha = date(2026, 10, 1)
    bancario.descripcion_original = descripcion

    identificacion_automatica = (
        servicios_conciliacion._bancario_identifica_contraparte(
            bancario,
            previsto,
            aliases,
        )
    )

    diagnostico = (
        servicios_conciliacion.diagnosticar_emparejamiento(
            bancario,
            previsto,
            aliases_configurados=aliases,
        )
    )

    assert identificacion_automatica is identificada
    assert diagnostico.contraparte_identificada is identificada

    assert diagnostico.aliases_aplicables == aplicables
    assert diagnostico.aliases_coincidentes == coincidentes

    if identificada:
        assert diagnostico.tipo == "DIFERENCIA"
        assert "CONTRAPARTE" not in diagnostico.motivos_descarte
    else:
        assert diagnostico.tipo == "DESCARTADA"
        assert "CONTRAPARTE" in diagnostico.motivos_descarte


def test_diagnostico_identificacion_conserva_todos_los_aliases(
    inmueble,
) -> None:
    inmueble.referencia = "LOCAL-DEBUG"

    previsto = _previsto_para_confirmar(
        inmueble,
        "Alquiler octubre",
        100000,
    )
    previsto.fecha_prevista_desde = date(2026, 10, 1)
    previsto.contraparte = "Juan Pérez"

    bancario = _bancario_para_confirmar(
        "debug-varios-aliases",
        97000,
    )
    bancario.fecha = date(2026, 10, 1)
    bancario.descripcion_original = (
        "PAGO JUAN PEREZ LOCAL 17 REF-123"
    )

    aliases = [
        ("ALQUILER", "LOCAL-DEBUG", "LOCAL 17"),
        ("ALQUILER", "LOCAL-DEBUG", "REF-123"),
        ("ALQUILER", "LOCAL-DEBUG", "OTRO TEXTO"),
    ]

    diagnostico = (
        servicios_conciliacion.diagnosticar_emparejamiento(
            bancario,
            previsto,
            aliases_configurados=aliases,
        )
    )

    assert diagnostico.contraparte_identificada is True

    assert diagnostico.aliases_aplicables == [
        "LOCAL 17",
        "REF-123",
        "OTRO TEXTO",
    ]

    assert diagnostico.aliases_coincidentes == [
        "LOCAL 17",
        "REF-123",
    ]

    assert diagnostico.tipo == "DIFERENCIA"
    assert diagnostico.motivos_descarte == []

    # Dos alias coincidentes no duplican la bonificación.
    assert diagnostico.puntos_contraparte == 50
    assert diagnostico.puntos_alias == 40
    assert diagnostico.puntuacion_total == 210


@pytest.mark.parametrize(
    (
        "importes_previstos",
        "importes_bancarios",
        "tipo_esperado",
        "motivos_esperados",
    ),
    [
        ([100000, 20000], [120000], "GRUPO_EXACTO", []),
        ([120000], [100000, 20000], "GRUPO_EXACTO", []),
        (
            [100000, 20000],
            [119962],
            "GRUPO_DIFERENCIA",
            [],
        ),
    ],
)
def test_diagnosticar_grupo_conciliacion_importes(
    inmueble,
    importes_previstos,
    importes_bancarios,
    tipo_esperado,
    motivos_esperados,
) -> None:
    previstos = [
        _previsto_para_confirmar(
            inmueble,
            f"Previsto {indice}",
            importe,
        )
        for indice, importe in enumerate(
            importes_previstos,
            start=1,
        )
    ]

    bancarios = [
        _bancario_para_confirmar(
            f"debug-grupo-{indice}",
            importe,
        )
        for indice, importe in enumerate(
            importes_bancarios,
            start=1,
        )
    ]

    diagnostico = (
        servicios_conciliacion.diagnosticar_grupo_conciliacion(
            bancarios,
            previstos,
            aliases_configurados=[],
        )
    )

    assert diagnostico.tipo == tipo_esperado
    assert diagnostico.motivos_descarte == motivos_esperados

    assert diagnostico.total_bancario == sum(
        importes_bancarios
    )
    assert diagnostico.total_previsto == sum(
        importes_previstos
    )

    assert diagnostico.diferencia == (
        sum(importes_bancarios)
        - sum(importes_previstos)
    )

    assert diagnostico.importe_exacto is (
        sum(importes_bancarios)
        == sum(importes_previstos)
    )


def test_diagnosticar_grupo_desglosa_parejas_y_puntuacion(
    inmueble,
) -> None:
    primero = _previsto_para_confirmar(
        inmueble, "Alquiler", 100000
    )
    segundo = _previsto_para_confirmar(
        inmueble, "Agua", 20000
    )

    primero.fecha_prevista_desde = date(2026, 10, 1)
    segundo.fecha_prevista_desde = date(2026, 10, 1)

    primero.contraparte = "Juan Pérez"
    segundo.contraparte = "Otra persona"

    bancario = _bancario_para_confirmar(
        "debug-grupo-desglose", 120000
    )
    bancario.fecha = date(2026, 10, 1)
    bancario.descripcion_original = "PAGO JUAN PEREZ"

    diagnostico = (
        servicios_conciliacion.diagnosticar_grupo_conciliacion(
            [bancario],
            [primero, segundo],
            aliases_configurados=[],
        )
    )

    assert diagnostico.tipo == "GRUPO_EXACTO"
    assert len(diagnostico.parejas) == 2

    assert [
        pareja.puntos_fecha
        for pareja in diagnostico.parejas
    ] == [20, 20]

    assert [
        pareja.puntos_contraparte
        for pareja in diagnostico.parejas
    ] == [50, 0]

    assert diagnostico.puntuacion_total == 145

    # Debe coincidir con el selector automático.
    propuesta = PropuestaConciliacion(
        bancarios=[bancario],
        previstos=[primero, segundo],
        puntuacion=0,
    )

    assert diagnostico.puntuacion_total == (
        servicios_conciliacion._puntuar_calidad_propuesta(
            propuesta,
            [],
        )
    )


@pytest.mark.parametrize(
    ("naturaleza_segundo", "fecha_bancaria", "motivo"),
    [
        ("GASTO", date(2026, 10, 5), "NATURALEZA"),
        ("INGRESO", date(2026, 9, 20), "FECHA"),
    ],
)
def test_diagnosticar_grupo_rechaza_parejas_incompatibles(
    inmueble,
    naturaleza_segundo,
    fecha_bancaria,
    motivo,
) -> None:
    primero = _previsto_para_confirmar(
        inmueble, "Alquiler", 100000
    )
    segundo = _previsto_para_confirmar(
        inmueble, "Agua", 20000
    )

    primero.fecha_prevista_desde = date(2026, 10, 1)
    segundo.fecha_prevista_desde = date(2026, 10, 1)
    segundo.naturaleza = naturaleza_segundo

    bancario = _bancario_para_confirmar(
        "debug-grupo-incompatible", 120000
    )
    bancario.fecha = fecha_bancaria

    diagnostico = (
        servicios_conciliacion.diagnosticar_grupo_conciliacion(
            [bancario],
            [primero, segundo],
            aliases_configurados=[],
        )
    )

    assert diagnostico.tipo == "DESCARTADO"
    assert motivo in diagnostico.motivos_descarte


@pytest.mark.parametrize(
    "cardinalidad",
    ["uno_a_dos", "dos_a_uno"],
)
@pytest.mark.parametrize(
    ("total_bancario", "debe_proponerse"),
    [
        (100000, True),   # Exacta
        (95000, True),    # Diferencia -5 %
        (105000, True),   # Diferencia +5 %
        (94999, False),   # Supera el 5 % por un céntimo
        (105001, False),  # Supera el 5 % por un céntimo
    ],
)
def test_propuestas_agrupadas_admiten_diferencia_cinco_por_ciento(
    session,
    inmueble,
    cardinalidad,
    total_bancario,
    debe_proponerse,
) -> None:
    """El margen se calcula sobre el total previsto del grupo."""

    if cardinalidad == "uno_a_dos":
        previsto = _previsto_para_confirmar(
            inmueble, "Alquiler octubre", 100000
        )
        previsto.contraparte = "Juan Pérez"
        previsto.fecha_prevista_desde = date(2026, 10, 1)

        primero = _bancario_para_confirmar(
            f"margen-12-a-{total_bancario}",
            40000,
        )
        segundo = _bancario_para_confirmar(
            f"margen-12-b-{total_bancario}",
            total_bancario - 40000,
        )

        previstos = [previsto]
        bancarios = [primero, segundo]

    else:
        primero = _previsto_para_confirmar(
            inmueble, "Alquiler octubre", 60000
        )
        segundo = _previsto_para_confirmar(
            inmueble, "Agua octubre", 40000
        )

        for previsto in (primero, segundo):
            previsto.contraparte = "Juan Pérez"
            previsto.fecha_prevista_desde = date(2026, 10, 1)

        bancario = _bancario_para_confirmar(
            f"margen-21-{total_bancario}",
            total_bancario,
        )

        previstos = [primero, segundo]
        bancarios = [bancario]

    for bancario in bancarios:
        bancario.fecha = date(2026, 10, 1)
        bancario.descripcion_original = "PAGO JUAN PEREZ"

    session.add_all([*previstos, *bancarios])
    session.flush()

    propuestas = buscar_propuestas_conciliacion(
        bancarios,
        previstos,
        aliases_configurados=[],
    )

    encontrada = any(
        set(propuesta.bancarios) == set(bancarios)
        and set(propuesta.previstos) == set(previstos)
        for propuesta in propuestas
    )

    assert encontrada is debe_proponerse


def test_propuesta_exacta_tiene_prioridad_sobre_grupo_con_diferencia(
    session,
    inmueble,
) -> None:
    """La diferencia agrupada no desplaza una coincidencia exacta."""

    previsto = _previsto_para_confirmar(
        inmueble, "Alquiler octubre", 100000
    )
    previsto.fecha_prevista_desde = date(2026, 10, 1)
    previsto.contraparte = "Juan Pérez"

    exacto = _bancario_para_confirmar(
        "prioridad-exacto",
        100000,
    )
    parcial_1 = _bancario_para_confirmar(
        "prioridad-parcial-1",
        40000,
    )
    parcial_2 = _bancario_para_confirmar(
        "prioridad-parcial-2",
        59000,
    )

    for bancario in (exacto, parcial_1, parcial_2):
        bancario.fecha = date(2026, 10, 1)
        bancario.descripcion_original = "PAGO JUAN PEREZ"

    session.add_all([
        previsto,
        exacto,
        parcial_1,
        parcial_2,
    ])
    session.flush()

    propuestas = buscar_propuestas_conciliacion(
        [exacto, parcial_1, parcial_2],
        [previsto],
        aliases_configurados=[],
    )

    assert len(propuestas) == 1

    assert propuestas[0].bancarios == [exacto]
    assert propuestas[0].previstos == [previsto]


@pytest.mark.parametrize(
    ("importe_bancario", "tipo", "motivos"),
    [
        (100000, "GRUPO_EXACTO", []),
        (95000, "GRUPO_DIFERENCIA", []),
        (105000, "GRUPO_DIFERENCIA", []),
        (94999, "DESCARTADO", ["IMPORTE_GRUPO"]),
        (105001, "DESCARTADO", ["IMPORTE_GRUPO"]),
    ],
)
def test_diagnostico_grupo_aplica_margen_cinco_por_ciento(
    inmueble,
    importe_bancario,
    tipo,
    motivos,
) -> None:
    primero = _previsto_para_confirmar(
        inmueble, "Alquiler octubre", 60000
    )
    segundo = _previsto_para_confirmar(
        inmueble, "Agua octubre", 40000
    )

    for previsto in (primero, segundo):
        previsto.fecha_prevista_desde = date(2026, 10, 1)
        previsto.contraparte = "Juan Pérez"

    bancario = _bancario_para_confirmar(
        f"debug-margen-grupo-{importe_bancario}",
        importe_bancario,
    )
    bancario.fecha = date(2026, 10, 1)
    bancario.descripcion_original = "PAGO JUAN PEREZ"

    diagnostico = (
        servicios_conciliacion.diagnosticar_grupo_conciliacion(
            [bancario],
            [primero, segundo],
            aliases_configurados=[],
        )
    )

    assert diagnostico.tipo == tipo
    assert diagnostico.motivos_descarte == motivos
    assert diagnostico.importe_exacto is (
        importe_bancario == 100000
    )
    assert diagnostico.diferencia == (
        importe_bancario - 100000
    )


def test_propuesta_aproximada_prefiere_grupo_con_menor_diferencia(
    session,
    inmueble,
) -> None:
    """AVLOGRO: 1.021 € debe cubrir alquiler y agua."""

    alquiler = _previsto_para_confirmar(
        inmueble,
        "Alquiler del local octubre",
        100000,
    )
    agua = _previsto_para_confirmar(
        inmueble,
        "Reembolso de gastos de agua",
        2069,
    )

    for previsto in (alquiler, agua):
        previsto.naturaleza = "INGRESO"
        previsto.fecha_prevista_desde = date(2026, 10, 1)
        previsto.fecha_prevista_hasta = date(2026, 10, 31)

    bancario = _bancario_para_confirmar(
        "avlogro-alquiler-agua",
        102100,
    )
    bancario.naturaleza = "INGRESO"
    bancario.fecha = date(2026, 10, 5)
    bancario.descripcion_original = (
        "GERARDO LOPEZ ALQUILER DEL LOCAL OCTUBRE"
    )

    session.add_all([alquiler, agua, bancario])
    session.flush()

    aliases = [
        ("INQUILINO", inmueble.referencia, "GERARDO LOPEZ"),
    ]

    propuestas = buscar_propuestas_conciliacion(
        [bancario],
        [alquiler, agua],
        aliases_configurados=aliases,
    )

    assert len(propuestas) == 1
    assert propuestas[0].bancarios == [bancario]
    assert set(propuestas[0].previstos) == {alquiler, agua}


def test_propuesta_exacta_prevalece_sobre_grupo_aproximado(
    session,
    inmueble,
) -> None:
    """Una coincidencia exacta no se desplaza por un grupo aproximado."""

    exacto = _previsto_para_confirmar(
        inmueble, "Alquiler completo", 102100
    )
    alquiler = _previsto_para_confirmar(
        inmueble, "Alquiler octubre", 100000
    )
    agua = _previsto_para_confirmar(
        inmueble, "Reembolso agua", 2069
    )

    for previsto in (exacto, alquiler, agua):
        previsto.naturaleza = "INGRESO"
        previsto.contraparte = "GERARDO LOPEZ"
        previsto.fecha_prevista_desde = date(2026, 10, 1)
        previsto.fecha_prevista_hasta = date(2026, 10, 31)

    bancario = _bancario_para_confirmar(
        "avlogro-prioridad-exacta", 102100
    )
    bancario.naturaleza = "INGRESO"
    bancario.fecha = date(2026, 10, 5)
    bancario.descripcion_original = "GERARDO LOPEZ"

    session.add_all([exacto, alquiler, agua, bancario])
    session.flush()

    propuestas = buscar_propuestas_conciliacion(
        [bancario],
        [exacto, alquiler, agua],
        aliases_configurados=[],
    )

    assert len(propuestas) == 1
    assert propuestas[0].bancarios == [bancario]
    assert propuestas[0].previstos == [exacto]


def test_no_elegir_entre_agrupaciones_aproximadas_ambiguas(
    session,
    inmueble,
) -> None:
    """No resolver dos grupos alternativos sólo por cercanía."""

    alquiler = _previsto_para_confirmar(
        inmueble, "Alquiler octubre", 100000
    )
    agua = _previsto_para_confirmar(
        inmueble, "Reembolso agua", 2069
    )
    otro_gasto = _previsto_para_confirmar(
        inmueble, "Reembolso otro gasto", 2100
    )

    for previsto in (alquiler, agua, otro_gasto):
        previsto.fecha_prevista_desde = date(2026, 10, 1)
        previsto.fecha_prevista_hasta = date(2026, 10, 31)
        previsto.contraparte = "GERARDO LOPEZ"

    bancario = _bancario_para_confirmar(
        "grupo-ambiguo-102100", 102100
    )
    bancario.descripcion_original = "GERARDO LOPEZ"

    session.add_all([
        alquiler, agua, otro_gasto, bancario,
    ])
    session.flush()

    propuestas = buscar_propuestas_conciliacion(
        [bancario],
        [alquiler, agua, otro_gasto],
        aliases_configurados=[],
    )

    # Alquiler + agua: diferencia de 31 céntimos.
    # Alquiler + otro gasto: diferencia de 0 céntimos.
    #
    # La segunda es exacta y, por nuestra regla de prioridad,
    # debe ganar. En este test NO hay ambigüedad aproximada.
    assert len(propuestas) == 1
    assert propuestas[0].previstos == [alquiler, otro_gasto]


def test_no_elegir_grupos_aproximados_por_diferencia_sola(
    session,
    inmueble,
) -> None:
    """Dos agrupaciones alternativas requieren revisión manual."""

    alquiler = _previsto_para_confirmar(
        inmueble, "Alquiler octubre", 100000
    )
    agua = _previsto_para_confirmar(
        inmueble, "Reembolso agua", 2069
    )
    otro_gasto = _previsto_para_confirmar(
        inmueble, "Reembolso otro gasto", 2050
    )

    for previsto in (alquiler, agua, otro_gasto):
        previsto.fecha_prevista_desde = date(2026, 10, 1)
        previsto.fecha_prevista_hasta = date(2026, 10, 31)
        previsto.contraparte = "GERARDO LOPEZ"

    bancario = _bancario_para_confirmar(
        "grupo-ambiguo-sin-exacta", 102100
    )
    bancario.descripcion_original = "GERARDO LOPEZ"

    session.add_all([
        alquiler, agua, otro_gasto, bancario,
    ])
    session.flush()

    propuestas = buscar_propuestas_conciliacion(
        [bancario],
        [alquiler, agua, otro_gasto],
        aliases_configurados=[],
    )

    # Alquiler + agua: diferencia de 31 céntimos.
    # Alquiler + otro gasto: diferencia de 50 céntimos.
    #
    # Ambos grupos son plausibles, con la misma contraparte
    # y las mismas fechas. La cercanía no basta para elegir.
    assert propuestas == []


def test_selecciona_agrupaciones_aproximadas_independientes(
    session,
    inmueble,
) -> None:
    """Dos pagos distintos se proponen sin interferirse."""

    alquiler_a = _previsto_para_confirmar(
        inmueble, "Alquiler A", 100000
    )
    agua_a = _previsto_para_confirmar(
        inmueble, "Agua A", 2069
    )
    alquiler_b = _previsto_para_confirmar(
        inmueble, "Alquiler B", 80000
    )
    agua_b = _previsto_para_confirmar(
        inmueble, "Agua B", 1500
    )

    for previsto in (alquiler_a, agua_a):
        previsto.fecha_prevista_desde = date(2026, 10, 1)
        previsto.fecha_prevista_hasta = date(2026, 10, 31)
        previsto.contraparte = "PAGADOR A"

    for previsto in (alquiler_b, agua_b):
        previsto.fecha_prevista_desde = date(2026, 10, 1)
        previsto.fecha_prevista_hasta = date(2026, 10, 31)
        previsto.contraparte = "PAGADOR B"

    bancario_a = _bancario_para_confirmar(
        "independiente-a", 102100
    )
    bancario_a.descripcion_original = "PAGADOR A"

    bancario_b = _bancario_para_confirmar(
        "independiente-b", 81520
    )
    bancario_b.descripcion_original = "PAGADOR B"

    session.add_all([
        alquiler_a, agua_a,
        alquiler_b, agua_b,
        bancario_a, bancario_b,
    ])
    session.flush()

    propuestas = buscar_propuestas_conciliacion(
        [bancario_a, bancario_b],
        [alquiler_a, agua_a, alquiler_b, agua_b],
        aliases_configurados=[],
    )

    assert len(propuestas) == 2

    grupos = {
        frozenset(propuesta.previstos)
        for propuesta in propuestas
    }

    assert grupos == {
        frozenset([alquiler_a, agua_a]),
        frozenset([alquiler_b, agua_b]),
    }


@pytest.mark.parametrize(
    ("naturaleza", "concepto", "debe_identificar"),
    [
        ("INGRESO", "Alquiler octubre", True),
        ("INGRESO", "Reembolso de agua", True),
        ("INGRESO", "Otros ingresos", True),
        ("GASTO", "Agua octubre", False),
    ],
)
def test_alias_inquilino_se_aplica_a_ingresos_del_inmueble(
    inmueble,
    naturaleza,
    concepto,
    debe_identificar,
) -> None:
    previsto = crear_movimiento_previsto(
        inmueble=inmueble,
        naturaleza=naturaleza,
        concepto=concepto,
        importe_esperado=10000,
    )

    bancario = _bancario_para_confirmar(
        f"alias-inquilino-{naturaleza}-{concepto}",
        10000,
    )
    bancario.naturaleza = naturaleza
    bancario.descripcion_original = "PAGO GERARDO LOPEZ"

    aliases = [
        ("INQUILINO", inmueble.referencia, "GERARDO LOPEZ"),
    ]

    identificado = (
        servicios_conciliacion._bancario_identifica_contraparte(
            bancario,
            previsto,
            aliases,
        )
    )

    assert identificado is debe_identificar


def test_alias_inquilino_no_identifica_otro_inmueble(
    inmueble,
) -> None:
    previsto = _previsto_para_confirmar(
        inmueble, "Reembolso de agua", 2069
    )

    bancario = _bancario_para_confirmar(
        "alias-inquilino-otro-inmueble", 2069
    )
    bancario.descripcion_original = "GERARDO LOPEZ"

    aliases = [
        ("INQUILINO", "OTRO-INMUEBLE", "GERARDO LOPEZ"),
    ]

    assert not servicios_conciliacion._bancario_identifica_contraparte(
        bancario,
        previsto,
        aliases,
    )

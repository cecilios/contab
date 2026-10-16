"""Pruebas de la lógica de negocio de conciliación."""

import pytest

from datetime import date
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from contab.config import CategoriaContable
from contab.models import (
    Conciliacion,
    Inmueble,
    MovimientoBancario,
    MovimientoPrevisto,
)
from contab.contabilidad.services import crear_apunte_contable
from contab.conciliacion.services import (
    ConciliacionError,
    actualizar_estado_movimiento_bancario,
    actualizar_estado_movimiento_previsto,
    asociar_movimientos,
    buscar_candidatos_conciliacion,
    cancelar_movimiento_previsto,
    clasificar_movimiento_bancario,
    clasificar_movimientos_bancarios,
    conciliar_movimiento_previsto_manualmente,
    confirmar_conciliacion,
    confirmar_grupo_conciliacion,
    crear_movimiento_desde_apunte,
    crear_movimiento_previsto,
    descartar_movimiento_bancario,
    deshacer_asociacion_bancaria,
    deshacer_conciliacion_manual,
    proponer_conciliacion,
    puntuar_candidato_conciliacion,
    restaurar_movimiento_bancario,
    restaurar_movimiento_previsto,
    saldo_movimiento_bancario,
    saldo_movimiento_previsto,
    validar_asociacion,
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



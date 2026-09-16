"""Pruebas de la lógica de negocio de conciliación."""

import pytest

from datetime import date
from sqlalchemy.exc import IntegrityError

from contab.config import CategoriaContable
from contab.models import (
    Inmueble,
    MovimientoBancario,
    MovimientoPrevisto,
)
from contab.contabilidad.services import crear_apunte_contable
from contab.conciliacion.services import (
    ConciliacionError,
    buscar_candidatos_conciliacion,
    cancelar_movimiento_previsto,
    clasificar_movimiento_bancario,
    clasificar_movimientos_bancarios,
    confirmar_conciliacion,
    crear_movimiento_desde_apunte,
    crear_movimiento_previsto,
    descartar_movimiento_bancario,
    proponer_conciliacion,
    puntuar_candidato_conciliacion,
    restaurar_movimiento_bancario,
    restaurar_movimiento_previsto,
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



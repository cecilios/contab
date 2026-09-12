"""Pruebas de la lógica de negocio de conciliación."""

import pytest

from datetime import date

from contab.config import CategoriaContable
from contab.contabilidad.services import crear_apunte_contable
from contab.conciliacion.services import (
    ConciliacionError,
    descartar_movimiento_bancario,
    restaurar_movimiento_bancario,
)
from contab.models import (
    MovimientoBancario,
    MovimientoPrevisto,
)
from contab.conciliacion.services import (
    ConciliacionError,
    cancelar_movimiento_previsto,
    crear_movimiento_desde_apunte,
    crear_movimiento_previsto,
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



from datetime import date

import pytest
from sqlalchemy import func, select

from contab.models import (
    ApunteContable,
    Conciliacion,
    DistribucionApunte,
    Inmueble,
    MovimientoBancario,
    MovimientoPrevisto,
)

from contab.migrations.versions.b8f0d5a2848b_2026_10_08_dejar_datos_coherentes import (
    _regularizar_datos,
)



def _crear_inmueble_subdividido(session):
    inmueble = Inmueble(
        referencia="EDIFICIO-COMUN",
        tipo="T",
        codigo_facturacion="EC",
        descripcion="Elementos comunes",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=10000,
    )

    local_a = Inmueble(
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="LA",
        descripcion="Local A",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=6000,
        inmueble_padre=inmueble,
    )

    local_b = Inmueble(
        referencia="LOCAL-B",
        tipo="L",
        codigo_facturacion="LB",
        descripcion="Local B",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=4000,
        inmueble_padre=inmueble,
    )

    session.add_all(
        [
            inmueble,
            local_a,
            local_b,
        ]
    )
    session.flush()

    return inmueble, local_a, local_b


def _crear_apunte_historico(
    session,
    inmueble,
    *,
    tratamiento: str,
) -> ApunteContable:
    apunte = ApunteContable(
        inmueble=inmueble,
        fecha=date(2026, 10, 2),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        tratamiento=tratamiento,
        nombre_documento="comunidad.pdf",
        base=10001,
        iva_importe=2001,
        retencion_importe=1001,
        total=11001,
        tercero_nombre="Proveedor",
        tercero_nif="",
        referencia_documento="",
        ruta_documento="",
    )

    session.add(apunte)
    session.flush()

    return apunte


def _crear_movimiento_historico(
    session,
    apunte,
) -> MovimientoPrevisto:
    movimiento = MovimientoPrevisto(
        inmueble=apunte.inmueble,
        apunte=apunte,
        naturaleza="GASTO",
        concepto=apunte.concepto,
        importe_esperado=apunte.total,
        contraparte=apunte.tercero_nombre,
        estado="PENDIENTE",
    )

    session.add(movimiento)
    session.flush()

    return movimiento



def test_regularizacion_crea_distribuciones_historicas(
    session,
) -> None:
    inmueble, local_a, local_b = (
        _crear_inmueble_subdividido(session)
    )

    apunte = _crear_apunte_historico(
        session,
        inmueble,
        tratamiento="REPERCUTIR",
    )

    _regularizar_datos(
        session.connection()
    )

    session.expire_all()

    distribuciones = session.scalars(
        select(DistribucionApunte)
        .where(
            DistribucionApunte.apunte_id
            == apunte.id
        )
        .order_by(
            DistribucionApunte.inmueble_id
        )
    ).all()

    assert len(distribuciones) == 2

    por_referencia = {
        distribucion.inmueble.referencia: distribucion
        for distribucion in distribuciones
    }

    primera = por_referencia["LOCAL-A"]
    ultima = por_referencia["LOCAL-B"]

    assert primera.inmueble is local_a
    assert primera.participacion == 6000
    assert primera.base == 6001
    assert primera.iva_importe == 1201
    assert primera.retencion_importe == 601
    assert primera.total == 6601

    assert ultima.inmueble is local_b
    assert ultima.participacion == 4000
    assert ultima.base == 4000
    assert ultima.iva_importe == 800
    assert ultima.retencion_importe == 400
    assert ultima.total == 4400

    assert sum(
        d.total
        for d in distribuciones
    ) == apunte.total


def test_regularizacion_elimina_movimiento_de_repercutir_en_t(
    session,
) -> None:
    inmueble, _, _ = (
        _crear_inmueble_subdividido(session)
    )

    apunte = _crear_apunte_historico(
        session,
        inmueble,
        tratamiento="REPERCUTIR",
    )

    movimiento = _crear_movimiento_historico(
        session,
        apunte,
    )

    movimiento_id = movimiento.id

    _regularizar_datos(
        session.connection()
    )

    session.expire_all()

    assert session.get(
        MovimientoPrevisto,
        movimiento_id,
    ) is None


def test_regularizacion_conserva_movimiento_de_contabilizar_en_t(
    session,
) -> None:
    inmueble, _, _ = (
        _crear_inmueble_subdividido(session)
    )

    apunte = _crear_apunte_historico(
        session,
        inmueble,
        tratamiento="CONTABILIZAR",
    )

    movimiento = _crear_movimiento_historico(
        session,
        apunte,
    )

    movimiento_id = movimiento.id

    _regularizar_datos(
        session.connection()
    )

    session.expire_all()

    assert session.get(
        MovimientoPrevisto,
        movimiento_id,
    ) is not None


def test_regularizacion_no_elimina_movimiento_conciliado(
    session,
) -> None:
    inmueble, _, _ = (
        _crear_inmueble_subdividido(session)
    )

    apunte = _crear_apunte_historico(
        session,
        inmueble,
        tratamiento="REPERCUTIR",
    )

    movimiento = _crear_movimiento_historico(
        session,
        apunte,
    )

    bancario = MovimientoBancario(
        fecha=date(2026, 10, 5),
        naturaleza="GASTO",
        importe=apunte.total,
        tipo_original="TRANSFERENCIA",
        descripcion_original="Pago",
        referencia_bancaria="REF-1",
        huella_importacion="huella-test",
    )

    conciliacion = Conciliacion(
        movimiento_bancario=bancario,
        movimiento_previsto=movimiento,
        importe_asociado=apunte.total,
    )

    session.add_all(
        [
            bancario,
            conciliacion,
        ]
    )
    session.flush()

    with pytest.raises(
        RuntimeError,
        match="concili",
    ):
        _regularizar_datos(
            session.connection()
        )


def test_regularizacion_no_duplica_distribuciones_existentes(
    session,
) -> None:
    inmueble, _, _ = (
        _crear_inmueble_subdividido(session)
    )

    apunte = _crear_apunte_historico(
        session,
        inmueble,
        tratamiento="CONTABILIZAR",
    )

    _regularizar_datos(
        session.connection()
    )
    _regularizar_datos(
        session.connection()
    )

    cantidad = session.scalar(
        select(
            func.count(DistribucionApunte.id)
        ).where(
            DistribucionApunte.apunte_id
            == apunte.id
        )
    )

    assert cantidad == 2


def test_regularizacion_rechaza_participaciones_incompletas(
    session,
) -> None:
    inmueble, _, local_b = (
        _crear_inmueble_subdividido(session)
    )

    local_b.participacion = 3000

    _crear_apunte_historico(
        session,
        inmueble,
        tratamiento="CONTABILIZAR",
    )

    session.flush()

    with pytest.raises(
        RuntimeError,
        match="participaciones",
    ):
        _regularizar_datos(
            session.connection()
        )


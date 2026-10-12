"""Pruebas de las rutas web del módulo de reembolsos."""

import pytest
from datetime import date
from sqlalchemy import select

from contab.app import create_app
from contab.config import CategoriaContable
from contab.contabilidad.services import (
    crear_apunte_contable,
)
from contab.database import Base
from contab.models import (
    Contrato,
    ContratoInquilino,
    ImputacionContrato,
    Inmueble,
    Inquilino,
    MovimientoPrevisto,
    SolicitudReembolso,
    SolicitudReembolsoLinea,
)


@pytest.fixture
def app():
    """Crea una aplicación aislada para las pruebas de reembolsos."""

    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="test-secret-key",
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    engine = session_factory.kw["bind"]

    Base.metadata.create_all(
        engine
    )

    try:
        yield app
    finally:
        engine.dispose()


def _seleccionar_base(client) -> None:
    """Selecciona la base de datos utilizada por la prueba."""

    response = client.post(
        "/",
        data={
            "database": "test",
        },
    )

    assert response.status_code == 302


def _categorias_gastos():
    return {
        "GAS_COMUNIDAD": CategoriaContable(
            codigo="GAS_COMUNIDAD",
            naturaleza="GASTO",
            nombre="Comunidad",
            activa=True,
            subcategorias=(),
        ),
    }


def _crear_contrato(
    session,
    *,
    fecha_inicio: date = date(2026, 1, 1),
) -> Contrato:
    """Crea un contrato con un titular para las pruebas."""

    inmueble = Inmueble(
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="A",
        descripcion="Local A",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=date(2035, 12, 31),
        genera_factura=True,
        fecha_inicio_facturacion=fecha_inicio,
        fianza=0,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )

    contrato.titulares.append(
        ContratoInquilino(
            inquilino=Inquilino(
                nombre="Empresa Inquilina, S.L.",
                nif="A12345678",
            ),
            orden=1,
        )
    )

    session.add(contrato)
    session.commit()

    return contrato


def test_reembolsos_muestra_gastos_pendientes(app) -> None:

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)

        apunte = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=_categorias_gastos(),
            fecha=date(2026, 8, 13),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Agua",
            base=2839,
            tratamiento="REPERCUTIR",
        )

        session.add(apunte)
        session.commit()

    client = app.test_client()
    _seleccionar_base(client)

    response = client.get(
        "/reembolsos/"
    )

    assert response.status_code == 200

    assert "LOCAL-A" in response.text
    assert "Empresa Inquilina, S.L." in response.text
    assert "Agua" in response.text
    assert "28,39" in response.text
    assert "Preparar solicitud" in response.text


def test_reembolsos_prepara_solicitud(app) -> None:

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)

        apunte = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=_categorias_gastos(),
            fecha=date(2026, 8, 13),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Agua",
            base=2839,
            tratamiento="REPERCUTIR",
        )

        session.add(apunte)
        session.commit()

        contrato_id = contrato.id
        apunte_id = apunte.id

    client = app.test_client()
    _seleccionar_base(client)

    response = client.post(
        f"/reembolsos/{contrato_id}/preparar",
        data={
            "origen": f"A:{apunte_id}",
        },
    )

    assert response.status_code == 200

    assert "Solicitud de reembolso" in response.text
    assert "LOCAL-A" in response.text
    assert "Empresa Inquilina, S.L." in response.text
    assert "Agua" in response.text

    assert response.text.count(
        "28,39"
    ) >= 2

    assert "Texto para el correo" in response.text
    assert "Marcar como enviado" in response.text


def test_reembolsos_rechaza_preparar_sin_gastos(app) -> None:

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)
        contrato_id = contrato.id

    client = app.test_client()
    _seleccionar_base(client)

    response = client.post(
        f"/reembolsos/{contrato_id}/preparar",
        data={},
    )

    assert response.status_code == 400
    assert (
        "Debe seleccionarse al menos un gasto."
        in response.text
    )


def test_reembolsos_revision_muestra_explicacion_del_prorrateo(app) -> None:

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(
            session,
            fecha_inicio=date(2026, 7, 1),
        )

        apunte = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=_categorias_gastos(),
            fecha=date(2026, 8, 13),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Agua. 01/06/2026 al 01/08/2026",
            base=2839,
            periodo_desde=date(2026, 6, 1),
            periodo_hasta=date(2026, 8, 1),
            criterio_periodo="EXCLUIR_HASTA",
            tratamiento="REPERCUTIR",
        )

        session.add(apunte)
        session.commit()

        contrato_id = contrato.id
        apunte_id = apunte.id

    client = app.test_client()
    _seleccionar_base(client)

    response = client.post(
        f"/reembolsos/{contrato_id}/preparar",
        data={
            "origen": f"A:{apunte_id}",
        },
    )

    assert response.status_code == 200

    # Tabla de revisión.
    assert "28,39" in response.text
    assert "14,43" in response.text

    # Explicación copiable.
    assert "31 de los 61 días" in response.text
    assert "28,39" in response.text
    assert "31" in response.text
    assert "61" in response.text
    assert "14,43" in response.text


def test_reembolsos_rechaza_origen_que_no_esta_pendiente(app) -> None:

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)
        contrato_id = contrato.id

    client = app.test_client()
    _seleccionar_base(client)

    response = client.post(
        f"/reembolsos/{contrato_id}/preparar",
        data={
            "origen": "A:999999",
        },
    )

    assert response.status_code == 400
    assert (
        "ya no está pendiente"
        in response.text
    )


def test_marcar_reembolso_como_enviado_persiste_todos_los_efectos(app) -> None:

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)

        apunte = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=_categorias_gastos(),
            fecha=date(2026, 8, 13),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Agua",
            base=2839,
            tratamiento="REPERCUTIR",
        )

        session.add(apunte)
        session.commit()

        contrato_id = contrato.id
        apunte_id = apunte.id

    client = app.test_client()
    _seleccionar_base(client)

    response = client.post(
        f"/reembolsos/{contrato_id}/enviar",
        data={
            "origen": f"A:{apunte_id}",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/reembolsos/"
    )

    with session_factory() as session:
        solicitud = session.scalar(
            select(SolicitudReembolso)
        )

        assert solicitud is not None
        assert solicitud.contrato_id == contrato_id
        assert solicitud.fecha_envio == date.today()
        assert solicitud.total == 2839

        assert len(solicitud.lineas) == 1

        linea = solicitud.lineas[0]

        assert linea.apunte_id == apunte_id
        assert linea.importe == 2839

        imputacion = session.scalar(
            select(ImputacionContrato)
        )

        assert imputacion is not None
        assert imputacion.apunte_id == apunte_id
        assert imputacion.contrato_id == contrato_id
        assert imputacion.importe == 2839

        movimiento = session.scalar(
            select(MovimientoPrevisto)
            .where(
                MovimientoPrevisto
                .solicitud_reembolso_id
                == solicitud.id
            )
        )

        assert movimiento is not None
        assert movimiento.naturaleza == "INGRESO"
        assert movimiento.importe_esperado == 2839
        assert movimiento.estado == "PENDIENTE"
        assert movimiento.apunte_id is None
        assert movimiento.contrato_id == contrato_id
        assert movimiento.fecha_prevista_desde is None
        assert movimiento.fecha_prevista_hasta is None
        assert (
            movimiento.contraparte
            == "Empresa Inquilina, S.L."
        )

        response = client.get(
            "/reembolsos/"
        )

        assert "Agua" not in response.text


def test_eliminar_solicitud_reembolso_restaura_gasto_pendiente(
    app,
) -> None:
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)

        apunte = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=_categorias_gastos(),
            fecha=date(2026, 8, 13),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Agua",
            base=2839,
            tratamiento="REPERCUTIR",
        )

        session.add(apunte)
        session.commit()

        contrato_id = contrato.id
        apunte_id = apunte.id

    client = app.test_client()
    _seleccionar_base(client)

    # El usuario prepara y marca la solicitud como enviada.
    response = client.post(
        f"/reembolsos/{contrato_id}/enviar",
        data={
            "origen": f"A:{apunte_id}",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        solicitud = session.scalar(
            select(SolicitudReembolso)
        )

        assert solicitud is not None
        solicitud_id = solicitud.id

        assert session.scalar(
            select(ImputacionContrato)
        ) is not None

        assert session.scalar(
            select(MovimientoPrevisto)
            .where(
                MovimientoPrevisto
                .solicitud_reembolso_id
                == solicitud_id
            )
        ) is not None

    # El usuario deshace la solicitud mientras el cobro sigue pendiente.
    response = client.post(
        f"/reembolsos/{solicitud_id}/eliminar"
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/reembolsos/"
    )

    with session_factory() as session:
        assert session.get(
            SolicitudReembolso,
            solicitud_id,
        ) is None

        assert session.scalar(
            select(SolicitudReembolsoLinea)
        ) is None

        assert session.scalar(
            select(ImputacionContrato)
        ) is None

        assert session.scalar(
            select(MovimientoPrevisto)
            .where(
                MovimientoPrevisto
                .solicitud_reembolso_id
                == solicitud_id
            )
        ) is None

    # El gasto vuelve a aparecer entre los pendientes.
    response = client.get(
        "/reembolsos/"
    )

    assert response.status_code == 200
    assert "Agua" in response.text
    assert "28,39" in response.text


def test_eliminar_solicitud_reembolso_rechaza_movimiento_conciliado(
    app,
) -> None:
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)

        apunte = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=_categorias_gastos(),
            fecha=date(2026, 8, 13),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Agua",
            base=2839,
            tratamiento="REPERCUTIR",
        )

        session.add(apunte)
        session.commit()

        contrato_id = contrato.id
        apunte_id = apunte.id

    client = app.test_client()
    _seleccionar_base(client)

    response = client.post(
        f"/reembolsos/{contrato_id}/enviar",
        data={
            "origen": f"A:{apunte_id}",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        solicitud = session.scalar(
            select(SolicitudReembolso)
        )

        assert solicitud is not None
        solicitud_id = solicitud.id

        movimiento = solicitud.movimiento_previsto

        assert movimiento is not None

        movimiento.estado = "CONCILIADO"
        session.commit()

    response = client.post(
        f"/reembolsos/{solicitud_id}/eliminar"
    )

    assert response.status_code == 400
    assert (
        "movimiento conciliado"
        in response.text
    )

    # Nada se ha eliminado.
    with session_factory() as session:
        solicitud = session.get(
            SolicitudReembolso,
            solicitud_id,
        )

        assert solicitud is not None
        assert len(solicitud.lineas) == 1

        assert session.scalar(
            select(ImputacionContrato)
        ) is not None

        movimiento = solicitud.movimiento_previsto

        assert movimiento is not None
        assert movimiento.estado == "CONCILIADO"


def test_reembolsos_muestra_solicitud_enviada_y_permite_eliminarla(
    app,
) -> None:
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)

        apunte = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=_categorias_gastos(),
            fecha=date(2026, 8, 13),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Agua",
            base=2839,
            tratamiento="REPERCUTIR",
        )

        session.add(apunte)
        session.commit()

        contrato_id = contrato.id
        apunte_id = apunte.id

    client = app.test_client()
    _seleccionar_base(client)

    client.post(
        f"/reembolsos/{contrato_id}/enviar",
        data={
            "origen": f"A:{apunte_id}",
        },
    )

    response = client.get(
        "/reembolsos/"
    )

    assert response.status_code == 200

    assert "Solicitudes enviadas" in response.text
    assert "LOCAL-A" in response.text
    assert "Empresa Inquilina, S.L." in response.text
    assert "28,39" in response.text
    assert "PENDIENTE" in response.text
    assert "Eliminar solicitud" in response.text


def test_reembolsos_no_ofrece_eliminar_solicitud_conciliada(
    app,
) -> None:
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)

        apunte = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=_categorias_gastos(),
            fecha=date(2026, 8, 13),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Agua",
            base=2839,
            tratamiento="REPERCUTIR",
        )

        session.add(apunte)
        session.commit()

        contrato_id = contrato.id
        apunte_id = apunte.id

    client = app.test_client()
    _seleccionar_base(client)

    client.post(
        f"/reembolsos/{contrato_id}/enviar",
        data={
            "origen": f"A:{apunte_id}",
        },
    )

    with session_factory() as session:
        solicitud = session.scalar(
            select(SolicitudReembolso)
        )

        solicitud.movimiento_previsto.estado = (
            "CONCILIADO"
        )

        session.commit()

    response = client.get(
        "/reembolsos/"
    )

    assert response.status_code == 200
    assert "CONCILIADO" not in response.text
    assert "Eliminar solicitud" not in response.text



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
    ApunteContable,
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

def _crear_apuntes_compensados(session) -> tuple[int, list[int]]:
    """Crea dos apuntes repercutibles cuyo saldo es cero."""

    contrato = _crear_contrato(session)
    categorias = _categorias_gastos()

    # El usuario registra un gasto repercutible de 100 €.
    gasto = crear_apunte_contable(
        inmueble=contrato.inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 1),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad octubre",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    # Posteriormente registra una devolución de 100 €.
    abono = crear_apunte_contable(
        inmueble=contrato.inmueble,
        categorias=categorias,
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Devolución comunidad",
        base=10000,
        importe_negativo=True,
        tratamiento="REPERCUTIR",
    )

    session.add_all([gasto, abono])
    session.commit()

    return contrato.id, [gasto.id, abono.id]



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


def test_reembolsos_pendientes_muestra_importes_negativos(app) -> None:
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)
        categorias = _categorias_gastos()

        # El usuario registra un gasto repercutible de 100 €.
        gasto = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=categorias,
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad octubre",
            base=10000,
            tratamiento="REPERCUTIR",
        )

        # También registra una devolución de 30,25 €.
        devolucion = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=categorias,
            fecha=date(2026, 10, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Devolución de comunidad",
            base=3025,
            importe_negativo=True,
            tratamiento="REPERCUTIR",
        )

        session.add_all([gasto, devolucion])
        session.commit()

    client = app.test_client()
    _seleccionar_base(client)

    # El usuario consulta los gastos pendientes de repercutir.
    response = client.get("/reembolsos/")

    assert response.status_code == 200

    # El gasto normal conserva su importe positivo.
    assert "Comunidad octubre" in response.text
    assert "100,00" in response.text

    # La devolución debe aparecer con signo negativo.
    assert "Devolución de comunidad" in response.text
    assert "-30,25" in response.text


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


@pytest.mark.parametrize(
    ("devolucion", "texto_esperado"),
    [
        (
            3000,
            "Total a abonar: 70,00 €.",
        ),
        (
            10000,
            "Los importes se compensan íntegramente. "
            "No queda ninguna cantidad pendiente de "
            "abonar o devolver.",
        ),
        (
            12000,
            "Total a tu favor: 20,00 €.",
        ),
    ],
)
def test_texto_solicitud_distingue_cobro_devolucion_y_compensacion(
    app,
    devolucion: int,
    texto_esperado: str,
) -> None:
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)
        categorias = _categorias_gastos()

        # El usuario registra un gasto repercutible de 100 €.
        gasto = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=categorias,
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad octubre",
            base=10000,
            tratamiento="REPERCUTIR",
        )

        # Registra una devolución que puede ser menor,
        # igual o mayor que el gasto original.
        abono = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=categorias,
            fecha=date(2026, 10, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Devolución comunidad",
            base=devolucion,
            importe_negativo=True,
            tratamiento="REPERCUTIR",
        )

        session.add_all([gasto, abono])
        session.commit()

        contrato_id = contrato.id
        gasto_id = gasto.id
        abono_id = abono.id

    client = app.test_client()
    _seleccionar_base(client)

    # El usuario selecciona ambos apuntes y prepara la solicitud.
    response = client.post(
        f"/reembolsos/{contrato_id}/preparar",
        data={
            "origen": [
                f"A:{gasto_id}",
                f"A:{abono_id}",
            ],
        },
    )

    assert response.status_code == 200

    # La revisión conserva el desglose de los dos conceptos.
    assert "Comunidad octubre" in response.text
    assert "Devolución comunidad" in response.text

    # El texto del correo explica quién debe pagar
    # o si ambos importes se compensan.
    assert texto_esperado in response.text


def test_texto_solicitud_no_duplica_periodo_del_concepto(
    app,
) -> None:
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)
        categorias = _categorias_gastos()

        # El usuario registra un gasto cuyo concepto ya incluye
        # el período al que corresponde.
        apunte = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=categorias,
            fecha=date(2026, 10, 31),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto=(
                "Comunidad octubre "
                "del 01/10/2026 al 31/10/2026"
            ),
            base=10000,
            periodo_desde=date(2026, 10, 1),
            periodo_hasta=date(2026, 10, 31),
            criterio_periodo="INCLUIR_AMBOS",
            tratamiento="REPERCUTIR",
        )

        session.add(apunte)
        session.commit()

        contrato_id = contrato.id
        apunte_id = apunte.id

    client = app.test_client()
    _seleccionar_base(client)

    # El usuario prepara una solicitud para este gasto.
    response = client.post(
        f"/reembolsos/{contrato_id}/preparar",
        data={
            "origen": f"A:{apunte_id}",
        },
    )

    assert response.status_code == 200

    # El texto para el correo utiliza el concepto original,
    # sin añadir otra vez el período.
    assert (
        "- Comunidad octubre del 01/10/2026 al 31/10/2026, "
        "de 100,00 €."
    ) in response.text

    # No debe aparecer la repetición del período.
    assert (
        "del 01/10/2026 al 31/10/2026, "
        "del 01/10/2026 al 31/10/2026"
    ) not in response.text


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


@pytest.mark.parametrize(
    ("importe_negativo", "texto_esperado", "calculo_esperado"),
    [
        (
            False,
            "Te corresponde abonar 31 de los 61 días",
            "28,39 × 31 / 61 = 14,43 €",
        ),
        (
            True,
            "Te corresponde una devolución por 31 de los 61 días",
            "-28,39 × 31 / 61 = -14,43 €",
        ),
    ],
)
def test_texto_reembolso_prorrateado_respeta_signo(
    app,
    importe_negativo: bool,
    texto_esperado: str,
    calculo_esperado: str,
) -> None:
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(
            session,
            fecha_inicio=date(2026, 7, 1),
        )

        # El usuario registra un gasto o una devolución
        # cuyo período empieza antes del contrato.
        apunte = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=_categorias_gastos(),
            fecha=date(2026, 8, 13),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Agua. 01/06/2026 al 01/08/2026",
            base=2839,
            importe_negativo=importe_negativo,
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

    # El usuario prepara la solicitud y consulta
    # la explicación que copiará al correo.
    response = client.post(
        f"/reembolsos/{contrato_id}/preparar",
        data={
            "origen": f"A:{apunte_id}",
        },
    )

    assert response.status_code == 200

    assert texto_esperado in response.text
    assert calculo_esperado in response.text

    if importe_negativo:
        # Una devolución no debe describirse como
        # una cantidad que el inquilino debe abonar.
        assert (
            "Te corresponde abonar"
            not in response.text
        )


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


@pytest.mark.parametrize(
    ("devolucion", "saldo", "naturaleza_prevista"),
    [
        (10000, 0, None),
        (12000, -2000, "GASTO"),
    ],
)
def test_marcar_reembolso_negativo_como_enviado(
    app,
    devolucion: int,
    saldo: int,
    naturaleza_prevista: str | None,
) -> None:
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato = _crear_contrato(session)
        categorias = _categorias_gastos()

        # El usuario registra un gasto repercutible de 100 €.
        gasto = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=categorias,
            fecha=date(2026, 10, 1),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Comunidad octubre",
            base=10000,
            tratamiento="REPERCUTIR",
        )

        # Posteriormente registra una devolución repercutible.
        abono = crear_apunte_contable(
            inmueble=contrato.inmueble,
            categorias=categorias,
            fecha=date(2026, 10, 15),
            naturaleza="GASTO",
            categoria="GAS_COMUNIDAD",
            concepto="Devolución comunidad",
            base=devolucion,
            importe_negativo=True,
            tratamiento="REPERCUTIR",
        )

        session.add_all([gasto, abono])
        session.commit()

        contrato_id = contrato.id
        gasto_id = gasto.id
        abono_id = abono.id

    client = app.test_client()
    _seleccionar_base(client)

    # El usuario selecciona ambos apuntes y marca
    # la solicitud como enviada.
    response = client.post(
        f"/reembolsos/{contrato_id}/enviar",
        data={
            "origen": [
                f"A:{gasto_id}",
                f"A:{abono_id}",
            ],
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
        assert solicitud.total == saldo
        assert len(solicitud.lineas) == 2

        # Las líneas persistidas mantienen importes positivos.
        importes = {
            linea.apunte_id: linea.importe
            for linea in solicitud.lineas
        }

        assert importes == {
            gasto_id: 10000,
            abono_id: devolucion,
        }

        # Los dos apuntes tienen sus imputaciones registradas.
        imputaciones = session.scalars(
            select(ImputacionContrato).where(
                ImputacionContrato.contrato_id == contrato_id
            )
        ).all()

        assert len(imputaciones) == 2

        if saldo == 0:
            # No hay movimiento bancario que conciliar.
            assert solicitud.movimiento_previsto is None
        else:
            # El saldo negativo genera un pago previsto.
            movimiento = solicitud.movimiento_previsto

            assert movimiento is not None
            assert movimiento.naturaleza == naturaleza_prevista
            assert movimiento.importe_esperado == abs(saldo)
            assert movimiento.estado == "PENDIENTE"

    # Los apuntes ya registrados no vuelven a aparecer
    # como pendientes de repercutir.
    response = client.get("/reembolsos/")

    assert response.status_code == 200
    assert "No hay gastos pendientes de repercutir." in response.text


def test_reembolsos_lista_solicitud_con_saldo_cero(app) -> None:
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato_id, apunte_ids = (
            _crear_apuntes_compensados(session)
        )

    client = app.test_client()
    _seleccionar_base(client)

    # El usuario confirma una solicitud cuyos importes se compensan.
    response = client.post(
        f"/reembolsos/{contrato_id}/enviar",
        data={
            "origen": [
                f"A:{apunte_id}"
                for apunte_id in apunte_ids
            ],
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        solicitud = session.scalar(
            select(SolicitudReembolso)
        )

        assert solicitud is not None
        assert solicitud.total == 0
        assert solicitud.movimiento_previsto is None

        solicitud_id = solicitud.id

    # El usuario consulta las solicitudes enviadas.
    response = client.get("/reembolsos/")

    assert response.status_code == 200

    # La compensación debe aparecer aunque no exista previsto.
    assert "Solicitudes enviadas" in response.text
    assert "0,00" in response.text
    assert "Sin movimiento" in response.text

    # Debe ofrecer la posibilidad de deshacerla.
    assert (
        f"/reembolsos/{solicitud_id}/eliminar"
        in response.text
    )
    assert "Eliminar solicitud" in response.text


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


def test_eliminar_solicitud_saldo_cero_restaura_pendientes(
    app,
) -> None:
    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        contrato_id, apunte_ids = (
            _crear_apuntes_compensados(session)
        )

    client = app.test_client()
    _seleccionar_base(client)

    # El usuario confirma la compensación de ambos apuntes.
    response = client.post(
        f"/reembolsos/{contrato_id}/enviar",
        data={
            "origen": [
                f"A:{apunte_id}"
                for apunte_id in apunte_ids
            ],
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        solicitud = session.scalar(
            select(SolicitudReembolso)
        )

        assert solicitud is not None
        assert solicitud.total == 0

        solicitud_id = solicitud.id

        # Ambos apuntes tienen imputaciones persistidas.
        imputaciones = session.scalars(
            select(ImputacionContrato).where(
                ImputacionContrato.contrato_id
                == contrato_id
            )
        ).all()

        assert len(imputaciones) == 2

    # El usuario elimina la solicitud de saldo cero.
    response = client.post(
        f"/reembolsos/{solicitud_id}/eliminar"
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/reembolsos/"
    )

    with session_factory() as session:
        # La solicitud y sus líneas han desaparecido.
        assert session.get(
            SolicitudReembolso,
            solicitud_id,
        ) is None

        assert session.scalars(
            select(SolicitudReembolsoLinea)
        ).all() == []

        # También desaparecen las imputaciones.
        assert session.scalars(
            select(ImputacionContrato)
        ).all() == []

        # Los apuntes contables originales se conservan.
        apuntes = session.scalars(
            select(ApunteContable).where(
                ApunteContable.id.in_(apunte_ids)
            )
        ).all()

        assert len(apuntes) == 2

    # Los dos apuntes vuelven a aparecer pendientes de repercutir.
    response = client.get("/reembolsos/")

    assert response.status_code == 200
    assert "Comunidad octubre" in response.text
    assert "Devolución comunidad" in response.text


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



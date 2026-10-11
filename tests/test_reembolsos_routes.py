"""Pruebas de las rutas web del módulo de reembolsos."""

from datetime import date

from contab.app import create_app
from contab.config import CategoriaContable
from contab.contabilidad.services import (
    crear_apunte_contable,
)
from contab.database import Base
from contab.models import (
    Contrato,
    ContratoInquilino,
    Inmueble,
    Inquilino,
)


def crear_app_test():
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

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

    return app


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


def test_reembolsos_muestra_gastos_pendientes() -> None:
    app = crear_app_test()

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


def test_reembolsos_prepara_solicitud() -> None:
    app = crear_app_test()

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


def test_reembolsos_rechaza_preparar_sin_gastos() -> None:
    app = crear_app_test()

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


def test_reembolsos_revision_muestra_explicacion_del_prorrateo() -> None:
    app = crear_app_test()

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


def test_reembolsos_rechaza_origen_que_no_esta_pendiente() -> None:
    app = crear_app_test()

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



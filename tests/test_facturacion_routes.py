"""Pruebas de las rutas web del módulo de facturación."""

from datetime import date

from sqlalchemy import select

from contab.app import create_app
from contab.database import Base
from contab.models import (
    ApunteContable,
    Contrato,
    ContratoInquilino,
    Factura,
    Inmueble,
    Inquilino,
    MovimientoPrevisto,
    RentaContrato,
)


def crear_app_test():
    """Crea una aplicación de facturación aislada para las pruebas."""

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


def test_emitir_factura_persiste_operacion_completa(
    tmp_path,
    monkeypatch,
) -> None:
    """Emite factura, apunte y cobro previsto en una sola operación."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
ING_ALQUILERES = INGRESO | Alquileres

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
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
            fecha_inicio=date(2026, 1, 15),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 2, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
        )

        inquilino = Inquilino(
            nombre="Ana Pérez",
            nif="11111111A",
        )

        contrato.titulares.append(
            ContratoInquilino(
                inquilino=inquilino,
                orden=1,
            )
        )

        contrato.rentas.append(
            RentaContrato(
                fecha_desde=contrato.fecha_inicio,
                importe=100000,
            )
        )

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario confirma la emisión de la factura preparada.
    response = client.post(
        f"/facturacion/emitir/{contrato_id}",
        data={
            "periodo": "2026-10-01",
            "fecha_emision": "2026-10-01",
        },
    )

    assert response.status_code == 302

    with session_factory() as session:
        factura = session.scalar(
            select(Factura)
        )
        apunte = session.scalar(
            select(ApunteContable)
        )
        movimiento = session.scalar(
            select(MovimientoPrevisto)
        )

        assert factura is not None
        assert factura.contrato_id == contrato_id
        assert factura.periodo == date(2026, 10, 1)
        assert factura.estado == "EMITIDA"
        assert factura.total == 102000

        assert apunte is not None
        assert apunte.referencia_documento == (
            factura.numero_factura
        )
        assert apunte.categoria == "ING_ALQUILERES"
        assert apunte.total == factura.total

        assert movimiento is not None
        assert movimiento.apunte_id == apunte.id
        assert movimiento.contrato_id == contrato_id
        assert movimiento.importe_esperado == factura.total
        assert movimiento.estado == "PENDIENTE"


def test_emitir_factura_no_persiste_nada_si_falla(
    tmp_path,
    monkeypatch,
) -> None:
    """No deja datos parciales cuando falla la emisión."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
ING_ALQUILERES = INGRESO | Alquileres

[subcategorias_contables]
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "CONTAB_CONFIG",
        str(ruta),
    )

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
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
            fecha_inicio=date(2026, 1, 15),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 2, 1),
            fianza=100000,
            direccion_facturacion="Dirección",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
        )

        contrato.rentas.append(
            RentaContrato(
                fecha_desde=contrato.fecha_inicio,
                importe=100000,
            )
        )

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # La emisión falla porque el contrato no tiene titular.
    response = client.post(
        f"/facturacion/emitir/{contrato_id}",
        data={
            "periodo": "2026-10-01",
            "fecha_emision": "2026-10-01",
        },
    )

    assert response.status_code == 400

    with session_factory() as session:
        assert session.scalar(
            select(Factura)
        ) is None

        assert session.scalar(
            select(ApunteContable)
        ) is None

        assert session.scalar(
            select(MovimientoPrevisto)
        ) is None



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
    RevisionRenta,
)
from contab.facturacion.routes import (
    _valores_iniciales_facturacion,
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
            "periodo": "10-2026",
            "fecha_emision": "01-10-2026",
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


def test_listar_facturacion_muestra_datos_del_periodo() -> None:
    """Muestra los ingresos preparados de un período sin modificarlos."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        inmueble_local = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local comercial",
            direccion="Dirección del local",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        contrato_local = Contrato(
            inmueble=inmueble_local,
            fecha_inicio=date(2026, 1, 15),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 2, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Calle Facturación 1",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler local",
        )

        contrato_local.titulares.append(
            ContratoInquilino(
                inquilino=Inquilino(
                    nombre="Ana Pérez",
                    nif="11111111A",
                ),
                orden=1,
            )
        )

        contrato_local.rentas.append(
            RentaContrato(
                fecha_desde=contrato_local.fecha_inicio,
                importe=100000,
            )
        )

        inmueble_otro = Inmueble(
            referencia="PISO-1",
            tipo="P",
            codigo_facturacion="B1",
            descripcion="Vivienda",
            direccion="Dirección del piso",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        contrato_otro = Contrato(
            inmueble=inmueble_otro,
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=False,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=80000,
            direccion_facturacion="Dirección",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler vivienda",
        )

        contrato_otro.rentas.append(
            RentaContrato(
                fecha_desde=contrato_otro.fecha_inicio,
                importe=80000,
            )
        )

        contrato_otro.titulares.append(
            ContratoInquilino(
                inquilino=Inquilino(
                    nombre="Luis García",
                    nif="22222222B",
                ),
                orden=1,
            )
        )

        session.add_all([
            contrato_local,
            contrato_otro,
        ])
        session.commit()

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario consulta la preparación de octubre.
    response = client.get(
        "/facturacion/"
        "?periodo=10-2026"
        "&fecha_emision=01-10-2026"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert 'value="10-2026"' in texto
    assert 'value="01-10-2026"' in texto

    assert "Locales" in texto
    assert "LOCAL-1" in texto
    assert "Ana Pérez" in texto
    assert "11111111A" in texto
    assert "Calle Facturación 1" in texto
    assert "36001" in texto
    assert "1.000,00" in texto
    assert "210,00" in texto
    assert "190,00" in texto
    assert "1.020,00" in texto
    assert "Emitir" in texto

    assert "Otros" in texto
    assert "PISO-1" in texto
    assert "Luis García" in texto
    assert "800,00" in texto
    assert "Contabilizar" in texto


def test_listar_facturacion_respeta_fecha_emision(
    monkeypatch,
) -> None:
    """Prepara la facturación con la fecha de emisión indicada."""

    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    fecha_recibida = None

    def preparar_periodo_facturacion_falso(
        *,
        contratos,
        periodo,
        fecha_emision,
    ):
        nonlocal fecha_recibida
        fecha_recibida = fecha_emision

        class Preparacion:
            locales = []
            otros = []

        return Preparacion()

    monkeypatch.setattr(
        "contab.facturacion.routes.preparar_periodo_facturacion",
        preparar_periodo_facturacion_falso,
    )

    # El usuario prepara octubre con una fecha de emisión
    # distinta del primer día del período.
    response = client.get(
        "/facturacion/"
        "?periodo=10-2026"
        "&fecha_emision=15-10-2026"
    )

    assert response.status_code == 200
    assert fecha_recibida == date(2026, 10, 15)


def test_valores_iniciales_facturacion_proponen_mes_siguiente() -> None:
    """Propone el mes siguiente y su primer día."""

    periodo, fecha_emision = _valores_iniciales_facturacion(
        date(2026, 9, 29)
    )

    assert periodo == date(2026, 10, 1)
    assert fecha_emision == date(2026, 10, 1)


def test_valores_iniciales_facturacion_cambian_de_anio() -> None:
    """Propone enero del año siguiente al preparar en diciembre."""

    periodo, fecha_emision = _valores_iniciales_facturacion(
        date(2026, 12, 31)
    )

    assert periodo == date(2027, 1, 1)
    assert fecha_emision == date(2027, 1, 1)


def test_listar_facturacion_rechaza_periodo_invalido() -> None:
    """Rechaza un período con formato inválido."""

    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/facturacion/"
        "?periodo=2026-10"
        "&fecha_emision=01-10-2026"
    )

    texto = response.get_data(as_text=True)

    assert response.status_code == 400
    assert "El período no es válido" in texto
    assert 'value="2026-10"' in texto
    assert 'value="01-10-2026"' in texto


def test_listar_facturacion_rechaza_fecha_emision_invalida() -> None:
    """Rechaza una fecha de emisión inválida."""

    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/facturacion/"
        "?periodo=10-2026"
        "&fecha_emision=30-02-2026"
    )

    texto = response.get_data(as_text=True)

    assert response.status_code == 400
    assert "La fecha indicada no es válida" in texto
    assert 'value="10-2026"' in texto
    assert 'value="30-02-2026"' in texto


def test_emitir_factura_desde_lista_conserva_aviso_revision(
    tmp_path,
    monkeypatch,
) -> None:
    """Emite desde la lista y conserva el aviso de revisión."""

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

        contrato.titulares.append(
            ContratoInquilino(
                inquilino=Inquilino(
                    nombre="Ana Pérez",
                    nif="11111111A",
                ),
                orden=1,
            )
        )

        contrato.rentas.append(
            RentaContrato(
                fecha_desde=contrato.fecha_inicio,
                importe=100000,
            )
        )

        revision = RevisionRenta(
            contrato=contrato,
            fecha_prevista=date(2026, 11, 1),
            metodo="IPC_NACIONAL",
            estado="PENDIENTE",
        )

        session.add(contrato)
        session.add(revision)
        session.commit()

        contrato_id = contrato.id
        revision_id = revision.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario emite desde la preparación de octubre.
    response = client.post(
        f"/facturacion/emitir/{contrato_id}",
        data={
            "periodo": "10-2026",
            "fecha_emision": "01-10-2026",
        },
    )

    assert response.status_code == 302
    assert (
        response.headers["Location"]
        == "/facturacion/"
        "?periodo=10-2026"
        "&fecha_emision=01-10-2026"
    )

    with session_factory() as session:
        factura = session.scalar(
            select(Factura)
        )

        assert factura is not None
        assert factura.revision_renta_id == revision_id
        assert factura.aviso_revision == "AVISO"


def test_contabilizar_ingreso_sin_factura_persiste_operacion_completa(
    tmp_path,
    monkeypatch,
) -> None:
    """Contabiliza un alquiler sin factura y vuelve al mismo período."""

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
            referencia="PISO-1",
            tipo="P",
            codigo_facturacion="B1",
            descripcion="Vivienda",
            direccion="Dirección del piso",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )

        contrato = Contrato(
            inmueble=inmueble,
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=False,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=80000,
            direccion_facturacion="Dirección",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler vivienda",
        )

        contrato.titulares.append(
            ContratoInquilino(
                inquilino=Inquilino(
                    nombre="Luis García",
                    nif="22222222B",
                ),
                orden=1,
            )
        )

        contrato.rentas.append(
            RentaContrato(
                fecha_desde=contrato.fecha_inicio,
                importe=80000,
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

    # El usuario contabiliza el ingreso desde la preparación de octubre.
    response = client.post(
        f"/facturacion/contabilizar/{contrato_id}",
        data={
            "periodo": "10-2026",
            "fecha_emision": "01-10-2026",
        },
    )

    assert response.status_code == 302
    assert (
        response.headers["Location"]
        == "/facturacion/"
        "?periodo=10-2026"
        "&fecha_emision=01-10-2026"
    )

    with session_factory() as session:
        assert session.scalar(
            select(Factura)
        ) is None

        apunte = session.scalar(
            select(ApunteContable)
        )
        movimiento = session.scalar(
            select(MovimientoPrevisto)
        )

        assert apunte is not None
        assert apunte.categoria == "ING_ALQUILERES"
        assert apunte.periodo_desde == date(2026, 10, 1)
        assert apunte.periodo_hasta == date(2026, 10, 31)
        assert apunte.total == 80000
        assert apunte.tercero_nombre == "Luis García"
        assert apunte.tercero_nif == "22222222B"

        assert movimiento is not None
        assert movimiento.apunte_id == apunte.id
        assert movimiento.contrato_id == contrato_id
        assert movimiento.importe_esperado == 80000
        assert movimiento.estado == "PENDIENTE"



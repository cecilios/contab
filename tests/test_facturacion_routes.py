"""Pruebas de las rutas web del módulo de facturación."""

from datetime import date
from types import SimpleNamespace

from sqlalchemy import select

from contab.app import create_app
from contab.database import Base
from contab.models import (
    ApunteContable,
    Contrato,
    ContratoInquilino,
    Factura,
    FacturaDestinatario,
    FacturaLinea,
    Inmueble,
    Inquilino,
    MovimientoPrevisto,
    RentaContrato,
    RevisionRenta,
)
from contab.facturacion.routes import (
    _valores_iniciales_facturacion,
)

from contab.facturacion.services import (
    siguiente_numero_factura,
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


def _crear_factura_emitida_para_test(
    session,
    *,
    referencia: str = "LOCAL-1",
    codigo_facturacion: str = "A1",
    numero_secuencia: int = 1,
    anio: int = 2026,
    mes: int = 10,
    destinatario: str = "Ana Pérez",
    nif: str = "11111111A",
) -> Factura:
    """Crea una factura persistida para probar su consulta."""

    inmueble = Inmueble(
        referencia=referencia,
        tipo="L",
        codigo_facturacion=codigo_facturacion,
        descripcion=f"Local {referencia}",
        direccion="Dirección del local",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2025, 1, 1),
        fecha_vencimiento=date(2030, 12, 31),
        genera_factura=True,
        fecha_inicio_facturacion=date(2025, 1, 1),
        fianza=100000,
        iva_porcentaje=2100,
        retencion_porcentaje=1900,
        direccion_facturacion="Calle del Cliente 10",
        codigo_postal_facturacion="36001",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler local",
    )

    contrato.titulares.append(
        ContratoInquilino(
            inquilino=Inquilino(
                nombre=destinatario,
                nif=nif,
            ),
            orden=1,
        )
    )

    numero_factura = (
        f"{numero_secuencia:02d}/"
        f"{anio}{codigo_facturacion}"
    )

    factura = Factura(
        contrato=contrato,
        numero_secuencia=numero_secuencia,
        anio=anio,
        numero_factura=numero_factura,
        fecha_emision=date(anio, mes, 1),
        periodo=date(anio, mes, 1),
        referencia_inmueble=inmueble.referencia,
        descripcion_inmueble=inmueble.descripcion,
        direccion_facturacion=contrato.direccion_facturacion,
        codigo_postal_facturacion=contrato.codigo_postal_facturacion,
        poblacion_facturacion=contrato.poblacion_facturacion,
        provincia_facturacion=contrato.provincia_facturacion,
        base=103500,
        iva_porcentaje=2100,
        iva_importe=21735,
        retencion_porcentaje=1900,
        retencion_importe=19665,
        total=105570,
        estado="EMITIDA",
        notas="Factura de prueba.",
    )

    factura.destinatarios.append(
        FacturaDestinatario(
            orden=1,
            nombre=destinatario,
            nif=nif,
        )
    )

    factura.lineas.extend(
        [
            FacturaLinea(
                orden=1,
                concepto="Alquiler local",
                importe=100000,
            ),
            FacturaLinea(
                orden=2,
                concepto="Consumo de agua",
                importe=3500,
            ),
        ]
    )

    session.add(factura)
    session.commit()

    return factura


def _anadir_registro_contable_factura_para_test(
    session,
    factura: Factura,
) -> tuple[ApunteContable, MovimientoPrevisto]:
    """Añade apunte y movimiento previsto asociados a una factura."""

    apunte = ApunteContable(
        inmueble=factura.contrato.inmueble,
        fecha=factura.fecha_emision,
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        tratamiento="CONTABILIZAR",
        concepto="Alquiler local",
        periodo_desde=factura.periodo,
        periodo_hasta=date(2026, 10, 31),
        base=factura.base,
        iva_importe=factura.iva_importe,
        retencion_importe=factura.retencion_importe,
        total=factura.total,
        tercero_nombre="Ana Pérez",
        tercero_nif="11111111A",
        referencia_documento=factura.numero_factura,
    )

    movimiento = MovimientoPrevisto(
        inmueble=factura.contrato.inmueble,
        contrato=factura.contrato,
        apunte=apunte,
        fecha_prevista_desde=factura.periodo,
        fecha_prevista_hasta=date(2026, 10, 31),
        naturaleza="INGRESO",
        concepto="Alquiler local",
        importe_esperado=factura.total,
        contraparte="Ana Pérez",
        estado="PENDIENTE",
    )

    factura.apunte_contable = apunte

    session.add_all([apunte, movimiento])
    session.commit()

    return apunte, movimiento



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
        "/facturacion/?periodo=10/2026"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert 'value="10/2026"' in texto
    assert 'value="01/10/2026"' in texto

    assert "Locales" in texto
    assert "LOCAL-1" in texto
    assert "Ana Pérez" in texto
    assert "1.000,00" in texto
    assert "210,00" in texto
    assert "190,00" in texto
    assert "1.020,00" in texto

    assert "Otros" in texto
    assert "PISO-1" in texto
    assert "Luis García" in texto
    assert "800,00" in texto
    assert "Contabilizar" in texto


def test_listar_facturacion_inicializa_fecha_emision_desde_periodo(
    monkeypatch,
) -> None:
    """Inicializa la fecha de emisión con el primer día del período."""

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

        return SimpleNamespace(
            periodo=periodo,
            locales=[],
            otros=[],
        )

    monkeypatch.setattr(
        "contab.facturacion.routes.preparar_periodo_facturacion",
        preparar_periodo_facturacion_falso,
    )

    response = client.get(
        "/facturacion/?periodo=10/2026"
    )

    assert response.status_code == 200
    assert fecha_recibida == date(2026, 10, 1)

    texto = response.get_data(as_text=True)

    assert 'value="10/2026"' in texto
    assert 'value="01/10/2026"' in texto


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
        "/facturacion/?periodo=2026-10"
    )

    texto = response.get_data(as_text=True)

    assert response.status_code == 400
    assert "El período no es válido" in texto
    assert 'value="2026-10"' in texto


def test_contabilizar_factura_conserva_aviso_revision(
    tmp_path,
    monkeypatch,
) -> None:
    """Contabiliza la factura y conserva el aviso de revisión."""

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
            iva_porcentaje=0,
            retencion_porcentaje=0,
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

    # El usuario contabiliza la factura previsualizada de octubre.
    response = client.post(
        f"/facturacion/facturas/{contrato_id}/contabilizar",
        data={
            "periodo": "10/2026",
            "fecha_emision": "01/10/2026",
            "linea_concepto": [
                "Alquiler",
            ],
            "linea_importe": [
                "1000,00",
            ],
            "iva_porcentaje": "0",
            "retencion_porcentaje": "0",
            "nota_texto": [],
            "base_previsualizada": "100000",
            "iva_previsualizado": "0",
            "retencion_previsualizada": "0",
            "total_previsualizado": "100000",
        },
    )

    assert response.status_code == 302
    assert (
        response.headers["Location"]
        == "/facturacion/"
        "?periodo=10/2026"
        "&fecha_emision=01/10/2026"
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
            "periodo": "10/2026",
            "fecha_emision": "01/10/2026",
        },
    )

    assert response.status_code == 302
    assert (
        response.headers["Location"]
        == "/facturacion/"
        "?periodo=10/2026"
        "&fecha_emision=01/10/2026"
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


def test_listar_facturacion_bloquea_revision_pendiente(
    tmp_path,
    monkeypatch,
) -> None:
    """Comprueba que impide emitir si la revisión está pendiente."""

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
            fecha_prevista=date(2026, 10, 1),
            metodo="IPC_NACIONAL",
            estado="PENDIENTE",
        )

        session.add(contrato)
        session.add(revision)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario prepara noviembre con la revisión de octubre todavía pendiente.
    response = client.get(
        "/facturacion/"
        "?periodo=11/2026"
        "&fecha_emision=01/11/2026"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "Pendiente" in texto
    assert "Resolver revisión" in texto
    assert "Previsualizar" not in texto


def test_contabilizar_factura_rechaza_revision_pendiente(
    tmp_path,
    monkeypatch,
) -> None:
    """Impide contabilizar si la revisión está pendiente."""

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
            iva_porcentaje=0,
            retencion_porcentaje=0,
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
            fecha_prevista=date(2026, 10, 1),
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

    response = client.post(
        f"/facturacion/facturas/{contrato_id}/contabilizar",
        data={
            "periodo": "11/2026",
            "fecha_emision": "01/11/2026",
            "linea_concepto": [
                "Alquiler",
            ],
            "linea_importe": [
                "1000,00",
            ],
            "iva_porcentaje": "0",
            "retencion_porcentaje": "0",
            "nota_texto": [],
            "base_previsualizada": "100000",
            "iva_previsualizado": "0",
            "retencion_previsualizada": "0",
            "total_previsualizado": "100000",
        },
    )

    assert response.status_code == 400
    assert (
        "La factura no puede contabilizarse hasta "
        "resolver la revisión de renta pendiente."
        in response.get_data(as_text=True)
    )

    with session_factory() as session:
        revision = session.get(
            RevisionRenta,
            revision_id,
        )

        assert revision is not None
        assert revision.estado == "PENDIENTE"

        assert session.scalar(select(Factura)) is None
        assert session.scalar(select(ApunteContable)) is None
        assert session.scalar(select(MovimientoPrevisto)) is None


def test_resolver_revision_muestra_formulario() -> None:
    """Muestra el formulario para resolver una revisión pendiente."""

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
            fecha_prevista=date(2026, 10, 1),
            metodo="IPC_NACIONAL",
            estado="PENDIENTE",
        )

        session.add(contrato)
        session.add(revision)
        session.commit()

        revision_id = revision.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario abre la revisión pendiente desde
    # la preparación de noviembre.
    response = client.get(
        f"/facturacion/revisiones/{revision_id}/resolver"
        "?periodo=11-2026"
        "&fecha_emision=01/11/2026"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "Revisión de renta" in texto
    assert "LOCAL-1" in texto
    assert "IPC_NACIONAL" in texto
    assert "01/10/2026" in texto
    assert "1.000,00" in texto
    assert "Índice aplicable (%)" in texto
    assert "Aplicar revisión" in texto
    assert "Cancelar" in texto
    assert (
        "/facturacion/"
        "?periodo=11-2026"
        "&amp;fecha_emision=01/11/2026"
        in texto
    )


def test_aplicar_revision_actualiza_renta_y_facturacion() -> None:
    """Aplica una revisión pendiente y usa la nueva renta al facturar."""

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
            iva_porcentaje=0,
            retencion_porcentaje=0,
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
            fecha_prevista=date(2026, 10, 1),
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

    # El usuario aplica un IPC del 2,5 % a la revisión pendiente.
    response = client.post(
        f"/facturacion/revisiones/{revision_id}/resolver"
        "?periodo=11/2026"
        "&fecha_emision=01/11/2026",
        data={
            "porcentaje": "2,5",
        },
    )

    assert response.status_code == 302
    assert (
        response.headers["Location"]
        .endswith(
            "/facturacion/"
            "?periodo=11/2026"
            "&fecha_emision=01/11/2026"
        )
    )

    # La revisión queda aplicada, se crea la nueva renta
    # y se prepara la revisión del año siguiente.
    with session_factory() as session:
        revision = session.get(
            RevisionRenta,
            revision_id,
        )

        assert revision.estado == "APLICADA"
        assert revision.porcentaje_aplicado == 250
        assert revision.fecha_resolucion is not None

        contrato = session.get(
            Contrato,
            contrato_id,
        )

        rentas = sorted(
            contrato.rentas,
            key=lambda renta: renta.fecha_desde,
        )

        assert len(rentas) == 2
        assert rentas[-1].fecha_desde == date(2026, 10, 1)
        assert rentas[-1].importe == 102500

        revisiones = sorted(
            contrato.revisiones_renta,
            key=lambda revision: revision.fecha_prevista,
        )

        assert len(revisiones) == 2

        siguiente_revision = revisiones[-1]

        assert siguiente_revision.fecha_prevista == date(
            2027,
            10,
            1,
        )
        assert siguiente_revision.metodo == "IPC_NACIONAL"
        assert siguiente_revision.estado == "PENDIENTE"

    # Al volver a preparar noviembre, Contab usa ya la nueva
    # renta y la factura deja de estar bloqueada.
    response = client.get(
        "/facturacion/"
        "?periodo=11/2026"
        "&fecha_emision=01/11/2026"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "1.025,00" in texto
    assert "Pendiente de revisión" not in texto
    assert "Resolver revisión" not in texto


def test_aplicar_revision_rechaza_porcentaje_invalido() -> None:
    """No modifica la revisión si el porcentaje no es válido."""

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
            iva_porcentaje=0,
            retencion_porcentaje=0,
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

        revision = RevisionRenta(
            contrato=contrato,
            fecha_prevista=date(2026, 10, 1),
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

    # El usuario introduce un porcentaje que no puede interpretarse.
    response = client.post(
        f"/facturacion/revisiones/{revision_id}/resolver"
        "?periodo=11/2026"
        "&fecha_emision=01/11/2026",
        data={
            "porcentaje": "dos y medio",
        },
    )

    assert response.status_code == 400

    # El error no debe haber modificado ni la revisión ni la renta.
    with session_factory() as session:
        revision = session.get(
            RevisionRenta,
            revision_id,
        )
        contrato = session.get(
            Contrato,
            contrato_id,
        )

        assert revision.estado == "PENDIENTE"
        assert revision.porcentaje_aplicado is None
        assert revision.fecha_resolucion is None

        assert len(contrato.rentas) == 1
        assert len(contrato.revisiones_renta) == 1


def test_aplicar_revision_rechaza_revision_resuelta() -> None:
    """No permite aplicar otra vez una revisión ya resuelta."""

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
            iva_porcentaje=0,
            retencion_porcentaje=0,
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

        revision = RevisionRenta(
            contrato=contrato,
            fecha_prevista=date(2026, 10, 1),
            metodo="IPC_NACIONAL",
            estado="APLICADA",
            porcentaje_aplicado=250,
            fecha_resolucion=date(2026, 10, 15),
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

    # El usuario intenta aplicar de nuevo una revisión ya resuelta.
    response = client.post(
        f"/facturacion/revisiones/{revision_id}/resolver"
        "?periodo=11/2026"
        "&fecha_emision=01/11/2026",
        data={
            "porcentaje": "3,0",
        },
    )

    assert response.status_code == 400

    with session_factory() as session:
        revision = session.get(
            RevisionRenta,
            revision_id,
        )
        contrato = session.get(
            Contrato,
            contrato_id,
        )

        assert revision.estado == "APLICADA"
        assert revision.porcentaje_aplicado == 250
        assert revision.fecha_resolucion == date(2026, 10, 15)

        assert len(contrato.rentas) == 1
        assert len(contrato.revisiones_renta) == 1


def test_aplicar_revision_rechaza_metodo_fijo() -> None:
    """No interpreta una revisión FIJO como revisión porcentual."""

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
            iva_porcentaje=0,
            retencion_porcentaje=0,
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

        revision = RevisionRenta(
            contrato=contrato,
            fecha_prevista=date(2026, 10, 1),
            metodo="FIJO",
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

    # FIJO todavía no tiene una semántica definida:
    # no debe tratarse como un porcentaje.
    response = client.post(
        f"/facturacion/revisiones/{revision_id}/resolver"
        "?periodo=11/2026"
        "&fecha_emision=01/11/2026",
        data={
            "porcentaje": "2,5",
        },
    )

    assert response.status_code == 400
    assert "FIJO" in response.get_data(as_text=True)

    with session_factory() as session:
        revision = session.get(
            RevisionRenta,
            revision_id,
        )
        contrato = session.get(
            Contrato,
            contrato_id,
        )

        assert revision.estado == "PENDIENTE"
        assert revision.porcentaje_aplicado is None
        assert revision.fecha_resolucion is None

        assert len(contrato.rentas) == 1
        assert len(contrato.revisiones_renta) == 1


def test_listar_facturacion_ofrece_modificar_factura() -> None:
    """Permite abrir la modificación de una factura pendiente."""

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
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Calle del Cliente 10",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler local",
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

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario prepara la facturación mensual.
    response = client.get(
        "/facturacion/"
        "?periodo=10/2026"
        "&fecha_emision=01/10/2026"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "Modificar" in texto
    assert (
        f"/facturacion/facturas/{contrato_id}/modificar"
        "?periodo=10/2026"
        in texto
    )


def test_modificar_factura_muestra_propuesta_sin_persistir(
    tmp_path,
) -> None:
    """Muestra una factura preparada sin guardarla en la base de datos."""

    ruta_db = tmp_path / "test.db"
    ruta_plantilla = tmp_path / "test-factura.html"

    ruta_plantilla.write_text(
        """
        <!doctype html>
        <html>
        <body>
            {% for linea in factura.lineas %}
                <p>
                    {{ linea.concepto }}:
                    {{ importe_a_texto(linea.importe) }}
                </p>
            {% endfor %}

            <p>
                Total:
                {{ importe_a_texto(factura.total) }}
            </p>

            {% for nota in factura.notas %}
                <p>{{ nota }}</p>
            {% endfor %}
        </body>
        </html>
        """,
        encoding="utf-8",
    )

    app = create_app(
        databases={
            "test": f"sqlite:///{ruta_db}",
        },
        secret_key="test-secret-key",
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

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
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Calle del Cliente 10",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler del local",
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

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El usuario abre la factura propuesta para modificarla.
    response = client.get(
        f"/facturacion/facturas/{contrato_id}/modificar"
        "?periodo=10/2026"
        "&fecha_emision=01/10/2026"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "Modificar factura" in texto
    assert "LOCAL-1" in texto
    assert "Ana Pérez" in texto
    assert "11111111A" in texto
    assert "Calle del Cliente 10" in texto
    assert "36001" in texto
    assert "Pontevedra" in texto

    assert "Alquiler del local. Octubre de 2026" in texto
    assert "1.000,00" in texto
    assert "210,00" in texto
    assert "190,00" in texto
    assert "1.020,00" in texto

    assert "01/10/2026" in texto
    assert "10/2026" in texto

    assert "Previsualizar" in texto
    assert "Cancelar" in texto

    # Abrir el formulario no emite ni contabiliza nada.
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


def test_modificar_factura_acepta_datos_editados(
    tmp_path,
) -> None:
    """Valida los datos editados y muestra la factura resultante."""


    ruta_db = tmp_path / "test.db"
    ruta_plantilla = tmp_path / "test-factura.html"

    ruta_plantilla.write_text(
        """
        <!doctype html>
        <html>
        <body>
            {% for linea in factura.lineas %}
                <p>
                    {{ linea.concepto }}:
                    {{ importe_a_texto(linea.importe) }}
                </p>
            {% endfor %}

            <p>
                Total:
                {{ importe_a_texto(factura.total) }}
            </p>

            {% for nota in factura.notas %}
                <p>{{ nota }}</p>
            {% endfor %}
        </body>
        </html>
        """,
        encoding="utf-8",
    )

    app = create_app(
        databases={
            "test": f"sqlite:///{ruta_db}",
        },
        secret_key="test-secret-key",
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

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
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Calle del Cliente 10",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler local",
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

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        f"/facturacion/facturas/{contrato_id}/modificar"
        "?periodo=10/2026"
        "&fecha_emision=01/10/2026",
        data={
            "linea_concepto": [
                "Alquiler octubre",
                "Consumo de agua",
                "",
                "",
                "",
            ],
            "linea_importe": [
                "1000,00",
                "35,00",
                "",
                "",
                "",
            ],
            "iva_porcentaje": "21",
            "retencion_porcentaje": "19",
            "nota_texto": [
                "Primera nota de prueba.",
                "Segunda nota de prueba.",
                "",
            ],
        },
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "Alquiler octubre" in texto
    assert "1.000,00" in texto
    assert "Consumo de agua" in texto
    assert "35,00" in texto

    assert "Primera nota de prueba." in texto
    assert "Segunda nota de prueba." in texto

    assert "1.055,70" in texto
    assert "Alquiler octubre. Octubre de 2026" not in response.text

    # Todavía no se ha persistido ni contabilizado nada.
    with session_factory() as session:
        assert session.scalar(select(Factura)) is None
        assert session.scalar(select(ApunteContable)) is None
        assert session.scalar(select(MovimientoPrevisto)) is None


def test_modificar_factura_rechaza_linea_incompleta() -> None:
    """Exige concepto e importe en cada línea utilizada."""

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
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
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

    response = client.post(
        f"/facturacion/facturas/{contrato_id}/modificar"
        "?periodo=10/2026"
        "&fecha_emision=01/10/2026",
        data={
            "linea_concepto": [
                "Alquiler",
                "Consumo de agua",
                "",
                "",
                "",
            ],
            "linea_importe": [
                "1000,00",
                "",
                "",
                "",
                "",
            ],
            "iva_porcentaje": "21",
            "retencion_porcentaje": "19",
            "nota_texto": ["", "", ""],
        },
    )

    assert response.status_code == 400


def test_modificar_factura_rechaza_factura_sin_lineas() -> None:
    """Una factura debe contener al menos una línea."""

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
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
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

    response = client.post(
        f"/facturacion/facturas/{contrato_id}/modificar"
        "?periodo=10/2026"
        "&fecha_emision=01/10/2026",
        data={
            "linea_concepto": ["", "", "", "", ""],
            "linea_importe": ["", "", "", "", ""],
            "iva_porcentaje": "21",
            "retencion_porcentaje": "19",
            "nota_texto": ["", "", ""],
        },
    )

    assert response.status_code == 400


def test_firma_factura_devuelve_firma_base_activa(
    tmp_path,
) -> None:
    """Devuelve la firma asociada a la base de datos activa."""

    ruta_db = tmp_path / "test.db"
    ruta_firma = tmp_path / "test-firma.png"

    contenido_firma = b"\x89PNG\r\n\x1a\nfirma-de-prueba"

    ruta_firma.write_bytes(contenido_firma)

    app = create_app(
        databases={
            "test": f"sqlite:///{ruta_db}",
        },
        secret_key="test-secret-key",
    )

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/facturacion/facturas/firma"
    )

    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data == contenido_firma


def test_firma_factura_no_encontrada(
    tmp_path,
) -> None:
    """Devuelve 404 si no existe la firma de la base activa."""

    ruta_db = tmp_path / "test.db"

    app = create_app(
        databases={
            "test": f"sqlite:///{ruta_db}",
        },
        secret_key="test-secret-key",
    )

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/facturacion/facturas/firma"
    )

    assert response.status_code == 404
    assert (
        "No se encuentra la firma de la factura."
        in response.text
    )


def test_firma_factura_requiere_base_activa(
    tmp_path,
) -> None:
    """Rechaza la petición si no hay una base seleccionada."""

    ruta_db = tmp_path / "test.db"

    app = create_app(
        databases={
            "test": f"sqlite:///{ruta_db}",
        },
        secret_key="test-secret-key",
    )

    client = app.test_client()

    response = client.get(
        "/facturacion/facturas/firma"
    )

    assert response.status_code == 400
    assert (
        "No se ha seleccionado ninguna base de datos."
        in response.text
    )


def test_contabilizar_factura_persiste_factura_editada(
    tmp_path,
) -> None:
    """Persiste la factura previsualizada y su registro contable."""

    ruta_db = tmp_path / "test.db"

    app = create_app(
        databases={
            "test": f"sqlite:///{ruta_db}",
        },
        secret_key="test-secret-key",
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

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
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Calle del Cliente 10",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler local",
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

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        f"/facturacion/facturas/{contrato_id}/contabilizar",
        data={
            "periodo": "10/2026",
            "fecha_emision": "01/10/2026",
            "linea_concepto": [
                "Alquiler octubre",
                "Consumo de agua",
            ],
            "linea_importe": [
                "1000,00",
                "35,00",
            ],
            "iva_porcentaje": "21",
            "retencion_porcentaje": "19",
            "nota_texto": [
                "Primera nota de prueba.",
                "Segunda nota de prueba.",
            ],
            "base_previsualizada": "103500",
            "iva_previsualizado": "21735",
            "retencion_previsualizada": "19665",
            "total_previsualizado": "105570",
        },
    )

    assert response.status_code == 302

    assert response.headers["Location"].endswith(
        "/facturacion/?periodo=10/2026"
        "&fecha_emision=01/10/2026"
    )

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
        assert factura.fecha_emision == date(2026, 10, 1)
        assert factura.estado == "EMITIDA"

        assert len(factura.lineas) == 2

        assert factura.lineas[0].concepto == "Alquiler octubre"
        assert factura.lineas[0].importe == 100000

        assert factura.lineas[1].concepto == "Consumo de agua"
        assert factura.lineas[1].importe == 3500

        assert factura.base == 103500
        assert factura.iva_porcentaje == 2100
        assert factura.iva_importe == 21735
        assert factura.retencion_porcentaje == 1900
        assert factura.retencion_importe == 19665
        assert factura.total == 105570

        assert factura.notas == (
            "Primera nota de prueba.\n"
            "Segunda nota de prueba."
        )

        assert apunte is not None
        assert apunte.referencia_documento == (
            factura.numero_factura
        )
        assert apunte.categoria == "ING_ALQUILERES"
        assert apunte.base == factura.base
        assert apunte.iva_importe == factura.iva_importe
        assert (
            apunte.retencion_importe
            == factura.retencion_importe
        )
        assert apunte.total == factura.total

        assert movimiento is not None
        assert movimiento.apunte_id == apunte.id
        assert movimiento.contrato_id == contrato_id
        assert movimiento.importe_esperado == factura.total
        assert movimiento.estado == "PENDIENTE"


def test_contabilizar_factura_persiste_atrasos_revision_aplicada(
    tmp_path,
) -> None:
    """Persiste la renta revisada y los atrasos de una revisión aplicada."""

    ruta_db = tmp_path / "test.db"

    app = create_app(
        databases={
            "test": f"sqlite:///{ruta_db}",
        },
        secret_key="test-secret-key",
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

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
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Calle del Cliente 10",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler local",
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

        contrato.rentas.extend(
            [
                RentaContrato(
                    fecha_desde=contrato.fecha_inicio,
                    importe=100000,
                ),
                RentaContrato(
                    fecha_desde=date(2026, 10, 1),
                    importe=103600,
                ),
            ]
        )

        revision = RevisionRenta(
            contrato=contrato,
            fecha_prevista=date(2026, 10, 1),
            fecha_resolucion=date(2026, 11, 1),
            metodo="IPC_NACIONAL",
            estado="APLICADA",
            porcentaje_aplicado=360,
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

    response = client.post(
        f"/facturacion/facturas/{contrato_id}/contabilizar",
        data={
            "periodo": "11/2026",
            "fecha_emision": "01/11/2026",
            "linea_concepto": [
                "Alquiler local. Noviembre de 2026",
                (
                    "Atrasos de Octubre 2026 "
                    "por actualización de renta"
                ),
            ],
            "linea_importe": [
                "1036,00",
                "36,00",
            ],
            "iva_porcentaje": "21",
            "retencion_porcentaje": "19",
            "nota_texto": [
                (
                    "El IPC General de Precios al Consumo de "
                    "octubre ha sido del 3,6%, por lo que se "
                    "incrementa el alquiler en esta cuantía."
                ),
                (
                    "Atrasos de Octubre 2026 por la actualización "
                    "de renta, conforme se indicó en el recibo "
                    "de dicho mes."
                ),
            ],
            "base_previsualizada": "107200",
            "iva_previsualizado": "22512",
            "retencion_previsualizada": "20368",
            "total_previsualizado": "109344",
        },
    )

    assert response.status_code == 302

    assert response.headers["Location"].endswith(
        "/facturacion/?periodo=11/2026"
        "&fecha_emision=01/11/2026"
    )

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
        assert factura.periodo == date(2026, 11, 1)
        assert factura.fecha_emision == date(2026, 11, 1)
        assert factura.estado == "EMITIDA"

        assert factura.revision_renta_id == revision_id
        assert factura.aviso_revision == "APLICADA"

        assert len(factura.lineas) == 2

        assert (
            factura.lineas[0].concepto
            == "Alquiler local. Noviembre de 2026"
        )
        assert factura.lineas[0].importe == 103600

        assert factura.lineas[1].concepto == (
            "Atrasos de Octubre 2026 "
            "por actualización de renta"
        )
        assert factura.lineas[1].importe == 3600

        assert factura.base == 107200
        assert factura.iva_porcentaje == 2100
        assert factura.iva_importe == 22512
        assert factura.retencion_porcentaje == 1900
        assert factura.retencion_importe == 20368
        assert factura.total == 109344

        assert factura.notas == (
            "El IPC General de Precios al Consumo de octubre "
            "ha sido del 3,6%, por lo que se incrementa el "
            "alquiler en esta cuantía.\n"
            "Atrasos de Octubre 2026 por la actualización de "
            "renta, conforme se indicó en el recibo de dicho mes."
        )

        assert apunte is not None
        assert apunte.referencia_documento == factura.numero_factura
        assert apunte.categoria == "ING_ALQUILERES"
        assert apunte.base == factura.base
        assert apunte.iva_importe == factura.iva_importe
        assert (
            apunte.retencion_importe
            == factura.retencion_importe
        )
        assert apunte.total == factura.total

        assert movimiento is not None
        assert movimiento.apunte_id == apunte.id
        assert movimiento.contrato_id == contrato_id
        assert movimiento.importe_esperado == factura.total
        assert movimiento.estado == "PENDIENTE"


def test_contabilizar_factura_rechaza_importes_distintos(
    tmp_path,
) -> None:
    """Rechaza importes distintos de los previsualizados."""

    ruta_db = tmp_path / "test.db"

    app = create_app(
        databases={
            "test": f"sqlite:///{ruta_db}",
        },
        secret_key="test-secret-key",
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

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
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Calle del Cliente 10",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler local",
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

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        f"/facturacion/facturas/{contrato_id}/contabilizar",
        data={
            "periodo": "10/2026",
            "fecha_emision": "01/10/2026",
            "linea_concepto": [
                "Alquiler octubre",
                "Consumo de agua",
            ],
            "linea_importe": [
                "1000,00",
                "35,00",
            ],
            "iva_porcentaje": "21",
            "retencion_porcentaje": "19",
            "nota_texto": [
                "Primera nota de prueba.",
                "Segunda nota de prueba.",
            ],
            "base_previsualizada": "103500",
            "iva_previsualizado": "21735",
            "retencion_previsualizada": "19665",

            # Un céntimo distinto del total calculado.
            "total_previsualizado": "105571",
        },
    )

    assert response.status_code == 400

    assert (
        "Los importes de la factura han cambiado. "
        "Vuelve a previsualizarla antes de contabilizar."
        in response.get_data(as_text=True)
    )

    with session_factory() as session:
        assert session.scalar(select(Factura)) is None
        assert session.scalar(select(ApunteContable)) is None
        assert session.scalar(select(MovimientoPrevisto)) is None


def test_previsualizar_factura_desde_lista_no_persiste(
    tmp_path,
    monkeypatch,
) -> None:
    """Previsualiza desde el resumen sin persistir la factura."""

    ruta_db = tmp_path / "test.db"
    ruta_plantilla = tmp_path / "test-factura.html"

    ruta_plantilla.write_text(
        """
        <!doctype html>
        <html>
        <body>
            {% for linea in factura.lineas %}
                <p>
                    {{ linea.concepto }}:
                    {{ importe_a_texto(linea.importe) }}
                </p>
            {% endfor %}

            <p>
                IVA:
                {{ importe_a_texto(factura.iva_importe) }}
            </p>

            <p>
                Retención:
                {{ importe_a_texto(factura.retencion_importe) }}
            </p>

            <p>
                Total:
                {{ importe_a_texto(factura.total) }}
            </p>
        </body>
        </html>
        """,
        encoding="utf-8",
    )

    app = create_app(
        databases={
            "test": f"sqlite:///{ruta_db}",
        },
        secret_key="test-secret-key",
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

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
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Calle del Cliente 10",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler local",
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

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # El resumen ofrece la previsualización directa.
    response = client.get(
        "/facturacion/"
        "?periodo=10/2026"
        "&fecha_emision=01/10/2026"
    )

    assert response.status_code == 200
    assert "Previsualizar" in response.get_data(as_text=True)

    # El usuario previsualiza directamente los datos preparados
    # en el resumen, sin pasar por Modificar.
    response = client.post(
        f"/facturacion/facturas/{contrato_id}/modificar"
        "?periodo=10/2026"
        "&fecha_emision=01/10/2026",
        data={
            "linea_concepto": [
                "Alquiler local",
            ],
            "linea_importe": [
                "1000,00",
            ],
            "iva_porcentaje": "21",
            "retencion_porcentaje": "19",
        },
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "Alquiler local" in texto
    assert "1.000,00" in texto
    assert "210,00" in texto
    assert "190,00" in texto
    assert "1.020,00" in texto

    # Previsualizar nunca persiste ni contabiliza.
    with session_factory() as session:
        assert session.scalar(select(Factura)) is None
        assert session.scalar(select(ApunteContable)) is None
        assert session.scalar(select(MovimientoPrevisto)) is None


def test_modificar_factura_muestra_nota_aviso_revision() -> None:
    """Muestra en la factura la nota de aviso de revisión."""

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
            fecha_prevista=date(2026, 10, 1),
            metodo="IPC_NACIONAL",
            estado="PENDIENTE",
        )

        session.add(contrato)
        session.add(revision)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # Septiembre debe mostrar el aviso de la revisión de octubre.
    response = client.get(
        f"/facturacion/facturas/{contrato_id}/modificar"
        "?periodo=09/2026"
        "&fecha_emision=01/09/2026"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert (
        "el próximo mes de octubre corresponde actualizar "
        "el alquiler"
    ) in texto

    assert "IPC General de Precios al Consumo" in texto


def test_modificar_factura_muestra_nota_esperando_indice() -> None:
    """Muestra la nota mientras se espera el índice de revisión."""

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
            fecha_prevista=date(2026, 10, 1),
            metodo="IPC_NACIONAL",
            estado="PENDIENTE",
        )

        session.add(contrato)
        session.add(revision)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    # Octubre debe indicar que todavía se espera el índice.
    response = client.get(
        f"/facturacion/facturas/{contrato_id}/modificar"
        "?periodo=10/2026"
        "&fecha_emision=01/10/2026"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert (
        "corresponde este mes actualizar el alquiler"
    ) in texto

    assert (
        "Como dicho dato no está aún disponible"
    ) in texto

    assert (
        "Se pasará la diferencia una vez que se conozca "
        "el dato del IPC General de Precios al Consumo."
    ) in texto


def test_modificar_factura_muestra_atrasos_revision_aplicada(
    tmp_path,
) -> None:
    """Muestra la renta revisada y los atrasos en el formulario."""

    ruta_db = tmp_path / "test.db"

    app = create_app(
        databases={
            "test": f"sqlite:///{ruta_db}",
        },
        secret_key="test-secret-key",
    )

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    Base.metadata.create_all(
        session_factory.kw["bind"]
    )

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
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Calle del Cliente 10",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler local",
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

        contrato.rentas.extend(
            [
                RentaContrato(
                    fecha_desde=contrato.fecha_inicio,
                    importe=100000,
                ),
                RentaContrato(
                    fecha_desde=date(2026, 10, 1),
                    importe=103600,
                ),
            ]
        )

        revision = RevisionRenta(
            contrato=contrato,
            fecha_prevista=date(2026, 10, 1),
            fecha_resolucion=date(2026, 11, 1),
            metodo="IPC_NACIONAL",
            estado="APLICADA",
            porcentaje_aplicado=360,
        )

        session.add(contrato)
        session.add(revision)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        f"/facturacion/facturas/{contrato_id}/modificar"
        "?periodo=11/2026"
        "&fecha_emision=01/11/2026"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    # La renta revisada aparece como primera línea.
    assert "Alquiler local. Noviembre de 2026" in texto
    assert "1036,00" in texto

    # Los atrasos aparecen como una línea independiente.
    assert (
        "Atrasos de Octubre 2026 "
        "por actualización de renta"
    ) in texto
    assert "36,00" in texto

    # También se muestran las notas de la revisión aplicada.
    assert (
        "El IPC General de Precios al Consumo de octubre "
        "ha sido del 3,6%"
    ) in texto

    assert (
        "Atrasos de Octubre 2026 por la actualización "
        "de renta"
    ) in texto

    # El formulario muestra los totales incluyendo los atrasos.
    assert "1.072,00" in texto
    assert "225,12" in texto
    assert "203,68" in texto
    assert "1.093,44" in texto


def test_listar_facturacion_desacopla_fecha_emision_de_preparar() -> None:
    """La fecha de emisión puede cambiarse sin volver a preparar."""

    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/facturacion/?periodo=10/2026"
    )

    assert response.status_code == 200

    html = response.get_data(as_text=True)

    assert 'id="periodo"' in html
    assert 'name="periodo"' in html

    assert 'id="periodo"' in html
    assert 'name="periodo"' in html

    assert 'id="fecha_emision"' in html
    assert 'value="01/10/2026"' in html

    # La fecha de emisión no forma parte del formulario
    # GET que vuelve a preparar el período.
    inicio_formulario = html.index("<form")
    fin_formulario = html.index(
        "</form>",
        inicio_formulario,
    )

    formulario_preparar = html[
        inicio_formulario:fin_formulario
    ]

    assert 'name="periodo"' in formulario_preparar
    assert (
        'name="fecha_emision"'
        not in formulario_preparar
    )


def test_listar_facturacion_propaga_fecha_emision_a_acciones() -> None:
    """Las acciones usan la fecha de emisión editable del resumen."""

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
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2030, 12, 31),
            genera_factura=True,
            fecha_inicio_facturacion=date(2026, 1, 1),
            fianza=100000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Calle del Cliente 10",
            codigo_postal_facturacion="36001",
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler local",
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

        session.add(contrato)
        session.commit()

        contrato_id = contrato.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/facturacion/?periodo=10/2026"
    )

    assert response.status_code == 200

    html = response.get_data(as_text=True)

    assert 'id="fecha_emision"' in html
    assert 'value="01/10/2026"' in html

    assert (
        f"/facturacion/facturas/{contrato_id}/modificar"
        "?periodo=10/2026"
        in html
    )

    assert (
        f"/facturacion/facturas/{contrato_id}/modificar"
        "?periodo=10/2026"
        "&amp;fecha_emision="
        not in html
    )

    assert "data-usa-fecha-emision" in html

    assert (
        'url.searchParams.set(\n'
        '                            "fecha_emision",'
        in html
    )


def test_listar_facturas_muestra_facturas_emitidas() -> None:
    """Muestra las facturas persistidas y permite consultar su detalle."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        factura = _crear_factura_emitida_para_test(
            session
        )
        factura_id = factura.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/facturacion/facturas"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "Facturas" in texto
    assert "01/10/2026" in texto
    assert "01/2026A1" in texto
    assert "LOCAL-1" in texto
    assert "Ana Pérez" in texto
    assert "1.055,70" in texto
    assert "Emitida" in texto

    assert (
        f'/facturacion/facturas/{factura_id}'
        in texto
    )


def test_ver_factura_muestra_datos_persistidos() -> None:
    """Muestra el contenido de una factura ya emitida."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        factura = _crear_factura_emitida_para_test(
            session
        )
        factura_id = factura.id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        f"/facturacion/facturas/{factura_id}"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "Factura 01/2026A1" in texto
    assert "LOCAL-1" in texto
    assert "Ana Pérez" in texto
    assert "11111111A" in texto

    assert "01/10/2026" in texto
    assert "Octubre de 2026" in texto
    assert "Emitida" in texto

    assert "Alquiler local" in texto
    assert "1.000,00" in texto

    assert "Consumo de agua" in texto
    assert "35,00" in texto

    assert "1.035,00" in texto
    assert "217,35" in texto
    assert "196,65" in texto
    assert "1.055,70" in texto

    assert "Factura de prueba." in texto


def test_ver_factura_inexistente_devuelve_404() -> None:
    """Devuelve 404 al consultar una factura inexistente."""

    app = crear_app_test()

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/facturacion/facturas/999"
    )

    assert response.status_code == 404
    assert (
        "Factura no encontrada."
        in response.get_data(as_text=True)
    )


def test_listar_facturas_filtra_por_anio() -> None:
    """Muestra únicamente las facturas del ejercicio seleccionado."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        _crear_factura_emitida_para_test(
            session,
            referencia="LOCAL-2025",
            codigo_facturacion="A1",
            anio=2025,
            destinatario="Cliente 2025",
            nif="11111111A",
        )

        _crear_factura_emitida_para_test(
            session,
            referencia="LOCAL-2026",
            codigo_facturacion="B1",
            anio=2026,
            destinatario="Cliente 2026",
            nif="22222222B",
        )

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/facturacion/facturas?anio=2026"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "LOCAL-2026" in texto
    assert "Cliente 2026" in texto

    assert "Cliente 2025" not in texto

    assert 'value="2026"' in texto


def test_listar_facturas_filtra_por_inmueble() -> None:
    """Muestra únicamente las facturas del inmueble seleccionado."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        factura_a = _crear_factura_emitida_para_test(
            session,
            referencia="LOCAL-A",
            codigo_facturacion="A1",
            anio=2026,
            destinatario="Cliente A",
            nif="11111111A",
        )

        _crear_factura_emitida_para_test(
            session,
            referencia="LOCAL-B",
            codigo_facturacion="B1",
            anio=2026,
            destinatario="Cliente B",
            nif="22222222B",
        )

        inmueble_id = (
            factura_a.contrato.inmueble.id
        )

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/facturacion/facturas"
        f"?anio=2026&inmueble_id={inmueble_id}"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "LOCAL-A" in texto
    assert "Cliente A" in texto

    assert "Cliente B" not in texto

    assert (
        f'value="{inmueble_id}" selected'
        in texto
    )


def test_ver_factura_usa_snapshot_historico() -> None:
    """La consulta de una factura no depende del contrato actual."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        factura = _crear_factura_emitida_para_test(
            session,
            referencia="LOCAL-HIST",
            codigo_facturacion="A1",
            destinatario="Cliente Histórico",
            nif="11111111A",
        )

        contrato = factura.contrato

        contrato.inmueble.referencia = "LOCAL-NUEVO"
        contrato.direccion_facturacion = "Dirección nueva"
        contrato.codigo_postal_facturacion = "99999"
        contrato.poblacion_facturacion = "Vigo"
        contrato.provincia_facturacion = "A Coruña"

        contrato.titulares[0].inquilino.nombre = (
            "Cliente Nuevo"
        )
        contrato.titulares[0].inquilino.nif = (
            "99999999Z"
        )

        factura_id = factura.id

        session.commit()

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        f"/facturacion/facturas/{factura_id}"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "LOCAL-HIST" in texto
    assert "Cliente Histórico" in texto
    assert "11111111A" in texto
    assert "Calle del Cliente 10" in texto
    assert "36001" in texto
    assert "Pontevedra" in texto

    assert "LOCAL-NUEVO" not in texto
    assert "Cliente Nuevo" not in texto
    assert "99999999Z" not in texto
    assert "Dirección nueva" not in texto


def test_listar_facturas_usa_snapshot_historico() -> None:
    """El listado muestra datos históricos de la factura."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        factura = _crear_factura_emitida_para_test(
            session,
            referencia="LOCAL-HIST",
            codigo_facturacion="A1",
            destinatario="Cliente Histórico",
            nif="11111111A",
        )

        factura.contrato.inmueble.referencia = (
            "LOCAL-NUEVO"
        )
        factura.contrato.titulares[
            0
        ].inquilino.nombre = "Cliente Nuevo"

        session.commit()

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.get(
        "/facturacion/facturas?anio=2026"
    )

    assert response.status_code == 200

    texto = response.get_data(as_text=True)

    assert "LOCAL-HIST" in texto
    assert "Cliente Histórico" in texto

    assert "Cliente Nuevo" not in texto


def test_eliminar_factura_borra_factura_y_registro_contable() -> None:
    """Elimina factura, detalle, apunte y movimiento previsto."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        factura = _crear_factura_emitida_para_test(
            session
        )

        apunte, movimiento = (
            _anadir_registro_contable_factura_para_test(
                session,
                factura,
            )
        )

        factura_id = factura.id
        apunte_id = apunte.id
        movimiento_id = movimiento.id

        linea_ids = [
            linea.id
            for linea in factura.lineas
        ]

        destinatario_ids = [
            destinatario.id
            for destinatario in factura.destinatarios
        ]

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        f"/facturacion/facturas/{factura_id}/eliminar"
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/facturacion/facturas"
    )

    with session_factory() as session:
        assert session.get(
            Factura,
            factura_id,
        ) is None

        assert session.get(
            ApunteContable,
            apunte_id,
        ) is None

        assert session.get(
            MovimientoPrevisto,
            movimiento_id,
        ) is None

        for linea_id in linea_ids:
            assert session.get(
                FacturaLinea,
                linea_id,
            ) is None

        for destinatario_id in destinatario_ids:
            assert session.get(
                FacturaDestinatario,
                destinatario_id,
            ) is None


def test_eliminar_factura_inexistente_devuelve_404() -> None:
    """Devuelve 404 al intentar eliminar una factura inexistente."""

    app = crear_app_test()

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        "/facturacion/facturas/999/eliminar"
    )

    assert response.status_code == 404
    assert (
        "Factura no encontrada."
        in response.get_data(as_text=True)
    )


def test_eliminar_factura_conciliada_devuelve_400_y_no_borra() -> None:
    """No modifica datos cuando la factura no puede eliminarse."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        factura = _crear_factura_emitida_para_test(
            session
        )

        apunte, movimiento = (
            _anadir_registro_contable_factura_para_test(
                session,
                factura,
            )
        )

        movimiento.estado = "CONCILIADO"

        factura_id = factura.id
        apunte_id = apunte.id
        movimiento_id = movimiento.id

        session.commit()

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        f"/facturacion/facturas/{factura_id}/eliminar"
    )

    assert response.status_code == 400
    assert (
        "conciliado"
        in response.get_data(
            as_text=True
        ).lower()
    )

    with session_factory() as session:
        assert session.get(
            Factura,
            factura_id,
        ) is not None

        assert session.get(
            ApunteContable,
            apunte_id,
        ) is not None

        assert session.get(
            MovimientoPrevisto,
            movimiento_id,
        ) is not None


def test_eliminar_factura_permite_reutilizar_su_numero() -> None:
    """Al eliminar la última factura, su número vuelve a quedar disponible."""

    app = crear_app_test()

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        factura = _crear_factura_emitida_para_test(
            session,
            numero_secuencia=1,
        )

        _anadir_registro_contable_factura_para_test(
            session,
            factura,
        )

        factura_id = factura.id
        contrato_id = factura.contrato_id

    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        f"/facturacion/facturas/{factura_id}/eliminar"
    )

    assert response.status_code == 302

    with session_factory() as session:
        contrato = session.get(
            Contrato,
            contrato_id,
        )

        numero, literal = siguiente_numero_factura(
            contrato=contrato,
            anio=2026,
        )

        assert numero == 1
        assert literal == "01/2026A1"





"""Pruebas de consulta y navegación de relaciones contables."""

import pytest

from datetime import date
from sqlalchemy import select

from contab.app import create_app
from contab.database import Base
from contab.models import (
    ApunteContable,
    Conciliacion,
    Contrato,
    Factura,
    Inmueble,
    MovimientoBancario,
    MovimientoPrevisto,
)
from contab.conciliacion.services import deshacer_asociacion_bancaria



def _sesiones_relaciones(client):
    return client.application.extensions[
        "contab_databases"
    ]["test"]


def _buscar_id_relaciones(client, modelo, campo, valor):
    with _sesiones_relaciones(client)() as session:
        identificador = session.scalar(
            select(modelo.id).where(
                getattr(modelo, campo) == valor
            )
        )
        assert identificador is not None
        return identificador



@pytest.fixture
def escenario():
    """Dos previstos comparten un bancario; uno tiene otro cobro."""

    app = create_app(
        databases={"test": "sqlite:///:memory:"},
        secret_key="test-secret-key",
    )
    session_factory = app.extensions["contab_databases"]["test"]
    engine = session_factory.kw["bind"]
    Base.metadata.create_all(engine)

    with session_factory() as session:
        inmueble = Inmueble(
            referencia="LOCAL-REL",
            codigo_facturacion="REL",
            tipo="L",
            descripcion="Local de relaciones",
            direccion="Calle de prueba",
            poblacion="Madrid",
            provincia="Madrid",
            porcentaje_titular=10000,
            tipo_derecho="PLENA_PROPIEDAD",
            porcentaje_derecho=10000,
            fecha_adquisicion=date(2020, 1, 1),
            tipo_adquisicion="ONEROSA",
            importe_adquisicion=0,
            gastos_adquisicion=0,
        )

        def apunte(concepto, importe):
            return ApunteContable(
                inmueble=inmueble,
                fecha=date(2026, 11, 1),
                naturaleza="INGRESO",
                categoria="ING_ALQUILERES",
                concepto=concepto,
                tratamiento="CONTABILIZAR",
                base=importe,
                iva_importe=0,
                retencion_importe=0,
                total=importe,
            )

        apunte_a = apunte("APUNTE RELACIONES A", 100000)
        apunte_b = apunte("APUNTE RELACIONES B", 50000)

        def factura(apunte, secuencia):
            contrato = Contrato(
                inmueble=inmueble,
                fecha_inicio=date(2025, 1, 1),
                fecha_vencimiento=date(2030, 12, 31),
                genera_factura=True,
                fecha_inicio_facturacion=date(2025, 1, 1),
                fianza=0,
                iva_porcentaje=0,
                retencion_porcentaje=0,
                direccion_facturacion="Calle de prueba",
                poblacion_facturacion="Madrid",
                provincia_facturacion="Madrid",
                concepto_factura="Alquiler",
            )

            return Factura(
                contrato=contrato,
                apunte_contable=apunte,
                numero_secuencia=secuencia,
                anio=2026,
                numero_factura=f"{secuencia:02d}/2026REL",
                referencia_inmueble=inmueble.referencia,
                descripcion_inmueble=inmueble.descripcion,
                direccion_facturacion=contrato.direccion_facturacion,
                poblacion_facturacion=contrato.poblacion_facturacion,
                provincia_facturacion=contrato.provincia_facturacion,
                fecha_emision=date(2026, 11, 1),
                periodo=date(2026, 11, 1),
                base=apunte.base,
                iva_porcentaje=0,
                iva_importe=0,
                retencion_porcentaje=0,
                retencion_importe=0,
                total=apunte.total,
                estado="EMITIDA",
            )


        factura_a = factura(apunte_a, 1)
        factura_b = factura(apunte_b, 2)

        previsto_a = MovimientoPrevisto(
            inmueble=inmueble,
            apunte=apunte_a,
            naturaleza="INGRESO",
            concepto="PREVISTO RELACIONES A",
            importe_esperado=100000,
            estado="CONCILIADO",
        )
        previsto_b = MovimientoPrevisto(
            inmueble=inmueble,
            apunte=apunte_b,
            naturaleza="INGRESO",
            concepto="PREVISTO RELACIONES B",
            importe_esperado=50000,
            estado="CONCILIADO",
        )

        bancario_compartido = MovimientoBancario(
            fecha=date(2026, 11, 12),
            naturaleza="INGRESO",
            importe=130000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="BANCARIO COMPARTIDO RELACIONES",
            huella_importacion="relaciones-compartido",
            estado="CONCILIADO",
        )
        bancario_adicional = MovimientoBancario(
            fecha=date(2026, 11, 13),
            naturaleza="INGRESO",
            importe=20000,
            tipo_original="TRANSFERENCIA",
            descripcion_original="BANCARIO ADICIONAL RELACIONES",
            huella_importacion="relaciones-adicional",
            estado="CONCILIADO",
        )

        previsto_manual = MovimientoPrevisto(
            inmueble=inmueble,
            naturaleza="INGRESO",
            concepto="PREVISTO MANUAL RELACIONES",
            importe_esperado=30000,
            estado="CONCILIADO",
            metodo_conciliacion="MANUAL",
            notas="Cobro comprobado externamente",
        )
        previsto_pendiente = MovimientoPrevisto(
            inmueble=inmueble,
            naturaleza="GASTO",
            concepto="PREVISTO PENDIENTE RELACIONES",
            importe_esperado=40000,
            estado="PENDIENTE",
        )

        session.add_all([
            previsto_a,
            previsto_b,
            bancario_compartido,
            bancario_adicional,
            previsto_manual,
            previsto_pendiente,
            factura_a,
            factura_b,
        ])
        session.flush()

        session.add_all([
            Conciliacion(
                movimiento_previsto=previsto_a,
                movimiento_bancario=bancario_compartido,
                importe_asociado=80000,
            ),
            Conciliacion(
                movimiento_previsto=previsto_b,
                movimiento_bancario=bancario_compartido,
                importe_asociado=50000,
            ),
            Conciliacion(
                movimiento_previsto=previsto_a,
                movimiento_bancario=bancario_adicional,
                importe_asociado=20000,
            ),
        ])
        session.flush()

        ids = {
            "apunte_a": apunte_a.id,
            "apunte_b": apunte_b.id,
            "previsto_a": previsto_a.id,
            "previsto_b": previsto_b.id,
            "bancario_compartido": bancario_compartido.id,
            "bancario_adicional": bancario_adicional.id,
            "previsto_manual": previsto_manual.id,
            "previsto_pendiente": previsto_pendiente.id,
        }
        session.commit()

    client = app.test_client()
    client.post("/", data={"database": "test"})

    yield client, ids

    engine.dispose()


def test_relaciones_desde_bancario_muestra_todos_sus_previstos(
    escenario,
):
    client, ids = escenario

    response = client.get(
        f"/conciliacion/relaciones/bancario/"
        f"{ids['bancario_compartido']}"
    )

    assert response.status_code == 200
    assert "BANCARIO COMPARTIDO RELACIONES" in response.text
    assert "PREVISTO RELACIONES A" in response.text
    assert "PREVISTO RELACIONES B" in response.text
    assert "APUNTE RELACIONES A" in response.text
    assert "APUNTE RELACIONES B" in response.text

    # El otro bancario de A queda fuera de este recorrido.
    assert "BANCARIO ADICIONAL RELACIONES" in response.text
    assert "Otros movimientos bancarios asociados" in response.text

    # El bancario no se repite en las relaciones
    assert response.text.count(
        "BANCARIO COMPARTIDO RELACIONES"
    ) == 1


def test_relaciones_desde_previsto_no_expande_otros_previstos(
    escenario,
):
    client, ids = escenario

    response = client.get(
        f"/conciliacion/relaciones/previsto/"
        f"{ids['previsto_a']}"
    )

    assert response.status_code == 200
    assert "PREVISTO RELACIONES A" in response.text
    assert "APUNTE RELACIONES A" in response.text
    assert "BANCARIO COMPARTIDO RELACIONES" in response.text
    assert "BANCARIO ADICIONAL RELACIONES" in response.text

    assert "PREVISTO RELACIONES B" not in response.text
    assert "APUNTE RELACIONES B" not in response.text


def test_relaciones_desde_apunte_muestra_su_previsto_y_bancarios(
    escenario,
):
    client, ids = escenario

    response = client.get(
        f"/conciliacion/relaciones/apunte/"
        f"{ids['apunte_a']}"
    )

    assert response.status_code == 200
    assert "APUNTE RELACIONES A" in response.text
    assert "PREVISTO RELACIONES A" in response.text
    assert "BANCARIO COMPARTIDO RELACIONES" in response.text
    assert "BANCARIO ADICIONAL RELACIONES" in response.text

    assert "PREVISTO RELACIONES B" not in response.text
    assert "APUNTE RELACIONES B" not in response.text


@pytest.mark.parametrize(
    "tipo",
    ["apunte", "previsto", "bancario"],
)
def test_relaciones_inexistentes_devuelven_404(
    escenario,
    tipo,
):
    client, _ = escenario

    response = client.get(
        f"/conciliacion/relaciones/{tipo}/999999"
    )

    assert response.status_code == 404


def test_relaciones_previsto_pendiente_sin_bancarios(
    escenario,
):
    client, ids = escenario

    response = client.get(
        f"/conciliacion/relaciones/previsto/"
        f"{ids['previsto_pendiente']}"
    )

    assert response.status_code == 200
    assert "PREVISTO PENDIENTE RELACIONES" in response.text
    assert "BANCARIO COMPARTIDO RELACIONES" not in response.text


def test_relaciones_conciliacion_manual_no_inventa_bancario(
    escenario,
):
    client, ids = escenario

    response = client.get(
        f"/conciliacion/relaciones/previsto/"
        f"{ids['previsto_manual']}"
    )

    assert response.status_code == 200
    assert "PREVISTO MANUAL RELACIONES" in response.text
    assert "Cobro comprobado externamente" in response.text
    assert "BANCARIO COMPARTIDO RELACIONES" not in response.text


def test_relaciones_bancario_compartido_permite_ir_a_cada_previsto(
    escenario,
):
    client, ids = escenario

    response = client.get(
        f"/conciliacion/relaciones/bancario/"
        f"{ids['bancario_compartido']}"
    )

    assert response.status_code == 200

    for previsto in ("previsto_a", "previsto_b"):
        assert (
            f"/conciliacion/relaciones/previsto/{ids[previsto]}"
            in response.text
        )


def test_relaciones_desde_bancario_muestra_facturas_de_cada_previsto(
    escenario,
):
    client, ids = escenario

    response = client.get(
        f"/conciliacion/relaciones/bancario/"
        f"{ids['bancario_compartido']}"
    )

    assert response.status_code == 200
    assert "01/2026REL" in response.text
    assert "02/2026REL" in response.text
    assert "APUNTE RELACIONES A" in response.text
    assert "APUNTE RELACIONES B" in response.text


@pytest.mark.parametrize(
    "origen, identificador",
    [
        ("previsto", "previsto_a"),
        ("apunte", "apunte_a"),
    ],
)
def test_relaciones_no_muestra_facturas_de_otros_previstos(
    escenario,
    origen,
    identificador,
):
    client, ids = escenario

    response = client.get(
        f"/conciliacion/relaciones/{origen}/"
        f"{ids[identificador]}"
    )

    assert response.status_code == 200
    assert "01/2026REL" in response.text
    assert "02/2026REL" not in response.text


def test_relaciones_previsto_pendiente_muestra_acciones(
    escenario,
):
    client, _ = escenario

    previsto_id = _buscar_id_relaciones(
        client,
        MovimientoPrevisto,
        "concepto",
        "PREVISTO PENDIENTE RELACIONES",
    )

    response = client.get(
        f"/conciliacion/relaciones/previsto/{previsto_id}"
    )

    assert response.status_code == 200
    assert "Conciliar manualmente" in response.text
    assert "Anular previsto" in response.text
    assert "Restaurar previsto" not in response.text
    assert "Deshacer conciliación manual" not in response.text


def test_relaciones_previsto_cancelado_solo_permite_restaurar(
    escenario,
):
    client, _ = escenario

    previsto_id = _buscar_id_relaciones(
        client,
        MovimientoPrevisto,
        "concepto",
        "PREVISTO PENDIENTE RELACIONES",
    )

    with _sesiones_relaciones(client)() as session:
        previsto = session.get(
            MovimientoPrevisto,
            previsto_id,
        )
        previsto.estado = "CANCELADO"
        session.commit()

    response = client.get(
        f"/conciliacion/relaciones/previsto/{previsto_id}"
    )

    assert response.status_code == 200
    assert "Restaurar previsto" in response.text
    assert "Anular previsto" not in response.text
    assert "Conciliar manualmente" not in response.text


def test_relaciones_conciliacion_manual_permite_deshacer(
    escenario,
):
    client, _ = escenario

    previsto_id = _buscar_id_relaciones(
        client,
        MovimientoPrevisto,
        "concepto",
        "PREVISTO MANUAL RELACIONES",
    )

    response = client.get(
        f"/conciliacion/relaciones/previsto/{previsto_id}"
    )

    assert response.status_code == 200
    assert "Deshacer conciliación manual" in response.text
    assert "Conciliar manualmente" not in response.text
    assert "Anular previsto" not in response.text


def test_anular_previsto_desde_relaciones_conserva_origen(
    escenario,
):
    client, _ = escenario

    previsto_id = _buscar_id_relaciones(
        client,
        MovimientoPrevisto,
        "concepto",
        "PREVISTO PENDIENTE RELACIONES",
    )

    response = client.post(
        f"/conciliacion/previstos/{previsto_id}/cancelar",
        data={
            "relaciones_tipo": "previsto",
            "relaciones_id": previsto_id,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.location.endswith(
        f"/conciliacion/relaciones/previsto/{previsto_id}"
    )

    with _sesiones_relaciones(client)() as session:
        previsto = session.get(
            MovimientoPrevisto,
            previsto_id,
        )
        assert previsto.estado == "CANCELADO"


def test_relaciones_bancario_compartido_muestra_deshacer_por_previsto(
    escenario,
):
    client, _ = escenario

    bancario_id = _buscar_id_relaciones(
        client,
        MovimientoBancario,
        "descripcion_original",
        "BANCARIO COMPARTIDO RELACIONES",
    )

    with _sesiones_relaciones(client)() as session:
        asociaciones = session.scalars(
            select(Conciliacion).where(
                Conciliacion.movimiento_bancario_id == bancario_id
            )
        ).all()

        acciones_esperadas = [
            (
                f"/conciliacion/previstos/"
                f"{asociacion.movimiento_previsto_id}"
                f"/asociaciones/{asociacion.id}/deshacer"
            )
            for asociacion in asociaciones
        ]

    assert len(acciones_esperadas) == 2

    response = client.get(
        f"/conciliacion/relaciones/bancario/{bancario_id}"
    )

    assert response.status_code == 200

    for accion in acciones_esperadas:
        assert f'action="{accion}"' in response.text


def test_relaciones_previsto_muestra_deshacer_por_bancario(
    escenario,
):
    client, _ = escenario

    previsto_id = _buscar_id_relaciones(
        client,
        MovimientoPrevisto,
        "concepto",
        "PREVISTO RELACIONES A",
    )

    with _sesiones_relaciones(client)() as session:
        asociaciones = session.scalars(
            select(Conciliacion).where(
                Conciliacion.movimiento_previsto_id == previsto_id
            )
        ).all()

        acciones_esperadas = [
            (
                f"/conciliacion/previstos/{previsto_id}"
                f"/asociaciones/{asociacion.id}/deshacer"
            )
            for asociacion in asociaciones
        ]

    assert len(acciones_esperadas) == 2

    response = client.get(
        f"/conciliacion/relaciones/previsto/{previsto_id}"
    )

    assert response.status_code == 200

    for accion in acciones_esperadas:
        assert f'action="{accion}"' in response.text


def test_deshacer_una_asociacion_no_elimina_las_demas(
    escenario,
):
    client, _ = escenario

    previsto_id = _buscar_id_relaciones(
        client,
        MovimientoPrevisto,
        "concepto",
        "PREVISTO RELACIONES A",
    )

    with _sesiones_relaciones(client)() as session:
        asociaciones = session.scalars(
            select(Conciliacion).where(
                Conciliacion.movimiento_previsto_id == previsto_id
            )
            .order_by(Conciliacion.id)
        ).all()

        assert len(asociaciones) == 2

        eliminada_id = asociaciones[0].id
        conservada_id = asociaciones[1].id

    response = client.post(
        (
            f"/conciliacion/previstos/{previsto_id}"
            f"/asociaciones/{eliminada_id}/deshacer"
        ),
        data={
            "relaciones_tipo": "previsto",
            "relaciones_id": previsto_id,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.location.endswith(
        f"/conciliacion/relaciones/previsto/{previsto_id}"
    )

    with _sesiones_relaciones(client)() as session:
        assert session.get(
            Conciliacion,
            eliminada_id,
        ) is None

        assert session.get(
            Conciliacion,
            conservada_id,
        ) is not None


def test_relaciones_desde_apunte_no_ofrece_deshacer_bancarios(
    escenario,
):
    client, _ = escenario

    apunte_id = _buscar_id_relaciones(
        client,
        ApunteContable,
        "concepto",
        "APUNTE RELACIONES A",
    )

    response = client.get(
        f"/conciliacion/relaciones/apunte/{apunte_id}"
    )

    assert response.status_code == 200
    assert "Deshacer conciliación (" not in response.text


def test_relaciones_no_permite_eliminar_apunte_con_factura(
    escenario,
):
    client, _ = escenario

    apunte_id = _buscar_id_relaciones(
        client,
        ApunteContable,
        "concepto",
        "APUNTE RELACIONES A",
    )

    response = client.get(
        f"/conciliacion/relaciones/apunte/{apunte_id}"
    )

    assert response.status_code == 200
    assert (
        f'href="/contabilidad/{apunte_id}/eliminar"'
        not in response.text
    )


def test_eliminacion_directa_apunte_con_factura_se_rechaza(
    escenario,
):
    client, _ = escenario

    apunte_id = _buscar_id_relaciones(
        client,
        ApunteContable,
        "concepto",
        "APUNTE RELACIONES A",
    )

    response = client.post(
        f"/contabilidad/{apunte_id}/eliminar"
    )

    assert response.status_code == 400
    assert "factura vinculada" in response.text

    with _sesiones_relaciones(client)() as session:
        assert session.get(
            ApunteContable,
            apunte_id,
        ) is not None


def test_relaciones_no_muestra_eliminar_factura_conciliada(
    escenario,
):
    client, _ = escenario

    apunte_id = _buscar_id_relaciones(
        client,
        ApunteContable,
        "concepto",
        "APUNTE RELACIONES A",
    )

    factura_id = _buscar_id_relaciones(
        client,
        Factura,
        "numero_factura",
        "01/2026REL",
    )

    response = client.get(
        f"/conciliacion/relaciones/apunte/{apunte_id}"
    )

    assert response.status_code == 200

    assert (
        f'action="/facturacion/facturas/{factura_id}/eliminar"'
        not in response.text
    )


def test_relaciones_ofrece_eliminar_ultima_factura_pendiente(
    escenario,
):
    client, _ = escenario

    previsto_id = _buscar_id_relaciones(
        client,
        MovimientoPrevisto,
        "concepto",
        "PREVISTO RELACIONES B",
    )

    factura_id = _buscar_id_relaciones(
        client,
        Factura,
        "numero_factura",
        "02/2026REL",
    )

    with _sesiones_relaciones(client)() as session:
        previsto = session.get(
            MovimientoPrevisto,
            previsto_id,
        )

        for asociacion in list(previsto.conciliaciones):
            deshacer_asociacion_bancaria(asociacion)

        session.commit()

    response = client.get(
        f"/conciliacion/relaciones/previsto/{previsto_id}"
    )

    assert response.status_code == 200

    assert (
        f'action="/facturacion/facturas/{factura_id}/eliminar"'
        in response.text
    )


def test_eliminar_factura_pendiente_elimina_sus_relaciones(
    escenario,
):
    client, _ = escenario

    previsto_id = _buscar_id_relaciones(
        client,
        MovimientoPrevisto,
        "concepto",
        "PREVISTO RELACIONES B",
    )

    apunte_id = _buscar_id_relaciones(
        client,
        ApunteContable,
        "concepto",
        "APUNTE RELACIONES B",
    )

    factura_id = _buscar_id_relaciones(
        client,
        Factura,
        "numero_factura",
        "02/2026REL",
    )

    with _sesiones_relaciones(client)() as session:
        previsto = session.get(
            MovimientoPrevisto,
            previsto_id,
        )

        for asociacion in list(previsto.conciliaciones):
            deshacer_asociacion_bancaria(asociacion)

        session.commit()

    response = client.post(
        f"/facturacion/facturas/{factura_id}/eliminar",
        follow_redirects=False,
    )

    assert response.status_code == 302

    with _sesiones_relaciones(client)() as session:
        assert session.get(Factura, factura_id) is None
        assert session.get(ApunteContable, apunte_id) is None
        assert session.get(MovimientoPrevisto, previsto_id) is None


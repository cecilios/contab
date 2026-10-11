"""Pruebas de la lógica de negocio de los reembolsos."""

import pytest

from datetime import date
from sqlalchemy.exc import IntegrityError

from contab.models import (
    Contrato,
    ImputacionContrato,
    Inmueble,
    SolicitudReembolso,
    SolicitudReembolsoLinea,
)
from contab.config import CategoriaContable
from contab.contabilidad.services import (
    buscar_gastos_repercutibles_pendientes,
    crear_apunte_contable,
)
from contab.reembolsos.services import (
    ReembolsoError,
    preparar_solicitud_reembolso,
)


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


def _contrato(
    inmueble: Inmueble,
    *,
    fecha_inicio: date = date(2026, 1, 1),
    fecha_fin: date | None = None,
) -> Contrato:
    return Contrato(
        inmueble=inmueble,
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=(
            fecha_fin
            if fecha_fin is not None
            else date(2035, 12, 31)
        ),
        fecha_fin=fecha_fin,
        genera_factura=True,
        fecha_inicio_facturacion=fecha_inicio,
        fianza=0,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )


def test_preparar_solicitud_reembolso_un_gasto(
    session,
) -> None:
    inmueble = Inmueble(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato(inmueble)

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad octubre",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    session.add_all([
        inmueble,
        contrato,
        apunte,
    ])
    session.commit()

    gastos = buscar_gastos_repercutibles_pendientes(
        session,
        contrato=contrato,
    )

    solicitud = preparar_solicitud_reembolso(
        contrato=contrato,
        gastos=gastos,
    )

    assert solicitud.contrato is contrato
    assert solicitud.total == 10000
    assert len(solicitud.lineas) == 1

    linea = solicitud.lineas[0]

    assert linea.apunte is apunte
    assert linea.concepto == "Comunidad octubre"
    assert linea.importe_total == 10000
    assert linea.importe_aplicable == 10000
    assert linea.imputacion.contrato is contrato


def test_preparar_solicitud_reembolso_subdividido_usa_importe_distribuido(
    session,
) -> None:
    inmueble = Inmueble(
        referencia="EDIFICIO",
        tipo="T",
        codigo_facturacion="E",
        descripcion="Edificio",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    local_a = Inmueble(
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="A",
        descripcion="Local A",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=6000,
        inmueble_padre=inmueble,
    )

    Inmueble(
        referencia="LOCAL-B",
        tipo="L",
        codigo_facturacion="B",
        descripcion="Local B",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=4000,
        inmueble_padre=inmueble,
    )

    contrato = _contrato(local_a)

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad edificio",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    session.add_all([
        inmueble,
        contrato,
        apunte,
    ])
    session.commit()

    gastos = buscar_gastos_repercutibles_pendientes(
        session,
        contrato=contrato,
    )

    solicitud = preparar_solicitud_reembolso(
        contrato=contrato,
        gastos=gastos,
    )

    assert solicitud.total == 6000
    assert len(solicitud.lineas) == 1

    linea = solicitud.lineas[0]

    assert linea.apunte is apunte
    assert linea.concepto == "Comunidad edificio"
    assert linea.importe_total == 10000
    assert linea.importe_aplicable == 6000

    assert linea.imputacion.apunte is None
    assert (
        linea.imputacion
        .distribucion_apunte
        .inmueble
        is local_a
    )


def test_preparar_solicitud_reembolso_suma_gastos_seleccionados(
    session,
) -> None:
    inmueble = Inmueble(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato(inmueble)

    for concepto, importe in (
        ("Agua", 3500),
        ("Comunidad", 10000),
    ):
        session.add(
            crear_apunte_contable(
                inmueble=inmueble,
                categorias=_categorias_gastos(),
                fecha=date(2026, 10, 15),
                naturaleza="GASTO",
                categoria="GAS_COMUNIDAD",
                concepto=concepto,
                base=importe,
                tratamiento="REPERCUTIR",
            )
        )

    session.add_all([
        inmueble,
        contrato,
    ])
    session.commit()

    gastos = buscar_gastos_repercutibles_pendientes(
        session,
        contrato=contrato,
    )

    solicitud = preparar_solicitud_reembolso(
        contrato=contrato,
        gastos=gastos,
    )

    assert solicitud.total == 13500
    assert [
        linea.importe_aplicable
        for linea in solicitud.lineas
    ] == [
        3500,
        10000,
    ]


def test_preparar_solicitud_reembolso_rechaza_seleccion_vacia(
    contrato,
) -> None:
    with pytest.raises(
        ReembolsoError,
        match="al menos un gasto",
    ):
        preparar_solicitud_reembolso(
            contrato=contrato,
            gastos=[],
        )


def test_preparar_solicitud_reembolso_rechaza_otro_contrato(
    session,
) -> None:
    inmueble_1 = Inmueble(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local 1",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    inmueble_2 = Inmueble(
        referencia="LOCAL-2",
        tipo="L",
        codigo_facturacion="L2",
        descripcion="Local 2",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato_1 = _contrato(inmueble_1)
    contrato_2 = _contrato(inmueble_2)

    apunte = crear_apunte_contable(
        inmueble=inmueble_1,
        categorias=_categorias_gastos(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    session.add_all([
        inmueble_1,
        inmueble_2,
        contrato_1,
        contrato_2,
        apunte,
    ])
    session.commit()

    gastos = buscar_gastos_repercutibles_pendientes(
        session,
        contrato=contrato_1,
    )

    with pytest.raises(
        ReembolsoError,
        match="mismo contrato",
    ):
        preparar_solicitud_reembolso(
            contrato=contrato_2,
            gastos=gastos,
        )


def test_preparar_solicitud_reembolso_rechaza_gasto_duplicado(
    session,
) -> None:
    inmueble = Inmueble(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato(inmueble)

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    session.add_all([
        inmueble,
        contrato,
        apunte,
    ])
    session.commit()

    gastos = buscar_gastos_repercutibles_pendientes(
        session,
        contrato=contrato,
    )

    with pytest.raises(
        ReembolsoError,
        match="dos veces",
    ):
        preparar_solicitud_reembolso(
            contrato=contrato,
            gastos=[
                gastos[0],
                gastos[0],
            ],
        )


def test_solicitud_reembolso_persiste_linea_de_apunte(
    session,
) -> None:
    inmueble = Inmueble(
        referencia="LOCAL-1",
        tipo="L",
        codigo_facturacion="L1",
        descripcion="Local",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato(inmueble)

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad octubre",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    solicitud = SolicitudReembolso(
        contrato=contrato,
        fecha_envio=date(2026, 10, 20),
    )

    solicitud.lineas.append(
        SolicitudReembolsoLinea(
            apunte=apunte,
            concepto="Comunidad octubre",
            importe=10000,
        )
    )

    session.add_all([
        inmueble,
        contrato,
        apunte,
        solicitud,
    ])
    session.commit()

    assert solicitud.id is not None
    assert solicitud.contrato is contrato
    assert solicitud.fecha_envio == date(2026, 10, 20)

    assert len(solicitud.lineas) == 1

    linea = solicitud.lineas[0]

    assert linea.apunte is apunte
    assert linea.distribucion_apunte is None
    assert linea.concepto == "Comunidad octubre"
    assert linea.importe == 10000
    assert solicitud.total == 10000


def test_solicitud_reembolso_persiste_linea_de_distribucion(
    session,
) -> None:
    inmueble = Inmueble(
        referencia="EDIFICIO",
        tipo="T",
        codigo_facturacion="E",
        descripcion="Edificio",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    local_a = Inmueble(
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="A",
        descripcion="Local A",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=6000,
        inmueble_padre=inmueble,
    )

    Inmueble(
        referencia="LOCAL-B",
        tipo="L",
        codigo_facturacion="B",
        descripcion="Local B",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=4000,
        inmueble_padre=inmueble,
    )

    contrato = _contrato(local_a)

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad edificio",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    distribucion = next(
        distribucion
        for distribucion in apunte.distribuciones
        if distribucion.inmueble is local_a
    )

    solicitud = SolicitudReembolso(
        contrato=contrato,
        fecha_envio=date(2026, 10, 20),
    )

    solicitud.lineas.append(
        SolicitudReembolsoLinea(
            distribucion_apunte=distribucion,
            concepto="Comunidad edificio",
            importe=6000,
        )
    )

    session.add_all([
        inmueble,
        contrato,
        apunte,
        solicitud,
    ])
    session.commit()

    linea = solicitud.lineas[0]

    assert linea.apunte is None
    assert linea.distribucion_apunte is distribucion
    assert linea.importe == 6000
    assert solicitud.total == 6000


@pytest.mark.parametrize(
    "usar_ambos",
    [
        False,
        True,
    ],
)
def test_linea_solicitud_reembolso_exige_un_origen(
    session,
    usar_ambos: bool,
) -> None:
    inmueble = Inmueble(
        referencia="EDIFICIO",
        tipo="T",
        codigo_facturacion="E",
        descripcion="Edificio",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    local_a = Inmueble(
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="A",
        descripcion="Local A",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
        participacion=10000,
        inmueble_padre=inmueble,
    )

    contrato = _contrato(local_a)

    apunte = crear_apunte_contable(
        inmueble=inmueble,
        categorias=_categorias_gastos(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    solicitud = SolicitudReembolso(
        contrato=contrato,
        fecha_envio=date(2026, 10, 20),
    )

    distribucion = apunte.distribuciones[0]

    linea = SolicitudReembolsoLinea(
        solicitud=solicitud,
        apunte=apunte if usar_ambos else None,
        distribucion_apunte=(
            distribucion
            if usar_ambos
            else None
        ),
        concepto="Comunidad",
        importe=10000,
    )

    session.add_all([
        inmueble,
        contrato,
        apunte,
        solicitud,
        linea,
    ])

    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()


@pytest.mark.parametrize(
    "importe",
    [
        0,
        -1,
    ],
)
def test_linea_solicitud_reembolso_exige_importe_positivo(
    session,
    contrato,
    importe: int,
) -> None:
    apunte = crear_apunte_contable(
        inmueble=contrato.inmueble,
        categorias=_categorias_gastos(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    solicitud = SolicitudReembolso(
        contrato=contrato,
        fecha_envio=date(2026, 10, 20),
    )

    solicitud.lineas.append(
        SolicitudReembolsoLinea(
            apunte=apunte,
            concepto="Comunidad",
            importe=importe,
        )
    )

    session.add(solicitud)

    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()


def test_solicitud_reembolso_no_duplica_apunte(
    session,
    contrato,
) -> None:
    apunte = crear_apunte_contable(
        inmueble=contrato.inmueble,
        categorias=_categorias_gastos(),
        fecha=date(2026, 10, 15),
        naturaleza="GASTO",
        categoria="GAS_COMUNIDAD",
        concepto="Comunidad",
        base=10000,
        tratamiento="REPERCUTIR",
    )

    solicitud = SolicitudReembolso(
        contrato=contrato,
        fecha_envio=date(2026, 10, 20),
    )

    solicitud.lineas.extend([
        SolicitudReembolsoLinea(
            apunte=apunte,
            concepto="Comunidad",
            importe=5000,
        ),
        SolicitudReembolsoLinea(
            apunte=apunte,
            concepto="Comunidad",
            importe=5000,
        ),
    ])

    session.add(solicitud)

    with pytest.raises(IntegrityError):
        session.flush()

    session.rollback()


def test_preparar_solicitud_explica_prorrateo_por_frontera_contrato(
    session,
) -> None:
    inmueble = Inmueble(
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="A",
        descripcion="Local A",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato(
        inmueble,
        fecha_inicio=date(2026, 7, 1),
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
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

    session.add_all([
        inmueble,
        contrato,
        apunte,
    ])
    session.commit()

    gastos = buscar_gastos_repercutibles_pendientes(
        session,
        contrato=contrato,
    )

    solicitud = preparar_solicitud_reembolso(
        contrato=contrato,
        gastos=gastos,
    )

    linea = solicitud.lineas[0]

    assert linea.importe_total == 2839
    assert linea.importe_aplicable == 1443
    assert linea.reparto_espacial is None

    assert linea.prorrateo_temporal is not None
    assert (
        linea.prorrateo_temporal.dias_totales
        == 61
    )
    assert (
        linea.prorrateo_temporal.dias_contrato
        == 31
    )
    assert (
        linea.prorrateo_temporal.importe_base
        == 2839
    )
    assert (
        linea.prorrateo_temporal.importe_resultante
        == 1443
    )


def test_preparar_solicitud_no_explica_periodo_completamente_cubierto(
    session,
) -> None:
    inmueble = Inmueble(
        referencia="LOCAL-A",
        tipo="L",
        codigo_facturacion="A",
        descripcion="Local A",
        direccion="Dirección",
        poblacion="Pontevedra",
        provincia="Pontevedra",
    )

    contrato = _contrato(
        inmueble,
        fecha_inicio=date(2026, 1, 1),
    )

    apunte = crear_apunte_contable(
        inmueble=inmueble,
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

    session.add_all([
        inmueble,
        contrato,
        apunte,
    ])
    session.commit()

    gastos = buscar_gastos_repercutibles_pendientes(
        session,
        contrato=contrato,
    )

    solicitud = preparar_solicitud_reembolso(
        contrato=contrato,
        gastos=gastos,
    )

    assert len(solicitud.lineas) == 1

    linea = solicitud.lineas[0]

    assert linea.importe_total == 2839
    assert linea.importe_aplicable == 2839
    assert linea.reparto_espacial is None
    assert linea.prorrateo_temporal is None



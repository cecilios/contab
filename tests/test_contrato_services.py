"""Pruebas de la lógica de negocio relacionada con contratos y rentas."""

from datetime import date

import pytest

from contab.models import (
    AjusteRenta,
    Contrato,
    ContratoInquilino,
    Inquilino,
    RentaContrato,
    RevisionRenta,
)

from contab.contratos.services import (
    AjusteRentaError,
    ContratoError,
    RentaContratoError,
    RentaFacturableError,
    RentaNoDisponibleError,
    RevisionRentaError,
    crear_ajuste_renta,
    crear_contrato,
    crear_renta_contrato,
    crear_revision_renta,
    renta_facturable,
    renta_vigente,
    resolver_revision_renta,
)


def test_renta_vigente_devuelve_renta_inicial(session, contrato) -> None:
    """Comprueba que se obtiene la renta inicial antes de cualquier revisión."""
    renta = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 2, 1),
        importe=100000,
    )

    session.add(renta)
    session.commit()

    resultado = renta_vigente(contrato, date(2026, 9, 15))

    assert resultado is renta


def test_renta_vigente_devuelve_ultima_renta_aplicable(session, contrato) -> None:
    """Comprueba que se utiliza la última renta vigente en la fecha consultada."""
    renta_inicial = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 2, 1),
        importe=100000,
    )
    renta_revisada = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2027, 2, 1),
        importe=102500,
    )

    session.add_all([renta_inicial, renta_revisada])
    session.commit()

    resultado = renta_vigente(contrato, date(2027, 8, 20))

    assert resultado is renta_revisada
    assert resultado.importe == 102500


def test_renta_vigente_respeta_fecha_exacta_de_cambio(session, contrato) -> None:
    """Comprueba que una nueva renta entra en vigor exactamente en fecha_desde."""
    renta_inicial = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 2, 1),
        importe=100000,
    )
    renta_revisada = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2027, 2, 1),
        importe=102500,
    )

    session.add_all([renta_inicial, renta_revisada])
    session.commit()

    assert renta_vigente(contrato, date(2027, 1, 31)) is renta_inicial
    assert renta_vigente(contrato, date(2027, 2, 1)) is renta_revisada


def test_renta_vigente_falla_si_no_hay_renta_aplicable(session, contrato) -> None:
    """Comprueba que consultar antes de la primera renta produce un error."""
    renta = RentaContrato(
        contrato=contrato,
        fecha_desde=date(2026, 2, 1),
        importe=100000,
    )

    session.add(renta)
    session.commit()

    with pytest.raises(RentaNoDisponibleError):
        renta_vigente(contrato, date(2026, 1, 15))


def test_renta_facturable_sin_ajuste(session, contrato) -> None:
    """Comprueba que sin ajustes se factura la renta ordinaria vigente."""
    session.add(
        RentaContrato(
            contrato=contrato,
            fecha_desde=date(2026, 2, 1),
            importe=100000,
        )
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 9, 1)) == 100000


def test_renta_facturable_con_reduccion_porcentual(session, contrato) -> None:
    """Comprueba que una reducción porcentual se aplica sobre la renta vigente."""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=100000,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 10, 1),
                tipo="REDUCCION_PORCENTUAL",
                valor=4000,
            ),
        ]
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 7, 1)) == 60000


def test_renta_facturable_con_reduccion_fija(session, contrato) -> None:
    """Comprueba que una reducción fija resta su importe a la renta vigente."""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=100000,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 10, 1),
                tipo="REDUCCION_FIJA",
                valor=20000,
            ),
        ]
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 7, 1)) == 80000


def test_renta_facturable_con_importe_fijo(session, contrato) -> None:
    """Comprueba que un importe fijo sustituye temporalmente la renta ordinaria."""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=100000,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 6, 1),
                tipo="IMPORTE_FIJO",
                valor=5000,
            ),
        ]
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 5, 1)) == 5000


def test_reduccion_porcentual_se_aplica_a_renta_revisada(session, contrato) -> None:
    """Comprueba que el ajuste porcentual se aplica a una nueva renta revisada."""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=100000,
            ),
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 7, 1),
                importe=102300,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 10, 1),
                tipo="REDUCCION_PORCENTUAL",
                valor=4000,
            ),
        ]
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 8, 1)) == 61380


def test_reduccion_fija_no_puede_producir_renta_negativa(session, contrato) -> None:
    """Comprueba que una reducción fija no puede producir renta negativa."""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=10000,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 10, 1),
                tipo="REDUCCION_FIJA",
                valor=20000,
            ),
        ]
    )
    session.commit()

    with pytest.raises(RentaFacturableError):
        renta_facturable(contrato, date(2026, 7, 1))


def test_renta_facturable_redondea_al_centimo_arriba(session, contrato) -> None:
    """Comprueba que los cálculos monetarios redondean medio céntimo hacia arriba:
       reduccion 50%, nueva renta 100,01 € × 50 % = 50,005 €  -> 50,01 €)"""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=10001,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 10, 1),
                tipo="REDUCCION_PORCENTUAL",
                valor=5000,
            ),
        ]
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 7, 1)) == 5001




def test_renta_facturable_redondea_al_centimo_abajo(session, contrato) -> None:
    """Comprueba que los cálculos monetarios redondean menos de medio céntimo
       hacia abajo: reduccion 75%, nueva renta  100,01 € × 25 % = 25,0025  -> 25,00 €)"""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=date(2026, 2, 1),
                importe=10001,
            ),
            AjusteRenta(
                contrato=contrato,
                fecha_desde=date(2026, 3, 1),
                fecha_hasta=date(2026, 10, 1),
                tipo="REDUCCION_PORCENTUAL",
                valor=7500,
            ),
        ]
    )
    session.commit()

    assert renta_facturable(contrato, date(2026, 7, 1)) == 2500


def test_crear_ajuste_renta_valido(contrato) -> None:
    """Comprueba que se crea un ajuste válido sin persistirlo ni hacer commit."""
    ajuste = crear_ajuste_renta(
        contrato=contrato,
        fecha_desde=date(2026, 3, 1),
        fecha_hasta=date(2026, 6, 1),
        tipo="REDUCCION_PORCENTUAL",
        valor=4000,
    )

    assert ajuste.contrato is contrato
    assert ajuste.fecha_desde == date(2026, 3, 1)
    assert ajuste.fecha_hasta == date(2026, 6, 1)
    assert ajuste.tipo == "REDUCCION_PORCENTUAL"
    assert ajuste.valor == 4000
    assert ajuste.id is None


def test_crear_ajuste_renta_rechaza_porcentaje_fuera_de_rango(contrato) -> None:
    """Comprueba que una reducción porcentual debe estar entre 0 % y 100 %."""
    with pytest.raises(AjusteRentaError):
        crear_ajuste_renta(
            contrato=contrato,
            fecha_desde=date(2026, 3, 1),
            fecha_hasta=date(2026, 6, 1),
            tipo="REDUCCION_PORCENTUAL",
            valor=10001,
        )


def test_crear_ajuste_renta_rechaza_importe_negativo(contrato) -> None:
    """Comprueba que una reducción fija o importe fijo no puede ser negativo."""
    with pytest.raises(AjusteRentaError):
        crear_ajuste_renta(
            contrato=contrato,
            fecha_desde=date(2026, 3, 1),
            fecha_hasta=date(2026, 6, 1),
            tipo="REDUCCION_FIJA",
            valor=-1,
        )


def test_crear_ajuste_renta_rechaza_tipo_desconocido(contrato) -> None:
    """Comprueba que sólo se admiten los tipos de ajuste definidos."""
    with pytest.raises(AjusteRentaError):
        crear_ajuste_renta(
            contrato=contrato,
            fecha_desde=date(2026, 3, 1),
            fecha_hasta=date(2026, 6, 1),
            tipo="DESCONOCIDO",
            valor=1000,
        )


def test_crear_ajuste_renta_rechaza_fechas_no_mensuales(contrato) -> None:
    """Comprueba que las fechas de un ajuste deben corresponder al día 1."""
    with pytest.raises(AjusteRentaError):
        crear_ajuste_renta(
            contrato=contrato,
            fecha_desde=date(2026, 3, 15),
            fecha_hasta=date(2026, 6, 1),
            tipo="IMPORTE_FIJO",
            valor=5000,
        )


def test_crear_ajuste_renta_rechaza_inicio_anterior_al_contrato(contrato) -> None:
    """Comprueba que un ajuste no puede comenzar antes que el contrato."""
    with pytest.raises(AjusteRentaError):
        crear_ajuste_renta(
            contrato=contrato,
            fecha_desde=date(2025, 12, 1),
            fecha_hasta=date(2026, 2, 1),
            tipo="IMPORTE_FIJO",
            valor=5000,
        )


def test_crear_ajuste_renta_rechaza_solapamiento(contrato) -> None:
    """Comprueba que no pueden existir dos ajustes simultáneos."""
    contrato.ajustes_renta.append(
        AjusteRenta(
            fecha_desde=date(2026, 3, 1),
            fecha_hasta=date(2026, 6, 1),
            tipo="REDUCCION_PORCENTUAL",
            valor=4000,
        )
    )

    with pytest.raises(AjusteRentaError):
        crear_ajuste_renta(
            contrato=contrato,
            fecha_desde=date(2026, 5, 1),
            fecha_hasta=date(2026, 8, 1),
            tipo="IMPORTE_FIJO",
            valor=5000,
        )


def test_crear_primera_renta_con_fecha_inicio_contrato(contrato) -> None:
    """Comprueba que la primera renta comienza exactamente al inicio del contrato."""
    renta = crear_renta_contrato(
        contrato=contrato,
        fecha_desde=contrato.fecha_inicio,
        importe=100000,
    )

    assert renta.contrato is contrato
    assert renta.fecha_desde == contrato.fecha_inicio
    assert renta.importe == 100000
    assert renta.id is None


def test_crear_primera_renta_rechaza_fecha_distinta_al_inicio(contrato) -> None:
    """Comprueba que la primera renta debe comenzar en la fecha inicial del contrato."""
    with pytest.raises(RentaContratoError):
        crear_renta_contrato(
            contrato=contrato,
            fecha_desde=date(2026, 2, 1),
            importe=100000,
        )


def test_crear_renta_posterior_admite_dia_primero(contrato) -> None:
    """Comprueba que una renta posterior puede comenzar el primer día del mes."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    renta = crear_renta_contrato(
        contrato=contrato,
        fecha_desde=date(2027, 2, 1),
        importe=102300,
    )

    assert renta.fecha_desde == date(2027, 2, 1)
    assert renta.importe == 102300


def test_crear_renta_posterior_rechaza_fecha_que_no_sea_dia_primero(contrato) -> None:
    """Comprueba que las rentas posteriores deben comenzar el día 1 del mes."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    with pytest.raises(RentaContratoError):
        crear_renta_contrato(
            contrato=contrato,
            fecha_desde=date(2027, 2, 15),
            importe=102300,
        )


def test_crear_renta_rechaza_importe_negativo(contrato) -> None:
    """Comprueba que una renta contractual no puede tener importe negativo."""
    with pytest.raises(RentaContratoError):
        crear_renta_contrato(
            contrato=contrato,
            fecha_desde=contrato.fecha_inicio,
            importe=-1,
        )


def test_crear_renta_rechaza_fecha_repetida(contrato) -> None:
    """Comprueba que no pueden existir dos rentas con la misma fecha de inicio."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=100000,
        )
    )

    with pytest.raises(RentaContratoError):
        crear_renta_contrato(
            contrato=contrato,
            fecha_desde=contrato.fecha_inicio,
            importe=110000,
        )


def test_crear_revision_renta_pendiente(contrato) -> None:
    """Comprueba que una revisión nueva se crea pendiente por defecto."""
    revision = crear_revision_renta(
        contrato=contrato,
        fecha_prevista=date(2027, 2, 1),
        metodo="IPC_NACIONAL",
    )

    assert revision.contrato is contrato
    assert revision.fecha_prevista == date(2027, 2, 1)
    assert revision.metodo == "IPC_NACIONAL"
    assert revision.estado == "PENDIENTE"
    assert revision.porcentaje_aplicado is None
    assert revision.fecha_resolucion is None
    assert revision.id is None


def test_crear_revision_rechaza_fecha_que_no_sea_dia_primero(contrato) -> None:
    """Comprueba que la fecha prevista de revisión debe ser día 1."""
    with pytest.raises(RevisionRentaError):
        crear_revision_renta(
            contrato=contrato,
            fecha_prevista=date(2027, 2, 15),
            metodo="IPC_NACIONAL",
        )


def test_crear_revision_rechaza_fecha_anterior_al_contrato(contrato) -> None:
    """Comprueba que una revisión no puede preceder al inicio del contrato."""
    with pytest.raises(RevisionRentaError):
        crear_revision_renta(
            contrato=contrato,
            fecha_prevista=date(2025, 12, 1),
            metodo="IPC_NACIONAL",
        )


def test_crear_revision_rechaza_metodo_vacio(contrato) -> None:
    """Comprueba que toda revisión debe indicar un método de actualización."""
    with pytest.raises(RevisionRentaError):
        crear_revision_renta(
            contrato=contrato,
            fecha_prevista=date(2027, 2, 1),
            metodo="",
        )


def test_crear_revision_rechaza_fecha_repetida(contrato) -> None:
    """Comprueba que no puede haber dos revisiones previstas en la misma fecha."""
    contrato.revisiones_renta.append(
        RevisionRenta(
            fecha_prevista=date(2027, 2, 1),
            metodo="IPC_NACIONAL",
        )
    )

    with pytest.raises(RevisionRentaError):
        crear_revision_renta(
            contrato=contrato,
            fecha_prevista=date(2027, 2, 1),
            metodo="IPC_REGIONAL",
        )


def test_resolver_revision_aplicada_crea_nueva_renta(session, contrato) -> None:
    """Comprueba que aplicar una revisión crea la nueva renta ordinaria."""
    renta = RentaContrato(
        contrato=contrato,
        fecha_desde=contrato.fecha_inicio,
        importe=100000,
    )
    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 2, 1),
        metodo="IPC_NACIONAL",
    )

    session.add_all([renta, revision])
    session.commit()

    nueva_renta, siguiente_revision = resolver_revision_renta(
        revision=revision,
        fecha_resolucion=date(2027, 3, 10),
        aplicar=True,
        porcentaje_aplicado=230,
    )

    assert revision.estado == "APLICADA"
    assert revision.porcentaje_aplicado == 230
    assert revision.fecha_resolucion == date(2027, 3, 10)

    assert nueva_renta is not None
    assert nueva_renta.fecha_desde == date(2027, 2, 1)
    assert nueva_renta.importe == 102300

    assert siguiente_revision.fecha_prevista == date(2028, 2, 1)
    assert siguiente_revision.metodo == "IPC_NACIONAL"
    assert siguiente_revision.estado == "PENDIENTE"


def test_resolver_revision_aplicada_admite_porcentaje_negativo(
    session, contrato
) -> None:
    """Comprueba que una revisión negativa reduce correctamente la renta."""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=contrato.fecha_inicio,
                importe=100000,
            ),
            RevisionRenta(
                contrato=contrato,
                fecha_prevista=date(2027, 2, 1),
                metodo="IPC_NACIONAL",
            ),
        ]
    )
    session.commit()

    revision = contrato.revisiones_renta[0]

    nueva_renta, _ = resolver_revision_renta(
        revision=revision,
        fecha_resolucion=date(2027, 3, 10),
        aplicar=True,
        porcentaje_aplicado=-125,
    )

    assert nueva_renta is not None
    assert nueva_renta.importe == 98750


def test_resolver_revision_redondea_nueva_renta_al_centimo(
    session, contrato
) -> None:
    """La nueva renta usa el redondeo contable al céntimo.
       Comprueba  que será 100,01 € × 1,5 = 150,015 € → 150,02 €"""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=contrato.fecha_inicio,
                importe=10001,
            ),
            RevisionRenta(
                contrato=contrato,
                fecha_prevista=date(2027, 2, 1),
                metodo="IPC_NACIONAL",
            ),
        ]
    )
    session.commit()

    revision = contrato.revisiones_renta[0]

    nueva_renta, _ = resolver_revision_renta(
        revision=revision,
        fecha_resolucion=date(2027, 3, 10),
        aplicar=True,
        porcentaje_aplicado=5000,
    )

    assert nueva_renta is not None
    assert nueva_renta.importe == 15002


def test_resolver_revision_no_aplicada_no_crea_renta(session, contrato) -> None:
    """Comprueba que una revisión no aplicada conserva la renta existente."""
    session.add_all(
        [
            RentaContrato(
                contrato=contrato,
                fecha_desde=contrato.fecha_inicio,
                importe=100000,
            ),
            RevisionRenta(
                contrato=contrato,
                fecha_prevista=date(2027, 2, 1),
                metodo="IPC_NACIONAL",
            ),
        ]
    )
    session.commit()

    revision = contrato.revisiones_renta[0]

    nueva_renta, siguiente_revision = resolver_revision_renta(
        revision=revision,
        fecha_resolucion=date(2027, 2, 20),
        aplicar=False,
        porcentaje_aplicado=None,
    )

    assert revision.estado == "NO_APLICADA"
    assert revision.porcentaje_aplicado is None
    assert revision.fecha_resolucion == date(2027, 2, 20)

    assert nueva_renta is None
    assert siguiente_revision.fecha_prevista == date(2028, 2, 1)


def test_resolver_revision_rechaza_revision_ya_resuelta(session, contrato) -> None:
    """Comprueba que una revisión sólo puede resolverse una vez."""
    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 2, 1),
        metodo="IPC_NACIONAL",
        estado="NO_APLICADA",
        fecha_resolucion=date(2027, 2, 20),
    )

    session.add(revision)
    session.commit()

    with pytest.raises(RevisionRentaError):
        resolver_revision_renta(
            revision=revision,
            fecha_resolucion=date(2027, 3, 1),
            aplicar=True,
            porcentaje_aplicado=200,
        )


def test_resolver_revision_aplicada_requiere_porcentaje(
    session, contrato
) -> None:
    """Comprueba que una revisión aplicada necesita un porcentaje."""
    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 2, 1),
        metodo="IPC_NACIONAL",
    )

    session.add(revision)
    session.commit()

    with pytest.raises(RevisionRentaError):
        resolver_revision_renta(
            revision=revision,
            fecha_resolucion=date(2027, 3, 1),
            aplicar=True,
            porcentaje_aplicado=None,
        )


def test_resolver_revision_no_aplicada_rechaza_porcentaje(
    session, contrato
) -> None:
    """Comprueba que una revisión no aplicada no admite porcentaje."""
    revision = RevisionRenta(
        contrato=contrato,
        fecha_prevista=date(2027, 2, 1),
        metodo="IPC_NACIONAL",
    )

    session.add(revision)
    session.commit()

    with pytest.raises(RevisionRentaError):
        resolver_revision_renta(
            revision=revision,
            fecha_resolucion=date(2027, 3, 1),
            aplicar=False,
            porcentaje_aplicado=200,
        )


def test_crear_contrato_completo(inmueble) -> None:
    """Comprueba que el alta prepara contrato, titulares, renta y revisión inicial."""
    titular_1 = Inquilino(
        nombre="Ana Pérez",
        nif="11111111A",
    )
    titular_2 = Inquilino(
        nombre="Luis García",
        nif="22222222B",
    )

    contrato = crear_contrato(
        inmueble=inmueble,
        titulares=[titular_1, titular_2],
        fecha_inicio=date(2026, 6, 15),
        fecha_vencimiento=date(2031, 6, 14),
        fecha_inicio_facturacion=date(2026, 9, 1),
        fianza=200000,
        iva_porcentaje=2100,
        retencion_porcentaje=1900,
        direccion_facturacion="Dirección de facturación",
        codigo_postal_facturacion="36001",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler del local",
        renta_inicial=100000,
        fecha_primera_revision=date(2027, 6, 1),
        metodo_revision="IPC_NACIONAL",
    )

    assert contrato.id is None
    assert contrato.inmueble is inmueble
    assert len(contrato.titulares) == 2
    assert contrato.titulares[0].inquilino is titular_1
    assert contrato.titulares[0].orden == 1
    assert contrato.titulares[1].inquilino is titular_2
    assert contrato.titulares[1].orden == 2

    assert len(contrato.rentas) == 1
    assert contrato.rentas[0].fecha_desde == date(2026, 6, 15)
    assert contrato.rentas[0].importe == 100000

    assert len(contrato.revisiones_renta) == 1
    assert contrato.revisiones_renta[0].fecha_prevista == date(2027, 6, 1)
    assert contrato.revisiones_renta[0].estado == "PENDIENTE"


def test_crear_contrato_requiere_al_menos_un_titular(inmueble) -> None:
    """Comprueba que no puede crearse un contrato sin titulares."""
    with pytest.raises(ContratoError):
        crear_contrato(
            inmueble=inmueble,
            titulares=[],
            fecha_inicio=date(2026, 6, 15),
            fecha_vencimiento=date(2031, 6, 14),
            fecha_inicio_facturacion=date(2026, 9, 1),
            fianza=200000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion=None,
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=100000,
            fecha_primera_revision=date(2027, 6, 1),
            metodo_revision="IPC_NACIONAL",
        )


def test_crear_contrato_rechaza_inicio_facturacion_no_mensual(inmueble) -> None:
    """Comprueba que la facturación debe comenzar el día 1 de un mes."""
    titular = Inquilino(nombre="Ana Pérez", nif="11111111A")

    with pytest.raises(ContratoError):
        crear_contrato(
            inmueble=inmueble,
            titulares=[titular],
            fecha_inicio=date(2026, 6, 15),
            fecha_vencimiento=date(2031, 6, 14),
            fecha_inicio_facturacion=date(2026, 9, 15),
            fianza=200000,
            iva_porcentaje=2100,
            retencion_porcentaje=1900,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion=None,
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=100000,
            fecha_primera_revision=date(2027, 6, 1),
            metodo_revision="IPC_NACIONAL",
        )


def test_crear_contrato_rechaza_otro_contrato_vigente_en_inmueble(
    session, inmueble
) -> None:
    """Comprueba que un inmueble no puede tener dos contratos vigentes."""
    existente = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2025, 1, 1),
        fecha_vencimiento=date(2030, 12, 31),
        fecha_inicio_facturacion=date(2025, 1, 1),
        fianza=100000,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )
    session.add(existente)
    session.commit()

    titular = Inquilino(nombre="Ana Pérez", nif="11111111A")

    with pytest.raises(ContratoError):
        crear_contrato(
            inmueble=inmueble,
            titulares=[titular],
            fecha_inicio=date(2026, 6, 15),
            fecha_vencimiento=date(2031, 6, 14),
            fecha_inicio_facturacion=date(2026, 9, 1),
            fianza=200000,
            iva_porcentaje=0,
            retencion_porcentaje=0,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion=None,
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=100000,
            fecha_primera_revision=date(2027, 6, 1),
            metodo_revision="IPC_NACIONAL",
        )


def test_crear_contrato_rechaza_inmueble_inactivo(inmueble) -> None:
    """Comprueba que no puede crearse un contrato para un inmueble inactivo."""
    inmueble.activo = False
    titular = Inquilino(nombre="Ana Pérez", nif="11111111A")

    with pytest.raises(ContratoError):
        crear_contrato(
            inmueble=inmueble,
            titulares=[titular],
            fecha_inicio=date(2026, 6, 15),
            fecha_vencimiento=date(2031, 6, 14),
            fecha_inicio_facturacion=date(2026, 9, 1),
            fianza=200000,
            iva_porcentaje=0,
            retencion_porcentaje=0,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion=None,
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=100000,
            fecha_primera_revision=date(2027, 6, 1),
            metodo_revision="IPC_NACIONAL",
        )


def test_crear_contrato_rechaza_vencimiento_anterior(inmueble) -> None:
    """Comprueba que el vencimiento no puede ser anterior al inicio."""
    titular = Inquilino(nombre="Ana Pérez", nif="11111111A")

    with pytest.raises(ContratoError):
        crear_contrato(
            inmueble=inmueble,
            titulares=[titular],
            fecha_inicio=date(2026, 6, 15),
            fecha_vencimiento=date(2026, 6, 14),
            fecha_inicio_facturacion=date(2026, 9, 1),
            fianza=200000,
            iva_porcentaje=0,
            retencion_porcentaje=0,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion=None,
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=100000,
            fecha_primera_revision=date(2027, 6, 1),
            metodo_revision="IPC_NACIONAL",
        )


def test_crear_contrato_rechaza_fianza_negativa(inmueble) -> None:
    """Comprueba que la fianza no puede ser negativa."""
    titular = Inquilino(nombre="Ana Pérez", nif="11111111A")

    with pytest.raises(ContratoError):
        crear_contrato(
            inmueble=inmueble,
            titulares=[titular],
            fecha_inicio=date(2026, 6, 15),
            fecha_vencimiento=date(2031, 6, 14),
            fecha_inicio_facturacion=date(2026, 9, 1),
            fianza=-1,
            iva_porcentaje=0,
            retencion_porcentaje=0,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion=None,
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=100000,
            fecha_primera_revision=date(2027, 6, 1),
            metodo_revision="IPC_NACIONAL",
        )


def test_crear_contrato_rechaza_iva_negativo(inmueble) -> None:
    """Comprueba que el porcentaje de IVA no puede ser negativo."""
    titular = Inquilino(nombre="Ana Pérez", nif="11111111A")

    with pytest.raises(ContratoError):
        crear_contrato(
            inmueble=inmueble,
            titulares=[titular],
            fecha_inicio=date(2026, 6, 15),
            fecha_vencimiento=date(2031, 6, 14),
            fecha_inicio_facturacion=date(2026, 9, 1),
            fianza=200000,
            iva_porcentaje=-1,
            retencion_porcentaje=0,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion=None,
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=100000,
            fecha_primera_revision=date(2027, 6, 1),
            metodo_revision="IPC_NACIONAL",
        )


def test_crear_contrato_rechaza_retencion_negativa(inmueble) -> None:
    """Comprueba que la retención no puede ser negativa."""
    titular = Inquilino(nombre="Ana Pérez", nif="11111111A")

    with pytest.raises(ContratoError):
        crear_contrato(
            inmueble=inmueble,
            titulares=[titular],
            fecha_inicio=date(2026, 6, 15),
            fecha_vencimiento=date(2031, 6, 14),
            fecha_inicio_facturacion=date(2026, 9, 1),
            fianza=200000,
            iva_porcentaje=0,
            retencion_porcentaje=-1,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion=None,
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=100000,
            fecha_primera_revision=date(2027, 6, 1),
            metodo_revision="IPC_NACIONAL",
        )


def test_crear_contrato_admite_nuevo_contrato_tras_finalizar_anterior(
    session, inmueble
) -> None:
    """Comprueba que puede crearse un contrato tras finalizar el anterior."""
    anterior = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2020, 1, 1),
        fecha_vencimiento=date(2025, 12, 31),
        fecha_fin=date(2025, 12, 31),
        fecha_inicio_facturacion=date(2020, 1, 1),
        fianza=100000,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )
    session.add(anterior)
    session.commit()

    titular = Inquilino(nombre="Ana Pérez", nif="11111111A")

    nuevo = crear_contrato(
        inmueble=inmueble,
        titulares=[titular],
        fecha_inicio=date(2026, 1, 1),
        fecha_vencimiento=date(2030, 12, 31),
        fecha_inicio_facturacion=date(2026, 1, 1),
        fianza=100000,
        iva_porcentaje=0,
        retencion_porcentaje=0,
        direccion_facturacion="Dirección",
        codigo_postal_facturacion=None,
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
        renta_inicial=100000,
        fecha_primera_revision=date(2027, 1, 1),
        metodo_revision="IPC_NACIONAL",
    )

    assert nuevo.inmueble is inmueble


def test_crear_contrato_rechaza_solapamiento_con_contrato_finalizado(
    session, inmueble
) -> None:
    """Comprueba que un contrato nuevo no puede solaparse con uno ya finalizado."""
    anterior = Contrato(
        inmueble=inmueble,
        fecha_inicio=date(2020, 1, 1),
        fecha_vencimiento=date(2026, 12, 31),
        fecha_fin=date(2026, 6, 30),
        fecha_inicio_facturacion=date(2020, 1, 1),
        fianza=100000,
        direccion_facturacion="Dirección",
        poblacion_facturacion="Pontevedra",
        provincia_facturacion="Pontevedra",
        concepto_factura="Alquiler",
    )
    session.add(anterior)
    session.commit()

    titular = Inquilino(nombre="Ana Pérez", nif="11111111A")

    with pytest.raises(ContratoError):
        crear_contrato(
            inmueble=inmueble,
            titulares=[titular],
            fecha_inicio=date(2026, 6, 1),
            fecha_vencimiento=date(2030, 12, 31),
            fecha_inicio_facturacion=date(2026, 6, 1),
            fianza=100000,
            iva_porcentaje=0,
            retencion_porcentaje=0,
            direccion_facturacion="Dirección",
            codigo_postal_facturacion=None,
            poblacion_facturacion="Pontevedra",
            provincia_facturacion="Pontevedra",
            concepto_factura="Alquiler",
            renta_inicial=100000,
            fecha_primera_revision=date(2027, 6, 1),
            metodo_revision="IPC_NACIONAL",
        )




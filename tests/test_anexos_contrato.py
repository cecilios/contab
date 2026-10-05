from datetime import date

import pytest

from contab.contratos.services import (
    AjusteRentaError,
    ContratoError,
    carencia_vigente,
    crear_ajuste_renta,
    crear_anexo_carencia,
    crear_anexo_prorroga,
    crear_anexo_renta_permanente,
    crear_anexo_renta_temporal,
    renta_facturable,
)

from contab.models import (
    AjusteRenta,
    AnexoContrato,
    RentaContrato,
)


@pytest.fixture
def contrato_con_renta(contrato):
    """Añade al contrato una renta inicial válida."""
    renta = RentaContrato(
        fecha_desde=contrato.fecha_inicio,
        importe=150000,
    )

    contrato.rentas.append(renta)

    return contrato



def test_crear_anexo_prorroga(contrato) -> None:
    """Comprueba que una prórroga amplía el vencimiento y deja trazabilidad."""
    contrato.fecha_vencimiento = date(2030, 9, 14)

    anexo = crear_anexo_prorroga(
        contrato=contrato,
        fecha=date(2030, 6, 1),
        nueva_fecha_vencimiento=date(2035, 9, 14),
        descripcion="Prórroga por cinco años",
    )

    assert isinstance(anexo, AnexoContrato)
    assert anexo.tipo == "PRORROGA"
    assert anexo.fecha == date(2030, 6, 1)
    assert anexo.nueva_fecha_vencimiento == date(2035, 9, 14)
    assert contrato.fecha_vencimiento == date(2035, 9, 14)


def test_crear_anexo_prorroga_rechaza_vencimiento_no_posterior(
    contrato,
) -> None:
    """Comprueba que una prórroga debe ampliar realmente el vencimiento."""
    contrato.fecha_vencimiento = date(2030, 9, 14)

    with pytest.raises(
        ContratoError,
        match="La nueva fecha de vencimiento debe ser posterior",
    ):
        crear_anexo_prorroga(
            contrato=contrato,
            fecha=date(2030, 6, 1),
            nueva_fecha_vencimiento=date(2030, 9, 14),
        )


def test_crear_anexo_prorroga_rechaza_vencimiento_no_posterior(
    contrato,
) -> None:
    """Comprueba que una prórroga debe ampliar realmente el vencimiento."""
    contrato.fecha_vencimiento = date(2030, 9, 14)

    with pytest.raises(
        ContratoError,
        match="La nueva fecha de vencimiento debe ser posterior",
    ):
        crear_anexo_prorroga(
            contrato=contrato,
            fecha=date(2030, 6, 1),
            nueva_fecha_vencimiento=date(2030, 9, 14),
        )


def test_crear_anexo_renta_permanente(contrato_con_renta) -> None:
    """Comprueba que un anexo permanente crea una nueva renta vinculada."""
    contrato = contrato_con_renta
    anexo, renta = crear_anexo_renta_permanente(
        contrato=contrato,
        fecha=date(2028, 5, 20),
        fecha_desde=date(2028, 6, 1),
        importe=175000,
        descripcion="Nueva renta pactada",
    )

    assert anexo.tipo == "CAMBIO_RENTA"
    assert anexo.fecha == date(2028, 5, 20)
    assert anexo.nueva_fecha_vencimiento is None

    assert renta.contrato is contrato
    assert renta.anexo is anexo
    assert renta.fecha_desde == date(2028, 6, 1)
    assert renta.importe == 175000


def test_crear_anexo_renta_permanente_rechaza_fecha_no_mensual(
    contrato_con_renta,
) -> None:
    """Comprueba que una nueva renta permanente comienza el día 1."""
    contrato = contrato_con_renta
    with pytest.raises(
        ContratoError,
        match="día 1 del mes",
    ):        crear_anexo_renta_permanente(
            contrato=contrato,
            fecha=date(2028, 5, 20),
            fecha_desde=date(2028, 6, 15),
            importe=175000,
        )


def test_crear_anexo_renta_temporal(
    contrato_con_renta,
) -> None:
    contrato = contrato_con_renta
    """Comprueba que un anexo temporal crea un ajuste vinculado."""
    anexo, ajuste = crear_anexo_renta_temporal(
        contrato=contrato,
        fecha=date(2028, 5, 20),
        fecha_desde=date(2028, 6, 1),
        fecha_hasta=date(2028, 12, 31),
        tipo="IMPORTE_FIJO",
        valor=120000,
        descripcion="Renta reducida temporalmente",
    )

    assert anexo.tipo == "CAMBIO_RENTA"
    assert anexo.fecha == date(2028, 5, 20)

    assert ajuste.contrato is contrato
    assert ajuste.anexo is anexo
    assert ajuste.fecha_desde == date(2028, 6, 1)
    assert ajuste.fecha_hasta == date(2028, 12, 31)
    assert ajuste.tipo == "IMPORTE_FIJO"
    assert ajuste.valor == 120000



def test_crear_anexo_renta_temporal_rechaza_solapamiento(
    contrato_con_renta,
) -> None:
    """Comprueba que un anexo temporal no puede solaparse con otro ajuste."""
    contrato = contrato_con_renta
    crear_anexo_renta_temporal(
        contrato=contrato,
        fecha=date(2028, 1, 1),
        fecha_desde=date(2028, 2, 1),
        fecha_hasta=date(2028, 6, 30),
        tipo="IMPORTE_FIJO",
        valor=120000,
    )

    with pytest.raises(
        ContratoError,
        match="se solapa con otro ajuste",
    ):
        crear_anexo_renta_temporal(
            contrato=contrato,
            fecha=date(2028, 3, 1),
            fecha_desde=date(2028, 5, 1),
            fecha_hasta=date(2028, 9, 30),
            tipo="IMPORTE_FIJO",
            valor=130000,
        )


def test_crear_ajuste_renta_acepta_periodo_por_meses_completos(contrato) -> None:
    """Comprueba que un ajuste puede abarcar meses completos."""
    ajuste = crear_ajuste_renta(
        contrato=contrato,
        fecha_desde=date(2026, 9, 1),
        fecha_hasta=date(2026, 11, 30),
        tipo="IMPORTE_FIJO",
        valor=120000,
    )

    assert ajuste.fecha_desde == date(2026, 9, 1)
    assert ajuste.fecha_hasta == date(2026, 11, 30)


def test_crear_ajuste_renta_rechaza_fecha_desde_que_no_es_dia_uno(
    contrato,
) -> None:
    """Comprueba que el ajuste debe comenzar el primer día del mes."""
    with pytest.raises(
        AjusteRentaError,
        match="primer día del mes",
    ):
        crear_ajuste_renta(
            contrato=contrato,
            fecha_desde=date(2026, 9, 2),
            fecha_hasta=date(2026, 11, 30),
            tipo="IMPORTE_FIJO",
            valor=120000,
        )


def test_crear_ajuste_renta_rechaza_fecha_hasta_que_no_es_fin_de_mes(
    contrato,
) -> None:
    """Comprueba que el ajuste debe terminar el último día del mes."""
    with pytest.raises(
        AjusteRentaError,
        match="último día del mes",
    ):
        crear_ajuste_renta(
            contrato=contrato,
            fecha_desde=date(2026, 9, 1),
            fecha_hasta=date(2026, 11, 29),
            tipo="IMPORTE_FIJO",
            valor=120000,
        )


def test_renta_facturable_aplica_ajuste_hasta_el_ultimo_mes_inclusive(
    contrato,
) -> None:
    """Comprueba que el último mes del ajuste queda incluido."""
    contrato.rentas.append(
        RentaContrato(
            fecha_desde=contrato.fecha_inicio,
            importe=150000,
        )
    )

    contrato.ajustes_renta.append(
        AjusteRenta(
            fecha_desde=date(2026, 9, 1),
            fecha_hasta=date(2026, 11, 30),
            tipo="IMPORTE_FIJO",
            valor=120000,
        )
    )

    assert renta_facturable(
        contrato,
        date(2026, 9, 1),
    ) == 120000

    assert renta_facturable(
        contrato,
        date(2026, 10, 1),
    ) == 120000

    assert renta_facturable(
        contrato,
        date(2026, 11, 1),
    ) == 120000

    assert renta_facturable(
        contrato,
        date(2026, 12, 1),
    ) == 150000


def test_crear_anexo_carencia(contrato) -> None:
    """Comprueba que un anexo puede establecer un período de carencia."""

    anexo = crear_anexo_carencia(
        contrato=contrato,
        fecha=date(2026, 10, 15),
        fecha_desde=date(2026, 11, 1),
        fecha_hasta=date(2027, 1, 31),
        descripcion="Carencia acordada por tres meses",
    )

    assert isinstance(anexo, AnexoContrato)
    assert anexo.contrato is contrato
    assert anexo.tipo == "CARENCIA"
    assert anexo.fecha == date(2026, 10, 15)
    assert anexo.fecha_desde == date(2026, 11, 1)
    assert anexo.fecha_hasta == date(2027, 1, 31)
    assert anexo.descripcion == "Carencia acordada por tres meses"
    assert anexo.nueva_fecha_vencimiento is None


def test_crear_anexo_carencia_rechaza_inicio_que_no_es_dia_uno(
    contrato,
) -> None:
    """Comprueba que una carencia debe comenzar el primer día de un mes."""

    with pytest.raises(
        ContratoError,
        match="primer día del mes",
    ):
        crear_anexo_carencia(
            contrato=contrato,
            fecha=date(2026, 10, 15),
            fecha_desde=date(2026, 11, 2),
            fecha_hasta=date(2027, 1, 31),
        )


def test_crear_anexo_carencia_rechaza_fin_que_no_es_ultimo_dia_del_mes(
    contrato,
) -> None:
    """Comprueba que una carencia debe terminar el último día de un mes."""

    with pytest.raises(
        ContratoError,
        match="último día del mes",
    ):
        crear_anexo_carencia(
            contrato=contrato,
            fecha=date(2026, 10, 15),
            fecha_desde=date(2026, 11, 1),
            fecha_hasta=date(2027, 1, 30),
        )


def test_crear_anexo_carencia_rechaza_fin_anterior_al_inicio(
    contrato,
) -> None:
    """Comprueba que el final de la carencia no puede preceder al inicio."""

    with pytest.raises(
        ContratoError,
        match="no puede ser anterior",
    ):
        crear_anexo_carencia(
            contrato=contrato,
            fecha=date(2026, 10, 15),
            fecha_desde=date(2027, 2, 1),
            fecha_hasta=date(2027, 1, 31),
        )


def test_crear_anexo_carencia_rechaza_inicio_anterior_al_contrato(
    contrato,
) -> None:
    """Comprueba que una carencia no puede comenzar antes del contrato."""

    with pytest.raises(
        ContratoError,
        match="antes del inicio del contrato",
    ):
        crear_anexo_carencia(
            contrato=contrato,
            fecha=date(2026, 2, 1),
            fecha_desde=date(2026, 1, 1),
            fecha_hasta=date(2026, 1, 31),
        )


def test_crear_anexo_carencia_rechaza_solapamiento(
    contrato,
) -> None:
    """Comprueba que dos períodos de carencia no pueden solaparse."""

    contrato.anexos.append(
        AnexoContrato(
            fecha=date(2026, 9, 15),
            tipo="CARENCIA",
            fecha_desde=date(2026, 11, 1),
            fecha_hasta=date(2027, 1, 31),
        )
    )

    with pytest.raises(
        ContratoError,
        match="se solapa con otro período de carencia",
    ):
        crear_anexo_carencia(
            contrato=contrato,
            fecha=date(2026, 10, 15),
            fecha_desde=date(2027, 1, 1),
            fecha_hasta=date(2027, 3, 31),
        )


def test_crear_anexo_carencia_permite_periodos_separados(
    contrato,
) -> None:
    """Comprueba que un contrato puede tener varias carencias no solapadas."""

    contrato.anexos.append(
        AnexoContrato(
            fecha=date(2026, 9, 15),
            tipo="CARENCIA",
            fecha_desde=date(2026, 11, 1),
            fecha_hasta=date(2027, 1, 31),
        )
    )

    anexo = crear_anexo_carencia(
        contrato=contrato,
        fecha=date(2027, 5, 15),
        fecha_desde=date(2027, 6, 1),
        fecha_hasta=date(2027, 7, 31),
    )

    assert anexo.tipo == "CARENCIA"
    assert anexo.fecha_desde == date(2027, 6, 1)
    assert anexo.fecha_hasta == date(2027, 7, 31)


def test_crear_anexo_carencia_rechaza_fecha_anterior_al_contrato(
    contrato,
) -> None:
    """Comprueba que el anexo no puede formalizarse antes del contrato."""

    with pytest.raises(
        ContratoError,
        match="fecha del anexo no puede ser anterior",
    ):
        crear_anexo_carencia(
            contrato=contrato,
            fecha=date(2025, 12, 31),
            fecha_desde=date(2026, 2, 1),
            fecha_hasta=date(2026, 2, 28),
        )


def test_carencia_vigente_detecta_todo_el_periodo(
    contrato,
) -> None:
    """Comprueba que la carencia está vigente en todos sus meses."""

    anexo = crear_anexo_carencia(
        contrato=contrato,
        fecha=date(2026, 10, 15),
        fecha_desde=date(2026, 11, 1),
        fecha_hasta=date(2027, 1, 31),
    )

    assert carencia_vigente(
        contrato,
        date(2026, 10, 1),
    ) is None

    assert carencia_vigente(
        contrato,
        date(2026, 11, 1),
    ) is anexo

    assert carencia_vigente(
        contrato,
        date(2026, 12, 1),
    ) is anexo

    assert carencia_vigente(
        contrato,
        date(2027, 1, 1),
    ) is anexo

    assert carencia_vigente(
        contrato,
        date(2027, 2, 1),
    ) is None



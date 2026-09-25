import pytest

from datetime import date

from contab.formato import (
    importe_a_texto,
    periodo_a_texto,
    texto_a_importe,
    texto_a_periodo,
    texto_a_porcentaje,
)


def test_importe_a_texto() -> None:
    assert importe_a_texto(102500) == "1.025,00"
    assert importe_a_texto(35) == "0,35"
    assert importe_a_texto(-102500) == "-1.025,00"


def test_texto_a_importe() -> None:
    assert texto_a_importe("1025,00") == 102500
    assert texto_a_importe("35,50") == 3550
    assert texto_a_importe("-12,25") == -1225


def test_texto_a_porcentaje() -> None:
    assert texto_a_porcentaje("2,5") == 250
    assert texto_a_porcentaje("2,50") == 250
    assert texto_a_porcentaje("-1,25") == -125


def test_texto_a_importe_rechaza_texto_invalido() -> None:
    with pytest.raises(ValueError):
        texto_a_importe("treinta")


def test_texto_a_porcentaje_rechaza_texto_invalido() -> None:
    with pytest.raises(ValueError):
        texto_a_porcentaje("dos y medio")

def test_periodo_a_texto() -> None:
    assert periodo_a_texto(date(2026, 11, 1)) == "11/2026"


def test_texto_a_periodo() -> None:
    assert texto_a_periodo("11/2026") == date(2026, 11, 1)


def test_texto_a_periodo_rechaza_formato_invalido() -> None:
    with pytest.raises(ValueError):
        texto_a_periodo("11-2026")

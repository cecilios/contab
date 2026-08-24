from pathlib import Path

import pytest

from contab.config import ConfigError, cargar_bases_datos


def test_cargar_bases_datos_lee_una_base(tmp_path: Path) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[databases]
cliente = sqlite:///cliente.db
""".strip(),
        encoding="utf-8",
    )

    databases = cargar_bases_datos(ruta)

    assert databases == {
        "cliente": "sqlite:///cliente.db",
    }


def test_cargar_bases_datos_lee_varias_bases(tmp_path: Path) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[databases]
demo = sqlite:///demo.db
principal = sqlite:///contab.db
""".strip(),
        encoding="utf-8",
    )

    databases = cargar_bases_datos(ruta)

    assert databases == {
        "demo": "sqlite:///demo.db",
        "principal": "sqlite:///contab.db",
    }


def test_cargar_bases_datos_rechaza_archivo_inexistente(
    tmp_path: Path,
) -> None:
    ruta = tmp_path / "no-existe.ini"

    with pytest.raises(
        ConfigError,
        match="No se encuentra el archivo",
    ):
        cargar_bases_datos(ruta)


def test_cargar_bases_datos_rechaza_seccion_inexistente(
    tmp_path: Path,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[otra_seccion]
valor = prueba
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match=r"\[databases\]",
    ):
        cargar_bases_datos(ruta)


def test_cargar_bases_datos_rechaza_lista_vacia(
    tmp_path: Path,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[databases]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="No hay ninguna base de datos configurada",
    ):
        cargar_bases_datos(ruta)

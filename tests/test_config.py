from pathlib import Path

import pytest

from contab.config import (
    ConfigError,
    cargar_bases_datos,
    cargar_secret_key,
    ruta_configuracion,
)



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


def test_cargar_secret_key(tmp_path: Path) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[app]
secret_key = clave-de-prueba
""".strip(),
        encoding="utf-8",
    )

    assert cargar_secret_key(ruta) == "clave-de-prueba"


def test_cargar_secret_key_rechaza_clave_vacia(
    tmp_path: Path,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[app]
secret_key =
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="secret_key",
    ):
        cargar_secret_key(ruta)


def test_ruta_configuracion_por_defecto(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "CONTAB_CONFIG",
        raising=False,
    )

    assert ruta_configuracion() == Path("contab.ini")


def test_ruta_configuracion_desde_variable_entorno(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "CONTAB_CONFIG",
        "/opt/contab/contab.ini",
    )

    assert ruta_configuracion() == Path(
        "/opt/contab/contab.ini"
    )



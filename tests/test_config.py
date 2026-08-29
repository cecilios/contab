from pathlib import Path

import pytest

from contab.config import (
    CategoriaContable,
    ConfigError,
    SubcategoriaContable,
    cargar_bases_datos,
    cargar_categorias_contables,
    cargar_secret_key,
    categorias_contables_activas,
    ruta_configuracion,
    validar_clasificacion_contable,
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


def test_cargar_categorias_contables(tmp_path: Path) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[categorias_contables]
ING_ALQUILERES = INGRESO | Alquileres
GAS_TRIBUTOS = GASTO | Tributos, tasas y recargos

[subcategorias_contables]
GAS_TRIBUTOS.IBI = Impuesto sobre Bienes Inmuebles
GAS_TRIBUTOS.TRU = Tasa de Residuos Urbanos
""".strip(),
        encoding="utf-8",
    )

    categorias = cargar_categorias_contables(ruta)

    assert categorias["ING_ALQUILERES"].naturaleza == "INGRESO"
    assert categorias["ING_ALQUILERES"].nombre == "Alquileres"
    assert categorias["ING_ALQUILERES"].activa is True
    assert categorias["ING_ALQUILERES"].subcategorias == ()

    tributos = categorias["GAS_TRIBUTOS"]

    assert tributos.naturaleza == "GASTO"
    assert [
        subcategoria.codigo
        for subcategoria in tributos.subcategorias
    ] == ["IBI", "TRU"]


def test_categorias_contables_activas_filtra_elementos() -> None:
    categorias = {
        "ING_ALQUILERES": CategoriaContable(
            codigo="ING_ALQUILERES",
            naturaleza="INGRESO",
            nombre="Alquileres",
            activa=True,
            subcategorias=(),
        ),
        "GAS_ANTIGUO": CategoriaContable(
            codigo="GAS_ANTIGUO",
            naturaleza="GASTO",
            nombre="Categoría antigua",
            activa=False,
            subcategorias=(),
        ),
    }

    activas = categorias_contables_activas(categorias)

    assert [
        categoria.codigo
        for categoria in activas
    ] == ["ING_ALQUILERES"]


def test_validar_clasificacion_contable() -> None:
    categorias = {
        "GAS_TRIBUTOS": CategoriaContable(
            codigo="GAS_TRIBUTOS",
            naturaleza="GASTO",
            nombre="Tributos",
            activa=True,
            subcategorias=(
                SubcategoriaContable(
                    codigo="IBI",
                    nombre="IBI",
                ),
                SubcategoriaContable(
                    codigo="TRU",
                    nombre="Tasa de Residuos Urbanos",
                ),
            ),
        ),
    }

    validar_clasificacion_contable(
        categorias,
        "GASTO",
        "GAS_TRIBUTOS",
        "TRU",
    )


@pytest.mark.parametrize(
    ("naturaleza", "categoria", "subcategoria", "mensaje"),
    [
        (
            "INGRESO",
            "GAS_TRIBUTOS",
            "IBI",
            "no corresponde",
        ),
        (
            "GASTO",
            "GAS_TRIBUTOS",
            "",
            "exige una subcategoría",
        ),
        (
            "GASTO",
            "GAS_TRIBUTOS",
            "AGUA",
            "no pertenece",
        ),
    ],
)
def test_validar_clasificacion_contable_rechaza_datos_invalidos(
    naturaleza: str,
    categoria: str,
    subcategoria: str,
    mensaje: str,
) -> None:
    categorias = {
        "GAS_TRIBUTOS": CategoriaContable(
            codigo="GAS_TRIBUTOS",
            naturaleza="GASTO",
            nombre="Tributos",
            activa=True,
            subcategorias=(
                SubcategoriaContable(
                    codigo="IBI",
                    nombre="IBI",
                ),
            ),
        ),
    }

    with pytest.raises(ValueError, match=mensaje):
        validar_clasificacion_contable(
            categorias,
            naturaleza,
            categoria,
            subcategoria,
        )


def test_validar_clasificacion_permite_codigos_inactivos_historicos() -> None:
    categorias = {
        "GAS_ANTIGUO": CategoriaContable(
            codigo="GAS_ANTIGUO",
            naturaleza="GASTO",
            nombre="Categoría antigua",
            activa=False,
            subcategorias=(
                SubcategoriaContable(
                    codigo="SUBCATEGORIA_ANTIGUA",
                    nombre="Subcategoría antigua",
                    activa=False,
                ),
            ),
        ),
    }

    validar_clasificacion_contable(
        categorias,
        "GASTO",
        "GAS_ANTIGUO",
        "SUBCATEGORIA_ANTIGUA",
        permitir_inactivas=True,
    )


def test_categorias_activas_filtra_subcategorias_inactivas() -> None:
    categorias = {
        "GAS_TRIBUTOS": CategoriaContable(
            codigo="GAS_TRIBUTOS",
            naturaleza="GASTO",
            nombre="Tributos",
            activa=True,
            subcategorias=(
                SubcategoriaContable(
                    codigo="IBI",
                    nombre="IBI",
                    activa=True,
                ),
                SubcategoriaContable(
                    codigo="ANTIGUA",
                    nombre="Tributo antiguo",
                    activa=False,
                ),
            ),
        ),
    }

    activas = categorias_contables_activas(categorias)

    assert [
        subcategoria.codigo
        for subcategoria in activas[0].subcategorias
    ] == ["IBI"]



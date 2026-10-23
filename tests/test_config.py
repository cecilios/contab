import pytest

from pathlib import Path
from flask import session

from contab.app import create_app

from contab.config import (
    CategoriaContable,
    ConfigError,
    SubcategoriaContable,
    cargar_alias_conciliacion,
    cargar_apuntes_automaticos,
    cargar_bancos,
    cargar_bases_datos,
    cargar_categorias_contables,
    cargar_debug_conciliacion,
    cargar_secret_key,
    categorias_contables_activas,
    ruta_configuracion,
    validar_clasificacion_contable,
)
from contab.context import (
    get_database_path,
    get_invoice_template_path,
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


def test_cargar_bancos(
    tmp_path,
) -> None:
    """Carga el banco asociado a cada base de datos."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[databases]
cliente = sqlite:///cliente.db
hermana = sqlite:///hermana.db

[bancos]
cliente = IBERCAJA
hermana = CAIXABANK
""".strip(),
        encoding="utf-8",
    )

    bancos = cargar_bancos(ruta)

    assert bancos == {
        "cliente": "IBERCAJA",
        "hermana": "CAIXABANK",
    }


def test_cargar_bancos_exige_banco_para_cada_base(
    tmp_path,
) -> None:
    """Cada base de datos debe tener un banco configurado."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[databases]
cliente = sqlite:///cliente.db
hermana = sqlite:///hermana.db

[bancos]
cliente = IBERCAJA
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="hermana",
    ):
        cargar_bancos(ruta)


def test_cargar_alias_conciliacion(
    tmp_path: Path,
) -> None:
    """Carga los alias de conciliación agrupados por base de datos."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[databases]
demo = sqlite:///demo.db
principal = sqlite:///contab.db

[conciliacion:demo:comunidad:AVLOGRO]
alias =
    C.P. AV. LOGROÑ
    CP.AV.LOGROÑO
    C.P. AVENIDA LO

[conciliacion:demo:alquiler:AVLOGRO]
alias =
    FRUTERIAS EL
    GERARDO LOPEZ

[conciliacion:principal:alquiler:OTRO]
alias =
    OTRO INQUILINO
""".strip(),
        encoding="utf-8",
    )

    aliases = cargar_alias_conciliacion(ruta)

    assert aliases == {
        "demo": [
            (
                "COMUNIDAD",
                "AVLOGRO",
                "C.P. AV. LOGROÑ",
            ),
            (
                "COMUNIDAD",
                "AVLOGRO",
                "CP.AV.LOGROÑO",
            ),
            (
                "COMUNIDAD",
                "AVLOGRO",
                "C.P. AVENIDA LO",
            ),
            (
                "ALQUILER",
                "AVLOGRO",
                "FRUTERIAS EL",
            ),
            (
                "ALQUILER",
                "AVLOGRO",
                "GERARDO LOPEZ",
            ),
        ],
        "principal": [
            (
                "ALQUILER",
                "OTRO",
                "OTRO INQUILINO",
            ),
        ],
    }


def test_cargar_alias_conciliacion_rechaza_base_desconocida(
    tmp_path: Path,
) -> None:
    """Un alias debe pertenecer a una base de datos configurada."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[databases]
demo = sqlite:///demo.db

[conciliacion:inexistente:alquiler:AVLOGRO]
alias =
    GERARDO LOPEZ
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="inexistente",
    ):
        cargar_alias_conciliacion(ruta)


def test_cargar_alias_conciliacion_rechaza_alias_vacios(
    tmp_path: Path,
) -> None:
    """Una sección de conciliación debe contener algún alias."""

    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        """
[databases]
demo = sqlite:///demo.db

[conciliacion:demo:alquiler:AVLOGRO]
alias =
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="ningún alias",
    ):
        cargar_alias_conciliacion(ruta)


def test_get_database_path(tmp_path) -> None:
    """Devuelve la ruta de la base de datos activa."""

    ruta_db = tmp_path / "comunidad.db"

    app = create_app(
        databases={
            "comunidad": f"sqlite:///{ruta_db}",
        },
        secret_key="test-secret-key",
    )

    with app.test_request_context():
        session["database"] = "comunidad"

        assert get_database_path() == ruta_db.resolve()


def test_get_invoice_template_path(tmp_path) -> None:
    """Obtiene la plantilla de factura asociada a la base."""

    ruta_db = tmp_path / "comunidad.db"

    app = create_app(
        databases={
            "comunidad": f"sqlite:///{ruta_db}",
        },
        secret_key="test-secret-key",
    )

    with app.test_request_context():
        session["database"] = "comunidad"

        assert get_invoice_template_path() == (
            tmp_path / "comunidad-factura.html"
        ).resolve()


def test_get_database_path_rechaza_base_en_memoria() -> None:
    """Una base SQLite en memoria no tiene recursos asociados."""

    app = create_app(
        databases={
            "test": "sqlite:///:memory:",
        },
        secret_key="test-secret-key",
    )

    with app.test_request_context():
        session["database"] = "test"

        with pytest.raises(
            RuntimeError,
            match="no tiene una ruta de archivo",
        ):
            get_database_path()


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("true", True),
        ("false", False),
        ("yes", True),
        ("no", False),
        ("1", True),
        ("0", False),
    ],
)
def test_cargar_debug_conciliacion(
    tmp_path,
    valor,
    esperado,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        f"[app]\ndebug_conciliacion = {valor}\n",
        encoding="utf-8",
    )

    assert cargar_debug_conciliacion(ruta) is esperado


def test_debug_conciliacion_desactivado_por_defecto(
    tmp_path,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        "[app]\nsecret_key = prueba\n",
        encoding="utf-8",
    )

    assert cargar_debug_conciliacion(ruta) is False


def test_debug_conciliacion_rechaza_valor_invalido(
    tmp_path,
) -> None:
    ruta = tmp_path / "contab.ini"
    ruta.write_text(
        "[app]\ndebug_conciliacion = quizá\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        cargar_debug_conciliacion(ruta)

def test_cargar_apuntes_automaticos_segun_base(
    tmp_path: Path,
) -> None:
    """Lee exclusivamente los apuntes de la base indicada."""

    ruta_config = tmp_path / "contab.ini"

    ruta_config.write_text(
        "[app]\nsecret_key = prueba\n",
        encoding="utf-8",
    )

    # El usuario tiene configuradas dos bases de datos.
    archivo_demo = (
        tmp_path / "apuntes-automaticos-demo.txt"
    )
    archivo_principal = (
        tmp_path / "apuntes-automaticos-principal.txt"
    )

    archivo_demo.write_text(
        "DEMO-1 | GAS_COMUNIDAD | Comunidad | 12,50\n",
        encoding="utf-8",
    )

    archivo_principal.write_text(
        """
# Gastos mensuales de la base principal

LOCAL-1 | GAS_COMUNIDAD | Comunidad | 87,35
LOCAL-2 | GAS_COMUNIDAD | Comunidad | 64,20
""".strip(),
        encoding="utf-8",
    )

    # El usuario selecciona la base de datos principal.
    apuntes = cargar_apuntes_automaticos(
        "principal",
        ruta_config,
    )

    # Se leen sus dos apuntes, no el de la base demo.
    assert len(apuntes) == 2

    assert apuntes[0].inmueble_referencia == "LOCAL-1"
    assert apuntes[0].categoria == "GAS_COMUNIDAD"
    assert apuntes[0].concepto == "Comunidad"
    assert apuntes[0].base == 8735

    assert apuntes[1].inmueble_referencia == "LOCAL-2"
    assert apuntes[1].categoria == "GAS_COMUNIDAD"
    assert apuntes[1].concepto == "Comunidad"
    assert apuntes[1].base == 6420


def test_cargar_apuntes_automaticos_rechaza_archivo_inexistente(
    tmp_path: Path,
) -> None:
    ruta_config = tmp_path / "contab.ini"

    ruta_config.write_text(
        "[app]\nsecret_key = prueba\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="No se encuentra el archivo",
    ):
        cargar_apuntes_automaticos(
            "principal",
            ruta_config,
        )


def test_cargar_apuntes_automaticos_rechaza_archivo_vacio(
    tmp_path: Path,
) -> None:
    ruta_config = tmp_path / "contab.ini"
    ruta_archivo = (
        tmp_path / "apuntes-automaticos-principal.txt"
    )

    ruta_config.write_text(
        "[app]\nsecret_key = prueba\n",
        encoding="utf-8",
    )

    ruta_archivo.write_text(
        """
# Apuntes mensuales
#
# Todavía no hay apuntes configurados.

""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="No hay apuntes automáticos",
    ):
        cargar_apuntes_automaticos(
            "principal",
            ruta_config,
        )


def test_cargar_apuntes_automaticos_rechaza_campos_incorrectos(
    tmp_path: Path,
) -> None:
    ruta_config = tmp_path / "contab.ini"
    ruta_archivo = (
        tmp_path / "apuntes-automaticos-principal.txt"
    )

    ruta_config.write_text(
        "[app]\nsecret_key = prueba\n",
        encoding="utf-8",
    )

    ruta_archivo.write_text(
        """
# Gastos mensuales
LOCAL-1 | GAS_COMUNIDAD | Comunidad
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="línea 2",
    ):
        cargar_apuntes_automaticos(
            "principal",
            ruta_config,
        )


@pytest.mark.parametrize(
    "linea",
    [
        "| GAS_COMUNIDAD | Comunidad | 87,35",
        "LOCAL-1 | | Comunidad | 87,35",
        "LOCAL-1 | GAS_COMUNIDAD | | 87,35",
    ],
)
def test_cargar_apuntes_automaticos_rechaza_campos_vacios(
    tmp_path: Path,
    linea: str,
) -> None:
    ruta_config = tmp_path / "contab.ini"
    ruta_archivo = (
        tmp_path / "apuntes-automaticos-principal.txt"
    )

    ruta_config.write_text(
        "[app]\nsecret_key = prueba\n",
        encoding="utf-8",
    )

    ruta_archivo.write_text(
        linea,
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="línea 1",
    ):
        cargar_apuntes_automaticos(
            "principal",
            ruta_config,
        )


@pytest.mark.parametrize(
    "importe",
    [
        "",
        "abc",
        "0",
        "0,00",
        "-10,50",
        "10,123",
        "12.50",
    ],
)
def test_cargar_apuntes_automaticos_rechaza_importes_invalidos(
    tmp_path: Path,
    importe: str,
) -> None:
    ruta_config = tmp_path / "contab.ini"
    ruta_archivo = (
        tmp_path / "apuntes-automaticos-principal.txt"
    )

    ruta_config.write_text(
        "[app]\nsecret_key = prueba\n",
        encoding="utf-8",
    )

    ruta_archivo.write_text(
        f"LOCAL-1 | GAS_COMUNIDAD | Comunidad | {importe}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="importe",
    ):
        cargar_apuntes_automaticos(
            "principal",
            ruta_config,
        )


@pytest.mark.parametrize(
    ("importe", "centimos"),
    [
        ("85", 8500),
        ("85,5", 8550),
        ("85,50", 8550),
        ("0,01", 1),
        ("1234,56", 123456),
    ],
)
def test_cargar_apuntes_automaticos_convierte_importes(
    tmp_path: Path,
    importe: str,
    centimos: int,
) -> None:
    ruta_config = tmp_path / "contab.ini"
    ruta_archivo = (
        tmp_path / "apuntes-automaticos-principal.txt"
    )

    ruta_config.write_text(
        "[app]\nsecret_key = prueba\n",
        encoding="utf-8",
    )

    ruta_archivo.write_text(
        f"LOCAL-1 | GAS_COMUNIDAD | Comunidad | {importe}\n",
        encoding="utf-8",
    )

    apuntes = cargar_apuntes_automaticos(
        "principal",
        ruta_config,
    )

    assert len(apuntes) == 1
    assert apuntes[0].base == centimos



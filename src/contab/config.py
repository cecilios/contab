import os
from configparser import ConfigParser
from pathlib import Path
from dataclasses import dataclass


class ConfigError(Exception):
    """Indica un error en la configuración de Contab."""

@dataclass(frozen=True)
class SubcategoriaContable:
    """Subcategoría contable definida en la configuración."""

    codigo: str
    nombre: str
    activa: bool = True


@dataclass(frozen=True)
class CategoriaContable:
    """Categoría contable definida en la configuración."""

    codigo: str
    naturaleza: str
    nombre: str
    activa: bool
    subcategorias: tuple[SubcategoriaContable, ...]



def ruta_configuracion() -> Path:
    """Devuelve la ruta del archivo de configuración de Contab."""
    ruta = os.environ.get("CONTAB_CONFIG")

    if ruta:
        return Path(ruta)

    return Path("contab.ini")


def cargar_secret_key(
    ruta: str | Path | None = None,
) -> str:
    """Carga la clave secreta de la aplicación."""
    if ruta is None:
        ruta = ruta_configuracion()

    ruta = Path(ruta)

    if not ruta.exists():
        raise ConfigError(
            f"No se encuentra el archivo de configuración: {ruta}"
        )

    config = ConfigParser()

    if not config.read(ruta, encoding="utf-8"):
        raise ConfigError(
            f"No se pudo leer el archivo de configuración: {ruta}"
        )

    if "app" not in config:
        raise ConfigError(
            "El archivo de configuración no contiene "
            "la sección [app]."
        )

    secret_key = config["app"].get("secret_key", "").strip()

    if not secret_key:
        raise ConfigError(
            "No se ha configurado secret_key en la sección [app]."
        )

    return secret_key


def cargar_bases_datos(
    ruta: str | Path | None = None,
) -> dict[str, str]:
    """Carga las bases de datos definidas en el archivo de configuración."""
    if ruta is None:
        ruta = ruta_configuracion()

    ruta = Path(ruta)

    if not ruta.exists():
        raise ConfigError(
            f"No se encuentra el archivo de configuración: {ruta}"
        )

    config = ConfigParser()

    if not config.read(ruta, encoding="utf-8"):
        raise ConfigError(
            f"No se pudo leer el archivo de configuración: {ruta}"
        )

    if "databases" not in config:
        raise ConfigError(
            "El archivo de configuración no contiene "
            "la sección [databases]."
        )

    databases = {
        nombre.strip(): url.strip()
        for nombre, url in config["databases"].items()
        if nombre.strip() and url.strip()
    }

    if not databases:
        raise ConfigError(
            "No hay ninguna base de datos configurada."
        )

    return databases


def _estado_configurado(
    texto: str,
    elemento: str,
) -> bool:
    """Convierte activa/inactiva en un booleano."""

    estado = texto.strip().lower()

    if estado == "activa":
        return True

    if estado == "inactiva":
        return False

    raise ConfigError(
        f"El estado de {elemento} debe ser activa o inactiva."
    )


def cargar_categorias_contables(
    ruta: str | Path | None = None,
) -> dict[str, CategoriaContable]:
    """Carga las categorías y subcategorías contables."""

    if ruta is None:
        ruta = ruta_configuracion()

    ruta = Path(ruta)

    if not ruta.exists():
        raise ConfigError(
            f"No se encuentra el archivo de configuración: {ruta}"
        )

    config = ConfigParser(interpolation=None)

    if not config.read(ruta, encoding="utf-8"):
        raise ConfigError(
            f"No se pudo leer el archivo de configuración: {ruta}"
        )

    if "categorias_contables" not in config:
        raise ConfigError(
            "El archivo de configuración no contiene "
            "la sección [categorias_contables]."
        )

    if "subcategorias_contables" not in config:
        raise ConfigError(
            "El archivo de configuración no contiene "
            "la sección [subcategorias_contables]."
        )

    datos_categorias: dict[str, dict] = {}

    for codigo_texto, valor in config[
        "categorias_contables"
    ].items():
        codigo = codigo_texto.strip().upper()
        partes = [parte.strip() for parte in valor.split("|")]

        if len(partes) not in (2, 3):
            raise ConfigError(
                f"La categoría {codigo} debe indicar "
                "naturaleza, nombre y, opcionalmente, estado."
            )

        naturaleza, nombre = partes[:2]

        naturaleza = naturaleza.upper()

        if naturaleza not in {"INGRESO", "GASTO"}:
            raise ConfigError(
                f"La categoría {codigo} tiene una naturaleza no válida."
            )

        if not nombre:
            raise ConfigError(
                f"La categoría {codigo} no tiene nombre."
            )

        activa = (
            _estado_configurado(
                partes[2],
                f"la categoría {codigo}",
            )
            if len(partes) == 3
            else True
        )

        datos_categorias[codigo] = {
            "naturaleza": naturaleza,
            "nombre": nombre,
            "activa": activa,
            "subcategorias": [],
        }

    if not datos_categorias:
        raise ConfigError(
            "No hay categorías contables configuradas."
        )

    for clave_texto, valor in config[
        "subcategorias_contables"
    ].items():
        clave = clave_texto.strip().upper()

        if clave.count(".") != 1:
            raise ConfigError(
                f"La subcategoría {clave} debe tener el formato "
                "CATEGORIA.SUBCATEGORIA."
            )

        categoria_codigo, codigo = clave.split(".")

        if categoria_codigo not in datos_categorias:
            raise ConfigError(
                f"La subcategoría {clave} pertenece a una "
                "categoría inexistente."
            )

        partes = [parte.strip() for parte in valor.split("|")]

        if len(partes) not in (1, 2):
            raise ConfigError(
                f"La subcategoría {clave} debe indicar "
                "nombre y, opcionalmente, estado."
            )

        nombre = partes[0]

        if not nombre:
            raise ConfigError(
                f"La subcategoría {clave} no tiene nombre."
            )

        activa = (
            _estado_configurado(
                partes[1],
                f"la subcategoría {clave}",
            )
            if len(partes) == 2
            else True
        )

        datos_categorias[categoria_codigo][
            "subcategorias"
        ].append(
            SubcategoriaContable(
                codigo=codigo,
                nombre=nombre,
                activa=activa,
            )
        )

    return {
        codigo: CategoriaContable(
            codigo=codigo,
            naturaleza=datos["naturaleza"],
            nombre=datos["nombre"],
            activa=datos["activa"],
            subcategorias=tuple(datos["subcategorias"]),
        )
        for codigo, datos in datos_categorias.items()
    }


def categorias_contables_activas(
    categorias: dict[str, CategoriaContable],
) -> tuple[CategoriaContable, ...]:
    """Devuelve las categorías activas para nuevos apuntes."""

    return tuple(
        CategoriaContable(
            codigo=categoria.codigo,
            naturaleza=categoria.naturaleza,
            nombre=categoria.nombre,
            activa=True,
            subcategorias=tuple(
                subcategoria
                for subcategoria in categoria.subcategorias
                if subcategoria.activa
            ),
        )
        for categoria in categorias.values()
        if categoria.activa
    )


def validar_clasificacion_contable(
    categorias: dict[str, CategoriaContable],
    naturaleza: str,
    categoria: str,
    subcategoria: str = "",
    *,
    permitir_inactivas: bool = False,
) -> None:
    """Valida la clasificación elegida para un apunte."""

    naturaleza = naturaleza.strip().upper()
    categoria = categoria.strip().upper()
    subcategoria = subcategoria.strip().upper()

    categoria_configurada = categorias.get(categoria)

    if categoria_configurada is None:
        raise ValueError(
            f"La categoría contable {categoria} no existe."
        )

    if (
        not categoria_configurada.activa
        and not permitir_inactivas
    ):
        raise ValueError(
            f"La categoría contable {categoria} está inactiva."
        )

    if categoria_configurada.naturaleza != naturaleza:
        raise ValueError(
            f"La categoría {categoria} no corresponde "
            f"a la naturaleza {naturaleza}."
        )

    subcategorias = {
        elemento.codigo: elemento
        for elemento in categoria_configurada.subcategorias
    }

    if not subcategorias:
        if subcategoria:
            raise ValueError(
                f"La categoría {categoria} no admite subcategoría."
            )

        return

    if not subcategoria:
        raise ValueError(
            f"La categoría {categoria} exige una subcategoría."
        )

    subcategoria_configurada = subcategorias.get(subcategoria)

    if subcategoria_configurada is None:
        raise ValueError(
            f"La subcategoría {subcategoria} no pertenece "
            f"a la categoría {categoria}."
        )

    if (
        not subcategoria_configurada.activa
        and not permitir_inactivas
    ):
        raise ValueError(
            f"La subcategoría {categoria}.{subcategoria} "
            "está inactiva."
        )


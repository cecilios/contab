import os
import re

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


@dataclass(frozen=True)
class ApunteAutomatico:
    """Datos de un apunte contable mensual configurado."""

    inmueble_referencia: str
    categoria: str
    concepto: str
    base: int



def ruta_configuracion() -> Path:
    """Devuelve la ruta del archivo de configuración de Contab."""
    ruta = os.environ.get("CONTAB_CONFIG")

    if ruta:
        return Path(ruta)

    return Path("contab.ini")


def cargar_apuntes_automaticos(
    nombre_base: str,
    ruta: str | Path | None = None,
) -> list[ApunteAutomatico]:
    """Carga los apuntes automáticos de una base de datos."""

    if ruta is None:
        ruta = ruta_configuracion()

    ruta = Path(ruta)

    # El nombre de la base forma parte del nombre del archivo.
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", nombre_base):
        raise ConfigError(
            "El nombre de la base de datos no es válido."
        )

    archivo = ruta.parent / (
        f"apuntes-automaticos-{nombre_base}.txt"
    )

    if not archivo.is_file():
        raise ConfigError(
            f"No se encuentra el archivo de apuntes "
            f"automáticos: {archivo}"
        )

    try:
        lineas = archivo.read_text(
            encoding="utf-8"
        ).splitlines()
    except (OSError, UnicodeError) as exc:
        raise ConfigError(
            f"No se pudo leer el archivo: {archivo}"
        ) from exc

    apuntes = []

    for numero_linea, linea in enumerate(
        lineas,
        start=1,
    ):
        linea = linea.strip()

        # Se ignoran comentarios y líneas vacías.
        if not linea or linea.startswith("#"):
            continue

        campos = [
            campo.strip()
            for campo in linea.split("|")
        ]

        if len(campos) != 4:
            raise ConfigError(
                f"Formato incorrecto en la línea "
                f"{numero_linea} de {archivo.name}: "
                f"se esperan cuatro campos."
            )

        (
            inmueble_referencia,
            categoria,
            concepto,
            importe_texto,
        ) = campos

        if not (
            inmueble_referencia
            and categoria
            and concepto
        ):
            raise ConfigError(
                f"Hay campos obligatorios vacíos "
                f"en la línea {numero_linea} "
                f"de {archivo.name}."
            )

        # Se admiten importes positivos con coma decimal
        # y un máximo de dos cifras decimales.
        if not re.fullmatch(
            r"\d+(?:,\d{1,2})?",
            importe_texto,
        ):
            raise ConfigError(
                f"El importe de la línea "
                f"{numero_linea} de {archivo.name} "
                f"no es válido."
            )

        partes = importe_texto.split(",")

        euros = int(partes[0])

        centimos = (
            int(partes[1].ljust(2, "0"))
            if len(partes) == 2
            else 0
        )

        base = euros * 100 + centimos

        if base <= 0:
            raise ConfigError(
                f"El importe de la línea "
                f"{numero_linea} de {archivo.name} "
                f"debe ser positivo."
            )

        apuntes.append(
            ApunteAutomatico(
                inmueble_referencia=inmueble_referencia,
                categoria=categoria.upper(),
                concepto=concepto,
                base=base,
            )
        )

    if not apuntes:
        raise ConfigError(
            f"No hay apuntes automáticos "
            f"en el archivo {archivo.name}."
        )

    return apuntes


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


def cargar_bancos(
    ruta: str | Path | None = None,
) -> dict[str, str]:
    """Carga el banco asociado a cada base de datos."""

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

    if "bancos" not in config:
        raise ConfigError(
            "El archivo de configuración no contiene "
            "la sección [bancos]."
        )

    bases_datos = {
        nombre.strip()
        for nombre, url in config["databases"].items()
        if nombre.strip() and url.strip()
    }

    bancos = {
        nombre.strip(): banco.strip().upper()
        for nombre, banco in config["bancos"].items()
        if nombre.strip() and banco.strip()
    }

    for nombre in bases_datos:
        if nombre not in bancos:
            raise ConfigError(
                f"No se ha configurado el banco para "
                f"la base de datos {nombre}."
            )

    bancos_desconocidos = (
        set(bancos) - bases_datos
    )

    if bancos_desconocidos:
        nombre = sorted(bancos_desconocidos)[0]

        raise ConfigError(
            f"Se ha configurado un banco para la base "
            f"de datos inexistente {nombre}."
        )

    bancos_soportados = {
        "IBERCAJA",
        "CAIXABANK",
    }

    for nombre, banco in bancos.items():
        if banco not in bancos_soportados:
            raise ConfigError(
                f"El banco {banco} configurado para "
                f"{nombre} no está soportado."
            )

    return bancos


def cargar_alias_conciliacion(
    ruta: str | Path | None = None,
) -> dict[str, list[tuple[str, str, str]]]:
    """Carga los alias temporales usados para proponer conciliaciones."""

    if ruta is None:
        ruta = ruta_configuracion()

    ruta = Path(ruta)

    bases_datos = cargar_bases_datos(ruta)

    config = ConfigParser(interpolation=None)

    if not config.read(ruta, encoding="utf-8"):
        raise ConfigError(
            f"No se pudo leer el archivo de configuración: {ruta}"
        )

    resultado: dict[str, list[tuple[str, str, str]]] = {}

    for seccion in config.sections():
        if not seccion.lower().startswith("conciliacion:"):
            continue

        partes = [
            parte.strip()
            for parte in seccion.split(":")
        ]

        if len(partes) != 4:
            raise ConfigError(
                f"La sección [{seccion}] no tiene un formato válido."
            )

        _, base_datos, tipo, inmueble_ref = partes

        base_datos = base_datos.lower()
        tipo = tipo.upper()
        inmueble_ref = inmueble_ref.upper()

        if base_datos not in bases_datos:
            raise ConfigError(
                f"La sección [{seccion}] corresponde a "
                f"la base de datos inexistente {base_datos}."
            )

        aliases = [
            linea.strip()
            for linea in config[seccion].get("alias", "").splitlines()
            if linea.strip()
        ]

        if not aliases:
            raise ConfigError(
                f"La sección [{seccion}] no contiene ningún alias."
            )

        resultado.setdefault(
            base_datos,
            [],
        ).extend(
            (
                tipo,
                inmueble_ref,
                alias,
            )
            for alias in aliases
        )

    return resultado


def cargar_debug_conciliacion(
    ruta: str | Path | None = None,
) -> bool:
    """Indica si está habilitado el diagnóstico de conciliación."""

    if ruta is None:
        ruta = ruta_configuracion()

    config = ConfigParser(interpolation=None)

    if not config.read(ruta, encoding="utf-8"):
        raise ConfigError(
            f"No se pudo leer el archivo de configuración: {ruta}"
        )

    try:
        return config.getboolean(
            "app",
            "debug_conciliacion",
            fallback=False,
        )
    except ValueError as exc:
        raise ConfigError(
            "debug_conciliacion debe ser true o false."
        ) from exc


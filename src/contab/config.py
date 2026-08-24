from configparser import ConfigParser
from pathlib import Path


class ConfigError(Exception):
    """Indica un error en la configuración de Contab."""


def cargar_bases_datos(
    ruta: str | Path = "contab.ini",
) -> dict[str, str]:
    """Carga las bases de datos definidas en el archivo de configuración."""
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



    

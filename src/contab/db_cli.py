import argparse
from importlib.resources import files

from alembic import command
from alembic.config import Config


def _alembic_config(database: str | None) -> Config:
    """Construye la configuración de Alembic para Contab."""
    migrations_path = files("contab").joinpath("migrations")

    config = Config()
    config.set_main_option(
        "script_location",
        str(migrations_path),
    )

    if database is not None:
        config.cmd_opts = argparse.Namespace(
            x=[f"database={database}"]
        )

    return config


def main() -> None:
    """Administra las migraciones de las bases de datos de Contab."""
    parser = argparse.ArgumentParser(
        prog="contab-db",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    current_parser = subparsers.add_parser(
        "current",
        help="Muestra la versión actual de la base de datos.",
    )
    current_parser.add_argument(
        "--database",
    )

    upgrade_parser = subparsers.add_parser(
        "upgrade",
        help="Actualiza la base de datos a la última versión.",
    )
    upgrade_parser.add_argument(
        "--database",
    )
    upgrade_parser.add_argument(
        "revision",
        nargs="?",
        default="head",
    )

    revision_parser = subparsers.add_parser(
        "revision",
        help="Genera una nueva revisión de Alembic.",
    )
    revision_parser.add_argument(
        "--database",
    )
    revision_parser.add_argument(
        "--autogenerate",
        action="store_true",
    )
    revision_parser.add_argument(
        "-m",
        "--message",
        required=True,
    )

    args = parser.parse_args()

    config = _alembic_config(args.database)

    if args.command == "current":
        command.current(config)

    elif args.command == "upgrade":
        command.upgrade(
            config,
            args.revision,
        )
    
    elif args.command == "revision":
        command.revision(
            config,
            message=args.message,
            autogenerate=args.autogenerate,
        )


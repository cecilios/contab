from waitress import serve

from contab.app import create_app


def main() -> None:
    """Arranca la aplicación Contab."""
    host = "127.0.0.1"
    port = 5000
    url = f"http://{host}:{port}"

    print(f"Contab disponible en: {url}")

    app = create_app()

    serve(
        app,
        host=host,
        port=port,
    )

"""Crea y configura la aplicación web Flask de Contab."""

from flask import Flask

from contab.database import create_session_factory, create_sqlite_engine
from contab.inmuebles.routes import bp as inmuebles_bp


def create_app(database_url: str = "sqlite:///contab.db") -> Flask:
    """Crea la aplicación Flask y configura su acceso a la base de datos."""
    app = Flask(__name__)

    engine = create_sqlite_engine(database_url)
    session_factory = create_session_factory(engine)

    app.extensions["contab_session_factory"] = session_factory

    app.register_blueprint(inmuebles_bp)

    @app.get("/")
    def index() -> str:
        return """
        <h1>Contab</h1>
        <p><a href="/inmuebles/">Inmuebles</a></p>
        """

    return app

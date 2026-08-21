"""Crea y configura la aplicación web Flask de Contab."""

from flask import Flask, redirect, render_template_string, request, session, url_for

from contab.database import create_session_factory, create_sqlite_engine
from contab.inmuebles.routes import bp as inmuebles_bp


def create_app(
    databases: dict[str, str] | None = None,
) -> Flask:
    """Crea la aplicación Flask y configura las bases de datos disponibles."""
    app = Flask(__name__)

    app.secret_key = "contab-development-key"

    if databases is None:
        databases = {
            "principal": "sqlite:///contab.db",
        }

    app.extensions["contab_databases"] = {
        nombre: create_session_factory(
            create_sqlite_engine(database_url)
        )
        for nombre, database_url in databases.items()
    }

    app.register_blueprint(inmuebles_bp)

    @app.route("/", methods=["GET", "POST"])
    def index():
        """Permite seleccionar la base de datos de trabajo."""
        if request.method == "POST":
            nombre = request.form["database"]

            if nombre not in app.extensions["contab_databases"]:
                return "Base de datos desconocida.", 400

            session["database"] = nombre

            return redirect(url_for("inmuebles.listar_inmuebles"))

        return render_template_string(
            """
            <!doctype html>
            <html lang="es">
            <head>
                <meta charset="utf-8">
                <title>Contab</title>
            </head>
            <body>
                <h1>Contab</h1>

                <form method="post">
                    <label>
                        Base de datos
                        <select name="database">
                        {% for nombre in databases %}
                            <option value="{{ nombre }}">
                                {{ nombre }}
                            </option>
                        {% endfor %}
                        </select>
                    </label>

                    <button type="submit">Entrar</button>
                </form>
            </body>
            </html>
            """,
            databases=app.extensions["contab_databases"].keys(),
        )

    return app

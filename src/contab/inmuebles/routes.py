"""Define las rutas web para consultar y mantener inmuebles."""

from flask import Blueprint, current_app, render_template
from sqlalchemy import select

from contab.models import Inmueble


bp = Blueprint(
    "inmuebles",
    __name__,
    url_prefix="/inmuebles",
    template_folder="templates",
)


@bp.get("/")
def listar_inmuebles():
    """Muestra el listado de inmuebles registrados en la base de datos."""
    session_factory = current_app.extensions["contab_session_factory"]

    with session_factory() as session:
        inmuebles = session.scalars(
            select(Inmueble).order_by(Inmueble.referencia)
        ).all()

        return render_template(
            "inmuebles/lista.html",
            inmuebles=inmuebles,
        )

"""Define las rutas web para consultar y mantener inmuebles."""

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import select

from contab.models import Inmueble


bp = Blueprint(
    "inmuebles",
    __name__,
    url_prefix="/inmuebles",
    template_folder="templates",
)


def _participacion_a_entero(valor: str) -> int:
    """Convierte un porcentaje escrito por el usuario a centésimas."""
    texto = valor.strip().replace(",", ".")
    return round(float(texto) * 100)


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


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo_inmueble():
    """Permite introducir y guardar un nuevo inmueble."""
    if request.method == "GET":
        return render_template(
            "inmuebles/nuevo.html",
            datos={},
            error=None,
        )

    datos = request.form

    if not datos["referencia"].strip():
        return (
            render_template(
                "inmuebles/nuevo.html",
                datos=datos,
                error="La referencia es obligatoria.",
            ),
            400,
        )

    session_factory = current_app.extensions["contab_session_factory"]

    inmueble = Inmueble(
        referencia=datos["referencia"].strip(),
        codigo_facturacion=datos["codigo_facturacion"].strip(),
        descripcion=datos["descripcion"].strip(),
        direccion=datos["direccion"].strip(),
        codigo_postal=datos["codigo_postal"].strip() or None,
        poblacion=datos["poblacion"].strip(),
        provincia=datos["provincia"].strip(),
        ref_catastral=datos["ref_catastral"].strip() or None,
        seguro=datos["seguro"].strip() or None,
        participacion=_participacion_a_entero(datos["participacion"]),
        notas=datos["notas"].strip() or None,
    )

    with session_factory() as session:
        session.add(inmueble)
        session.commit()

    return redirect(url_for("inmuebles.listar_inmuebles"))

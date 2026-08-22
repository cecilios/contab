"""Define las rutas web para consultar y mantener inmuebles."""

from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import select
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from contab.models import Inmueble
from contab.context import get_database_name, get_session_factory

bp = Blueprint(
    "inmuebles",
    __name__,
    url_prefix="/inmuebles",
    template_folder="templates",
)


def _participacion_a_entero(valor: str) -> int:
    """Convierte un porcentaje escrito por el usuario a centésimas."""
    texto = valor.strip().replace(",", ".")

    try:
        porcentaje = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(
            "La participación debe ser un porcentaje válido."
        ) from exc

    if porcentaje <= 0:
        raise ValueError(
            "La participación debe ser superior al 0 %."
        )

    if porcentaje > 100:
        raise ValueError(
            "La participación no puede superar el 100 %."
        )

    return int(
        (porcentaje * 100).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


@bp.get("/")
def listar_inmuebles():
    """Muestra el listado de inmuebles registrados en la base de datos."""
    session_factory = get_session_factory()

    with session_factory() as session:
        inmuebles = session.scalars(
            select(Inmueble).order_by(Inmueble.referencia)
        ).all()

        return render_template(
            "inmuebles/lista.html",
            inmuebles=inmuebles,
            database_name=get_database_name(),
        )


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo_inmueble():
    """Permite introducir y guardar un nuevo inmueble."""
    if request.method == "GET":
        return render_template(
            "inmuebles/nuevo.html",
            datos={},
            error=None,
            database_name=get_database_name(),
        )

    datos = request.form

    campos_obligatorios = (
        ("referencia", "La referencia es obligatoria."),
        (
            "codigo_facturacion",
            "El código de facturación es obligatorio.",
        ),
        ("descripcion", "La descripción es obligatoria."),
        ("direccion", "La dirección es obligatoria."),
        ("poblacion", "La población es obligatoria."),
        ("provincia", "La provincia es obligatoria."),
    )

    for campo, mensaje in campos_obligatorios:
        if not datos[campo].strip():
            return (
                render_template(
                    "inmuebles/nuevo.html",
                    datos=datos,
                    error=mensaje,
                    database_name=get_database_name(),
                ),
                400,
            )

    try:
        participacion = _participacion_a_entero(
            datos["participacion"]
        )
    except ValueError as exc:
        return (
            render_template(
                "inmuebles/nuevo.html",
                datos=datos,
                error=str(exc),
                database_name=get_database_name(),
            ),
            400,
        )

    session_factory = get_session_factory()

    with session_factory() as session:
        referencia = datos["referencia"].strip()
        codigo_facturacion = datos["codigo_facturacion"].strip()

        inmueble_referencia = session.scalar(
            select(Inmueble).where(
                Inmueble.referencia == referencia
            )
        )

        if inmueble_referencia is not None:
            return (
                render_template(
                    "inmuebles/nuevo.html",
                    datos=datos,
                    error="Ya existe un inmueble con esa referencia.",
                    database_name=get_database_name(),
                ),
                400,
            )

        inmueble_codigo = session.scalar(
            select(Inmueble).where(
                Inmueble.codigo_facturacion == codigo_facturacion
            )
        )

        if inmueble_codigo is not None:
            return (
                render_template(
                    "inmuebles/nuevo.html",
                    datos=datos,
                    error=(
                        "Ya existe un inmueble con ese "
                        "código de facturación."
                    ),
                    database_name=get_database_name(),
                ),
                400,
            )

        inmueble = Inmueble(
            referencia=referencia,
            codigo_facturacion=codigo_facturacion,
            descripcion=datos["descripcion"].strip(),
            direccion=datos["direccion"].strip(),
            codigo_postal=datos["codigo_postal"].strip() or None,
            poblacion=datos["poblacion"].strip(),
            provincia=datos["provincia"].strip(),
            ref_catastral=datos["ref_catastral"].strip() or None,
            seguro=datos["seguro"].strip() or None,
            participacion=participacion,
            notas=datos["notas"].strip() or None,
        )

        session.add(inmueble)
        session.commit()

    return redirect(url_for("inmuebles.listar_inmuebles"))

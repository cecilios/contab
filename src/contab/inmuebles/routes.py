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


def _validar_datos_inmueble(datos) -> tuple[dict, str | None]:
    """Valida los datos del formulario y devuelve valores normalizados."""
    campos_obligatorios = (
        ("referencia", "La referencia es obligatoria."),
        ("codigo_facturacion", "El código de facturación es obligatorio."),
        ("descripcion", "La descripción es obligatoria."),
        ("direccion", "La dirección es obligatoria."),
        ("poblacion", "La población es obligatoria."),
        ("provincia", "La provincia es obligatoria."),
    )

    for campo, mensaje in campos_obligatorios:
        if not datos[campo].strip():
            return {}, mensaje

    try:
        participacion = _participacion_a_entero(datos["participacion"])
    except ValueError as exc:
        return {}, str(exc)

    valores = {
        "referencia": datos["referencia"].strip(),
        "codigo_facturacion": datos["codigo_facturacion"].strip(),
        "descripcion": datos["descripcion"].strip(),
        "direccion": datos["direccion"].strip(),
        "codigo_postal": datos["codigo_postal"].strip() or None,
        "poblacion": datos["poblacion"].strip(),
        "provincia": datos["provincia"].strip(),
        "ref_catastral": datos["ref_catastral"].strip() or None,
        "seguro": datos["seguro"].strip() or None,
        "participacion": participacion,
        "notas": datos["notas"].strip() or None,
    }

    return valores, None


def _buscar_duplicado(
    session,
    referencia: str,
    codigo_facturacion: str,
    excluir_id: int | None = None,
) -> str | None:
    """Detecta referencias o códigos de facturación ya utilizados."""
    inmueble_referencia = session.scalar(
        select(Inmueble).where(
            Inmueble.referencia == referencia
        )
    )

    if (
        inmueble_referencia is not None
        and inmueble_referencia.id != excluir_id
    ):
        return "Ya existe un inmueble con esa referencia."

    inmueble_codigo = session.scalar(
        select(Inmueble).where(
            Inmueble.codigo_facturacion == codigo_facturacion
        )
    )

    if (
        inmueble_codigo is not None
        and inmueble_codigo.id != excluir_id
    ):
        return "Ya existe un inmueble con ese código de facturación."

    return None


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
            titulo="Nuevo inmueble",
            database_name=get_database_name(),
        )

    valores, error = _validar_datos_inmueble(request.form)

    if error:
        return (
            render_template(
                "inmuebles/nuevo.html",
                datos=request.form,
                error=error,
                titulo="Nuevo inmueble",
                database_name=get_database_name(),
            ),
            400,
        )

    session_factory = get_session_factory()

    with session_factory() as session:
        error = _buscar_duplicado(
            session,
            valores["referencia"],
            valores["codigo_facturacion"],
        )

        if error:
            return (
                render_template(
                    "inmuebles/nuevo.html",
                    datos=request.form,
                    error=error,
                    titulo="Nuevo inmueble",
                    database_name=get_database_name(),
                ),
                400,
            )

        inmueble = Inmueble(**valores)

        session.add(inmueble)
        session.commit()

    return redirect(url_for("inmuebles.listar_inmuebles"))


@bp.route("/<int:inmueble_id>/editar", methods=["GET", "POST"])
def editar_inmueble(inmueble_id: int):
    """Permite modificar los datos de un inmueble existente."""
    session_factory = get_session_factory()

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        if inmueble is None:
            return "Inmueble no encontrado.", 404

        if request.method == "GET":
            datos = {
                "referencia": inmueble.referencia,
                "codigo_facturacion": inmueble.codigo_facturacion,
                "descripcion": inmueble.descripcion,
                "direccion": inmueble.direccion,
                "codigo_postal": inmueble.codigo_postal or "",
                "poblacion": inmueble.poblacion,
                "provincia": inmueble.provincia,
                "ref_catastral": inmueble.ref_catastral or "",
                "seguro": inmueble.seguro or "",
                "participacion": f"{inmueble.participacion / 100:.2f}".replace(
                    ".",
                    ",",
                ),
                "notas": inmueble.notas or "",
            }

            return render_template(
                "inmuebles/nuevo.html",
                datos=datos,
                error=None,
                titulo="Editar inmueble",
                database_name=get_database_name(),
            )

        valores, error = _validar_datos_inmueble(request.form)

        if error:
            return (
                render_template(
                    "inmuebles/nuevo.html",
                    datos=request.form,
                    error=error,
                    titulo="Editar inmueble",
                    database_name=get_database_name(),
                ),
                400,
            )

        error = _buscar_duplicado(
            session,
            valores["referencia"],
            valores["codigo_facturacion"],
            excluir_id=inmueble.id,
        )

        if error:
            return (
                render_template(
                    "inmuebles/nuevo.html",
                    datos=request.form,
                    error=error,
                    titulo="Editar inmueble",
                    database_name=get_database_name(),
                ),
                400,
            )

        for campo, valor in valores.items():
            setattr(inmueble, campo, valor)

        session.commit()

    return redirect(url_for("inmuebles.listar_inmuebles"))


@bp.route("/<int:inmueble_id>/estado", methods=["GET", "POST"])
def cambiar_estado_inmueble(inmueble_id: int):
    """Permite activar o desactivar un inmueble previa confirmación."""
    session_factory = get_session_factory()

    with session_factory() as session:
        inmueble = session.get(Inmueble, inmueble_id)

        if inmueble is None:
            return "Inmueble no encontrado.", 404

        accion = "Desactivar" if inmueble.activo else "Activar"

        if request.method == "GET":
            return render_template(
                "inmuebles/estado.html",
                inmueble=inmueble,
                accion=accion,
                database_name=get_database_name(),
            )

        inmueble.activo = not inmueble.activo
        session.commit()

    return redirect(url_for("inmuebles.listar_inmuebles"))

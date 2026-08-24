"""Define las rutas web para consultar y mantener inquilinos."""

from flask import Blueprint, redirect, render_template, request, url_for
from sqlalchemy import select

from contab.context import get_database_name, get_session_factory
from contab.models import Inquilino


bp = Blueprint(
    "inquilinos",
    __name__,
    url_prefix="/inquilinos",
    template_folder="templates",
)


def _validar_datos_inquilino(datos) -> tuple[dict, str | None]:
    """Valida los datos del formulario y devuelve valores normalizados."""
    if not datos["nombre"].strip():
        return {}, "El nombre es obligatorio."

    if not datos["nif"].strip():
        return {}, "El NIF es obligatorio."

    valores = {
        "nombre": datos["nombre"].strip(),
        "nif": datos["nif"].strip(),
        "direccion": datos["direccion"].strip() or None,
        "codigo_postal": datos["codigo_postal"].strip() or None,
        "poblacion": datos["poblacion"].strip() or None,
        "provincia": datos["provincia"].strip() or None,
        "email": datos["email"].strip() or None,
        "telefono": datos["telefono"].strip() or None,
        "notas": datos["notas"].strip() or None,
    }

    return valores, None


def _buscar_nif_duplicado(
    session,
    nif: str,
    excluir_id: int | None = None,
) -> str | None:
    """Detecta si el NIF ya pertenece a otro inquilino."""
    inquilino = session.scalar(
        select(Inquilino).where(
            Inquilino.nif == nif
        )
    )

    if inquilino is not None and inquilino.id != excluir_id:
        return "Ya existe un inquilino con ese NIF."

    return None


@bp.get("/")
def listar_inquilinos():
    """Muestra el listado de inquilinos registrados."""
    session_factory = get_session_factory()

    with session_factory() as session:
        inquilinos = session.scalars(
            select(Inquilino).order_by(Inquilino.nombre)
        ).all()

        return render_template(
            "inquilinos/lista.html",
            inquilinos=inquilinos,
            database_name=get_database_name(),
        )


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo_inquilino():
    """Permite introducir y guardar un nuevo inquilino."""
    if request.method == "GET":
        return render_template(
            "inquilinos/formulario.html",
            titulo="Nuevo inquilino",
            datos={},
            error=None,
            database_name=get_database_name(),
        )

    valores, error = _validar_datos_inquilino(request.form)

    if error:
        return (
            render_template(
                "inquilinos/formulario.html",
                titulo="Nuevo inquilino",
                datos=request.form,
                error=error,
                database_name=get_database_name(),
            ),
            400,
        )

    session_factory = get_session_factory()

    with session_factory() as session:
        with session.begin():
            error = _buscar_nif_duplicado(
                session,
                valores["nif"],
            )

            if error:
                return (
                    render_template(
                        "inquilinos/formulario.html",
                        titulo="Nuevo inquilino",
                        datos=request.form,
                        error=error,
                        database_name=get_database_name(),
                    ),
                    400,
                )

            inquilino = Inquilino(**valores)
            session.add(inquilino)

    return redirect(url_for("inquilinos.listar_inquilinos"))


@bp.route("/<int:inquilino_id>/editar", methods=["GET", "POST"])
def editar_inquilino(inquilino_id: int):
    """Permite modificar los datos de un inquilino existente."""
    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            inquilino = session.get(Inquilino, inquilino_id)

            if inquilino is None:
                return "Inquilino no encontrado.", 404

            datos = {
                "nombre": inquilino.nombre,
                "nif": inquilino.nif,
                "direccion": inquilino.direccion or "",
                "codigo_postal": inquilino.codigo_postal or "",
                "poblacion": inquilino.poblacion or "",
                "provincia": inquilino.provincia or "",
                "email": inquilino.email or "",
                "telefono": inquilino.telefono or "",
                "notas": inquilino.notas or "",
            }

            return render_template(
                "inquilinos/formulario.html",
                titulo="Editar inquilino",
                datos=datos,
                error=None,
                database_name=get_database_name(),
            )

    valores, error = _validar_datos_inquilino(request.form)

    if error:
        return (
            render_template(
                "inquilinos/formulario.html",
                titulo="Editar inquilino",
                datos=request.form,
                error=error,
                database_name=get_database_name(),
            ),
            400,
        )

    with session_factory() as session:
        with session.begin():
            inquilino = session.get(Inquilino, inquilino_id)

            if inquilino is None:
                return "Inquilino no encontrado.", 404

            error = _buscar_nif_duplicado(
                session,
                valores["nif"],
                excluir_id=inquilino.id,
            )

            if error:
                return (
                    render_template(
                        "inquilinos/formulario.html",
                        titulo="Editar inquilino",
                        datos=request.form,
                        error=error,
                        database_name=get_database_name(),
                    ),
                    400,
                )

            for campo, valor in valores.items():
                setattr(inquilino, campo, valor)

    return redirect(url_for("inquilinos.listar_inquilinos"))



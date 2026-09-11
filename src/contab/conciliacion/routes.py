"""Define las rutas web de conciliación bancaria."""

from flask import (
    Blueprint,
    render_template,
    request,
)

from contab.conciliacion.importacion import (
    ImportacionBancariaError,
    leer_csv_bancario,
    preparar_movimientos_bancarios,
)
from contab.context import (
    get_bank_name,
    get_database_name,
    get_session_factory,
)


bp = Blueprint(
    "conciliacion",
    __name__,
    url_prefix="/conciliacion",
    template_folder="templates",
)


def _render_formulario_importacion(
    *,
    error: str | None = None,
    resultado: str | None = None,
):
    """Muestra el formulario con todo su contexto."""

    return render_template(
        "conciliacion/importar.html",
        banco=get_bank_name(),
        error=error,
        resultado=resultado,
        database_name=get_database_name(),
    )


@bp.route("/importar", methods=["GET", "POST"])
def importar_movimientos():
    """Importa los movimientos del banco configurado."""

    if request.method == "GET":
        return _render_formulario_importacion()

    archivo = request.files.get("archivo")

    if archivo is None or not archivo.filename:
        return (
            _render_formulario_importacion(
                error="Debe seleccionar un archivo CSV.",
            ),
            400,
        )

    try:
        contenido = archivo.read().decode(
            "utf-8-sig"
        )

        importados = leer_csv_bancario(
            banco=get_bank_name(),
            contenido=contenido,
        )

    except UnicodeDecodeError:
        return (
            _render_formulario_importacion(
                error=(
                    "El archivo CSV no está codificado "
                    "en UTF-8."
                ),
            ),
            400,
        )

    except ImportacionBancariaError as exc:
        return (
            _render_formulario_importacion(
                error=str(exc),
            ),
            400,
        )

    session_factory = get_session_factory()

    with session_factory() as session:
        with session.begin():
            nuevos = preparar_movimientos_bancarios(
                session=session,
                movimientos=importados,
            )

            session.add_all(nuevos)

    existentes = len(importados) - len(nuevos)

    resultado = (
        f"Movimientos importados: {len(nuevos)}. "
        f"Ya existentes: {existentes}."
    )

    return _render_formulario_importacion(
        resultado=resultado,
    )



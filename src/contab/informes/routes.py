"""Define las rutas web para informes y exportaciones."""

from datetime import date
from flask import (
    Blueprint,
    Response,
    render_template,
    request,
)
from sqlalchemy import select
from werkzeug.utils import secure_filename

from contab.context import (
    get_database_name,
    get_session_factory,
)
from contab.informes.services import (
    generar_csv_iva,
    generar_zip_iva,
)
from contab.models import ApunteContable, Inmueble



bp = Blueprint(
    "informes",
    __name__,
    url_prefix="/informes",
    template_folder="templates",
)


@bp.get("/")
def indice():
    """Muestra los informes y exportaciones disponibles."""
    return render_template(
        "informes/indice.html",
        database_name=get_database_name(),
    )


@bp.route("/iva", methods=["GET", "POST"])
def exportar_iva():
    """Prepara y descarga la exportación anual para IVA."""
    session_factory = get_session_factory()

    with session_factory() as session:
        inmuebles = session.scalars(
            select(Inmueble).order_by(
                Inmueble.referencia
            )
        ).all()

        if request.method == "GET":
            return render_template(
                "informes/iva.html",
                inmuebles=inmuebles,
                anio=date.today().year,
                error=None,
                database_name=get_database_name(),
            )

        try:
            seleccion = request.form[
                "inmueble_id"
            ]
            anio = int(request.form["anio"])

            if not 1 <= anio <= 9999:
                raise ValueError

            inmueble_id = (
                None
                if seleccion == "todos"
                else int(seleccion)
            )

        except (KeyError, ValueError):
            return (
                render_template(
                    "informes/iva.html",
                    inmuebles=inmuebles,
                    anio=request.form.get(
                        "anio",
                        date.today().year,
                    ),
                    error=(
                        "Debe seleccionar un inmueble "
                        "e indicar un año válido."
                    ),
                    database_name=get_database_name(),
                ),
                400,
            )

        inmueble = None

        if inmueble_id is not None:
            inmueble = session.get(
                Inmueble,
                inmueble_id,
            )

            if inmueble is None:
                return (
                    render_template(
                        "informes/iva.html",
                        inmuebles=inmuebles,
                        anio=anio,
                        error=(
                            "El inmueble seleccionado "
                            "no existe."
                        ),
                        database_name=get_database_name(),
                    ),
                    400,
                )

        consulta = (
            select(ApunteContable)
            .where(
                ApunteContable.fecha
                >= date(anio, 1, 1),
                ApunteContable.fecha
                <= date(anio, 12, 31),
            )
            .order_by(
                ApunteContable.fecha,
                ApunteContable.id,
            )
        )

        if inmueble_id is not None:
            consulta = consulta.where(
                ApunteContable.inmueble_id
                == inmueble_id
            )

        apuntes = session.scalars(
            consulta
        ).all()

        if inmueble_id is None:
            contenido = generar_zip_iva(
                inmuebles=inmuebles,
                apuntes=apuntes,
                anio=anio,
            )

            response = Response(
                contenido,
                content_type="application/zip",
            )
            response.headers[
                "Content-Disposition"
            ] = (
                f'attachment; filename="'
                f'iva-{anio}.zip"'
            )

            return response

        contenido = generar_csv_iva(
            inmueble=inmueble,
            apuntes=apuntes,
            anio=anio,
        )

        referencia = (
            secure_filename(inmueble.referencia)
            or f"inmueble-{inmueble.id}"
        )
        nombre_archivo = (
            f"iva-{referencia}-{anio}.csv"
        )

        response = Response(
            contenido,
            content_type=(
                "text/csv; charset=utf-8"
            ),
        )
        response.headers[
            "Content-Disposition"
        ] = (
            f'attachment; filename="'
            f'{nombre_archivo}"'
        )

        return response


def test_exportar_iva_rechaza_formulario_incompleto() -> None:
    """Comprueba que inmueble y año son obligatorios."""
    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        "/informes/iva",
        data={
            "inmueble_id": "",
            "anio": "",
        },
    )

    assert response.status_code == 400
    assert (
        "Debe seleccionar un inmueble "
        "e indicar un año válido."
        in response.text
    )
    assert 'name="inmueble_id"' in response.text
    assert 'name="anio"' in response.text


def test_exportar_iva_rechaza_inmueble_inexistente() -> None:
    """Comprueba que el inmueble solicitado debe existir."""
    app = crear_app_test()
    client = app.test_client()

    client.post(
        "/",
        data={"database": "test"},
    )

    response = client.post(
        "/informes/iva",
        data={
            "inmueble_id": "999999",
            "anio": "2026",
        },
    )

    assert response.status_code == 400
    assert (
        "El inmueble seleccionado no existe."
        in response.text
    )
    assert 'value="2026"' in response.text




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
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)

from contab.context import (
    get_database_name,
    get_session_factory,
)
from contab.informes.services import (
    generar_csv_iva,
    generar_csv_resumen_iva,
    generar_zip_iva,
)
from contab.models import (
    ApunteContable,
    Contrato,
    Inmueble,
)



bp = Blueprint(
    "informes",
    __name__,
    url_prefix="/informes",
    template_folder="templates",
)



def _porcentaje_a_entero(valor: str) -> int:
    """Convierte un porcentaje a centésimas de porcentaje."""
    texto = valor.strip().replace(",", ".")

    try:
        porcentaje = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError from exc

    return int(
        (porcentaje * 100).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
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


@bp.route(
    "/iva-resumen-anual",
    methods=["GET", "POST"],
)
def resumen_anual_iva():
    """Prepara y descarga el resumen anual de IVA."""
    if request.method == "GET":
        return render_template(
            "informes/iva_resumen_anual.html",
            anio=date.today().year,
            porcentaje_irpf_estimado="24,00",
            error=None,
            database_name=get_database_name(),
        )

    try:
        anio = int(request.form["anio"])
        porcentaje_texto = request.form[
            "porcentaje_irpf_estimado"
        ]
        porcentaje_irpf_estimado = (
            _porcentaje_a_entero(
                porcentaje_texto
            )
        )

        if not 1 <= anio <= 9999:
            raise ValueError

        if not 0 <= porcentaje_irpf_estimado <= 10000:
            raise ValueError

    except (KeyError, ValueError):
        return (
            render_template(
                "informes/iva_resumen_anual.html",
                anio=request.form.get(
                    "anio",
                    date.today().year,
                ),
                porcentaje_irpf_estimado=(
                    request.form.get(
                        "porcentaje_irpf_estimado",
                        "24,00",
                    )
                ),
                error=(
                    "Debe indicar un año y un porcentaje "
                    "IRPF / IRNR válidos."
                ),
                database_name=get_database_name(),
            ),
            400,
        )

    session_factory = get_session_factory()

    with session_factory() as session:
        inmuebles = session.scalars(
            select(Inmueble).order_by(
                Inmueble.referencia
            )
        ).all()

        contratos = session.scalars(
            select(Contrato)
        ).all()

        apuntes = session.scalars(
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
        ).all()

        contenido = generar_csv_resumen_iva(
            inmuebles=inmuebles,
            contratos=contratos,
            apuntes=apuntes,
            anio=anio,
            porcentaje_irpf_estimado=(
                porcentaje_irpf_estimado
            ),
        )

    response = Response(
        contenido,
        content_type="text/csv; charset=utf-8",
    )
    response.headers["Content-Disposition"] = (
        f'attachment; filename="'
        f'iva-resumen-anual-{anio}.csv"'
    )

    return response



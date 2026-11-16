"""Define las rutas web para informes y exportaciones."""

from datetime import date
from io import BytesIO
from flask import (
    Blueprint,
    render_template,
    request,
    send_file,
)
from sqlalchemy import select
from werkzeug.utils import secure_filename
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)

from contab.config import cargar_categorias_contables
from contab.formato import importe_a_texto
from contab.informes.xlsx import (
    generar_xlsx_ingresos_gastos,
    generar_xlsx_resumen_iva,
)
from contab.context import (
    get_database_name,
    get_session_factory,
)
from contab.informes.services import (
    preparar_ingresos_gastos_anuales,
    preparar_resumen_anual_iva,
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


@bp.get("/iva-resumen-anual")
def resumen_anual_iva():
    """Consulta el resumen anual de IVA en pantalla."""

    anio_texto = request.args.get(
        "anio",
        str(date.today().year),
    ).strip()

    porcentaje_texto = request.args.get(
        "porcentaje_irpf_estimado",
        "24,00",
    ).strip()

    # La primera visita utiliza el criterio predeterminado.
    # En consultas posteriores, una casilla desmarcada
    # no aparece entre los parámetros del formulario.
    descontar_gastos = (
        "descontar_gastos" in request.args
        if request.args
        else True
    )

    try:
        anio = int(anio_texto)
        porcentaje_irpf_estimado = _porcentaje_a_entero(
            porcentaje_texto
        )

        if not 1 <= anio <= 9999:
            raise ValueError

        if not 0 <= porcentaje_irpf_estimado <= 10000:
            raise ValueError

    except ValueError:
        return (
            "Debe indicar un año y un porcentaje "
            "IRPF / IRNR válidos.",
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
                ApunteContable.fecha >= date(anio, 1, 1),
                ApunteContable.fecha <= date(anio, 12, 31),
            )
            .order_by(
                ApunteContable.fecha,
                ApunteContable.id,
            )
        ).all()

        filas = preparar_resumen_anual_iva(
            inmuebles=inmuebles,
            contratos=contratos,
            apuntes=apuntes,
            anio=anio,
            porcentaje_irpf_estimado=porcentaje_irpf_estimado,
            descontar_gastos=descontar_gastos,
        )

        if request.args.get("exportar") == "xlsx":
            contenido = generar_xlsx_resumen_iva(filas)

            return send_file(
                BytesIO(contenido),
                as_attachment=True,
                download_name=(
                    f"iva-resumen-anual-{anio}.xlsx"
                ),
                mimetype=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
            )

        return render_template(
            "informes/iva_resumen_anual.html",
            filas=filas,
            anio=anio,
            porcentaje_irpf_estimado=porcentaje_texto,
            importe_a_texto=importe_a_texto,
            database_name=get_database_name(),
            descontar_gastos=descontar_gastos,
        )


@bp.get("/ingresos-gastos-anuales")
def ingresos_gastos_anuales():
    """Consulta o exporta ingresos y gastos anuales."""

    anio_texto = request.args.get(
        "anio",
        str(date.today().year),
    ).strip()

    seleccion = request.args.get(
        "inmueble_id",
        "",
    ).strip()

    exportar = request.args.get("exportar") == "xlsx"

    try:
        anio = int(anio_texto)

        if not 1 <= anio <= 9999:
            raise ValueError

    except ValueError:
        return "Debe indicar un ejercicio válido.", 400

    if seleccion not in {"", "todos"}:
        try:
            inmueble_id = int(seleccion)
        except ValueError:
            return "Debe seleccionar un inmueble válido.", 400
    else:
        inmueble_id = None

    if exportar and not seleccion:
        return "Debe seleccionar un inmueble.", 400

    session_factory = get_session_factory()

    with session_factory() as session:
        inmuebles = session.scalars(
            select(Inmueble).order_by(Inmueble.referencia)
        ).all()

        informes = []

        if seleccion:
            if seleccion == "todos":
                seleccionados = inmuebles
            else:
                inmueble = session.get(Inmueble, inmueble_id)

                if inmueble is None:
                    return (
                        "El inmueble seleccionado no existe.",
                        404,
                    )

                seleccionados = [inmueble]

            if exportar or seleccion != "todos":
                categorias = cargar_categorias_contables()

                # Incluye apuntes propios y los que tengan
                # distribuciones persistidas a los hijos.
                apuntes = session.scalars(
                    select(ApunteContable)
                    .where(
                        ApunteContable.fecha >= date(anio, 1, 1),
                        ApunteContable.fecha <= date(anio, 12, 31),
                    )
                    .order_by(
                        ApunteContable.fecha,
                        ApunteContable.id,
                    )
                ).all()

                informes = [
                    preparar_ingresos_gastos_anuales(
                        inmueble=inmueble,
                        apuntes=apuntes,
                        categorias=categorias,
                        anio=anio,
                    )
                    for inmueble in seleccionados
                ]

        if exportar:
            contenido = generar_xlsx_ingresos_gastos(informes)

            nombre = (
                f"ingresos-gastos-{anio}.xlsx"
                if seleccion == "todos"
                else (
                    "ingresos-gastos-"
                    f"{secure_filename(informes[0]['inmueble'].referencia)}"
                    f"-{anio}.xlsx"
                )
            )

            return send_file(
                BytesIO(contenido),
                as_attachment=True,
                download_name=nombre,
                mimetype=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
            )

        informe = informes[0] if informes else None

        return render_template(
            "informes/ingresos_gastos_anuales.html",
            inmuebles=inmuebles,
            seleccion=seleccion,
            anio=anio,
            informe=informe,
            importe_a_texto=importe_a_texto,
            database_name=get_database_name(),
        )


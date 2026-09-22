"""Define las rutas web del módulo de facturación."""

from datetime import date, datetime
from sqlalchemy import select
from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    url_for,
)

from contab.models import Contrato
from contab.config import cargar_categorias_contables
from contab.context import (
    get_database_name,
    get_session_factory,
)
from contab.facturacion.services import (
    FacturacionError,
    contabilizar_ingreso_sin_factura,
    emitir_factura,
    preparar_periodo_facturacion,
)



bp = Blueprint(
    "facturacion",
    __name__,
    url_prefix="/facturacion",
    template_folder="templates",
)


def _render_lista(
    *,
    preparacion,
    periodo_texto: str,
    fecha_emision_texto: str,
    error: str | None = None,
):
    """Muestra la preparación mensual de facturación."""

    return render_template(
        "facturacion/lista.html",
        preparacion=preparacion,
        periodo_texto=periodo_texto,
        fecha_emision_texto=fecha_emision_texto,
        importe_a_texto=_importe_a_texto,
        error=error,
        database_name=get_database_name(),
    )


def _importe_a_texto(importe: int) -> str:
    """Convierte un importe en céntimos a texto."""

    euros, centimos = divmod(importe, 100)

    euros_texto = f"{euros:,}".replace(",", ".")

    return f"{euros_texto},{centimos:02d} €"


def _valores_iniciales_facturacion(
    hoy: date,
) -> tuple[date, date]:
    """Calcula período y fecha de emisión iniciales."""

    if hoy.month == 12:
        periodo = date(
            hoy.year + 1,
            1,
            1,
        )
    else:
        periodo = date(
            hoy.year,
            hoy.month + 1,
            1,
        )

    return periodo, periodo


def _periodo(texto: str) -> date:
    """Convierte un período mm-aaaa a su primer día."""

    try:
        valor = datetime.strptime(
            texto.strip(),
            "%m-%Y",
        ).date()
    except ValueError as exc:
        raise ValueError(
            "El período no es válido o no tiene "
            "el formato mm-aaaa."
        ) from exc

    return date(
        valor.year,
        valor.month,
        1,
    )


def _fecha(texto: str) -> date:
    """Convierte una fecha dd-mm-aaaa."""

    try:
        return datetime.strptime(
            texto.strip(),
            "%d-%m-%Y",
        ).date()
    except ValueError as exc:
        raise ValueError(
            "La fecha indicada no es válida o no tiene "
            "el formato dd-mm-aaaa."
        ) from exc




@bp.get("/")
def listar():
    """Muestra la preparación de facturación de un período."""

    periodo_texto = request.args.get(
        "periodo",
        "",
    ).strip()

    fecha_emision_texto = request.args.get(
        "fecha_emision",
        "",
    ).strip()

    if not periodo_texto and not fecha_emision_texto:
        periodo, fecha_emision = (
            _valores_iniciales_facturacion(
                date.today()
            )
        )

        periodo_texto = periodo.strftime(
            "%m-%Y"
        )
        fecha_emision_texto = fecha_emision.strftime(
            "%d-%m-%Y"
        )
    else:
        try:
            periodo = _periodo(
                periodo_texto
            )
            fecha_emision = _fecha(
                fecha_emision_texto
            )
        except ValueError as exc:
            return (
                _render_lista(
                    preparacion=None,
                    periodo_texto=periodo_texto,
                    fecha_emision_texto=fecha_emision_texto,
                    error=str(exc),
                ),
                400,
            )

    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            contratos = list(
                session.scalars(
                    select(Contrato)
                    .order_by(Contrato.id)
                )
            )

            preparacion = preparar_periodo_facturacion(
                contratos=contratos,
                periodo=periodo,
                fecha_emision=fecha_emision,
            )

            return _render_lista(
                preparacion=preparacion,
                periodo_texto=periodo_texto,
                fecha_emision_texto=fecha_emision_texto,
            )

    except FacturacionError as exc:
        return str(exc), 400


@bp.post("/emitir/<int:contrato_id>")
def emitir(contrato_id: int):
    """Emite y registra contablemente una factura."""

    periodo_texto = request.form["periodo"]
    fecha_emision_texto = request.form["fecha_emision"]

    try:
        periodo = _periodo(periodo_texto)
        fecha_emision = _fecha(fecha_emision_texto)
    except ValueError as exc:
        return str(exc), 400

    categorias = cargar_categorias_contables()
    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            with session.begin():
                contrato = session.get(
                    Contrato,
                    contrato_id,
                )

                if contrato is None:
                    return "Contrato no encontrado.", 404

                factura, apunte, movimiento = emitir_factura(
                    contrato=contrato,
                    periodo=periodo,
                    fecha_emision=fecha_emision,
                    categorias=categorias,
                )

                session.add(factura)
                session.add(apunte)
                session.add(movimiento)

    except FacturacionError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "facturacion.listar",
            periodo=periodo_texto,
            fecha_emision=fecha_emision_texto,
        )
    )


@bp.post("/contabilizar/<int:contrato_id>")
def contabilizar(contrato_id: int):
    """Contabiliza un ingreso de alquiler que no genera factura."""

    periodo_texto = request.form["periodo"]
    fecha_emision_texto = request.form["fecha_emision"]

    try:
        periodo = _periodo(periodo_texto)
        fecha = _fecha(fecha_emision_texto)
    except ValueError as exc:
        return str(exc), 400

    categorias = cargar_categorias_contables()
    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            with session.begin():
                contrato = session.get(
                    Contrato,
                    contrato_id,
                )

                if contrato is None:
                    return "Contrato no encontrado.", 404

                apunte, movimiento = (
                    contabilizar_ingreso_sin_factura(
                        contrato=contrato,
                        periodo=periodo,
                        fecha=fecha,
                        categorias=categorias,
                    )
                )

                session.add(apunte)
                session.add(movimiento)

    except FacturacionError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "facturacion.listar",
            periodo=periodo_texto,
            fecha_emision=fecha_emision_texto,
        )
    )



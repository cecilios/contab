"""Define las rutas web del módulo de facturación."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from sqlalchemy import select
from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from dataclasses import dataclass

from contab.formato import (
    fecha_a_texto,
    importe_a_texto,
    importe_a_texto_entrada,
    periodo_a_texto,
    porcentaje_a_texto_entrada,
    texto_a_fecha,
    texto_a_importe,
    texto_a_periodo,
    texto_a_porcentaje,
)
from contab.models import (
    Contrato,
    RevisionRenta,
)
from contab.config import (
    cargar_categorias_contables,
)
from contab.context import (
    get_database_name,
    get_invoice_template_path,
    get_session_factory,
)
from contab.facturacion.services import (
    CalculoFacturaError,
    FacturacionError,
    FacturaEditada,
    LineaFacturaEditada,
    calcular_importes_factura,
    contabilizar_ingreso_sin_factura,
    emitir_factura,
    preparar_datos_documento_factura,
    preparar_periodo_facturacion,
    situacion_revision,
)
from contab.contratos.services import (
    RevisionRentaError,
    renta_vigente,
    resolver_revision_renta,
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
        importe_a_texto=importe_a_texto,
        error=error,
        database_name=get_database_name(),
    )


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

        periodo_texto = periodo_a_texto(periodo)
        fecha_emision_texto = fecha_a_texto(fecha_emision)
    else:
        try:
            periodo = texto_a_periodo(
                periodo_texto
            )
            fecha_emision = texto_a_fecha(
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
    conceptos = request.form.getlist("linea_concepto")
    importes = request.form.getlist("linea_importe")
    if len(conceptos) != len(importes):
        return "Las líneas adicionales de la factura no son válidas.", 400

    try:
        periodo = texto_a_periodo(periodo_texto)
        fecha_emision = texto_a_fecha(fecha_emision_texto)
        lineas_adicionales = [
            (concepto, texto_a_importe(importe))
            for concepto, importe in zip(
                conceptos,
                importes,
                strict=True,
            )
        ]
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

                revision, revision_estado = situacion_revision(
                    contrato,
                    periodo,
                )

                if revision_estado == "PENDIENTE":
                    return (
                        "La factura no puede emitirse hasta resolver "
                        "la revisión de renta pendiente.",
                        400,
                    )

                factura, apunte, movimiento = emitir_factura(
                    contrato=contrato,
                    periodo=periodo,
                    fecha_emision=fecha_emision,
                    categorias=categorias,
                    lineas_adicionales=lineas_adicionales,
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
        periodo = texto_a_periodo(periodo_texto)
        fecha = texto_a_fecha(fecha_emision_texto)
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


@bp.get("/revisiones/<int:revision_id>/resolver")
def resolver_revision(revision_id: int):
    """Muestra el formulario para resolver una revisión de renta."""

    periodo_texto = request.args.get("periodo", "")
    fecha_emision_texto = request.args.get("fecha_emision", "")

    session_factory = get_session_factory()

    with session_factory() as session:
        revision = session.get(
            RevisionRenta,
            revision_id,
        )

        if revision is None:
            return "Revisión de renta no encontrada.", 404

        if revision.estado != "PENDIENTE":
            return "La revisión de renta ya está resuelta.", 400

        renta = renta_vigente(
            revision.contrato,
            revision.fecha_prevista,
        )

        return render_template(
            "facturacion/resolver_revision.html",
            revision=revision,
            renta=renta,
            periodo_texto=periodo_texto,
            fecha_emision_texto=fecha_emision_texto,
            importe_a_texto=importe_a_texto,
        )


@bp.post("/revisiones/<int:revision_id>/resolver")
def aplicar_revision(revision_id: int):
    """Aplica una revisión de renta pendiente."""

    periodo_texto = request.args.get("periodo", "")
    fecha_emision_texto = request.args.get(
        "fecha_emision",
        "",
    )

    try:
        porcentaje_aplicado = texto_a_porcentaje(
            request.form["porcentaje"]
        )
    except (KeyError, ValueError) as exc:
        return str(exc), 400

    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            with session.begin():
                revision = session.get(
                    RevisionRenta,
                    revision_id,
                )

                if revision is None:
                    return "Revisión de renta no encontrada.", 404

                if revision.metodo == "FIJO":
                    return (
                        "Las revisiones de tipo FIJO todavía "
                        "no pueden resolverse desde facturación.",
                        400,
                    )

                nueva_renta, siguiente_revision = (
                    resolver_revision_renta(
                        revision=revision,
                        fecha_resolucion=date.today(),
                        aplicar=True,
                        porcentaje_aplicado=porcentaje_aplicado,
                    )
                )

                if nueva_renta is not None:
                    session.add(nueva_renta)

                session.add(siguiente_revision)

    except RevisionRentaError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "facturacion.listar",
            periodo=periodo_texto,
            fecha_emision=fecha_emision_texto,
        )
    )


@bp.get("/facturas/<int:contrato_id>/modificar")
def modificar_factura(contrato_id: int):
    """Muestra el formulario de una factura preparada."""

    periodo_texto = request.args.get(
        "periodo",
        "",
    ).strip()
    fecha_emision_texto = request.args.get(
        "fecha_emision",
        "",
    ).strip()

    try:
        periodo = texto_a_periodo(periodo_texto)
        fecha_emision = texto_a_fecha(
            fecha_emision_texto
        )
    except ValueError as exc:
        return str(exc), 400

    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            contrato = session.get(
                Contrato,
                contrato_id,
            )

            if contrato is None:
                return "Contrato no encontrado.", 404

            preparacion = preparar_periodo_facturacion(
                contratos=[contrato],
                periodo=periodo,
                fecha_emision=fecha_emision,
            )

            if not preparacion.locales:
                return (
                    "No existe una factura preparada "
                    "para este contrato y período.",
                    400,
                )

            factura = preparacion.locales[0]

            if factura.factura is not None:
                return "La factura ya ha sido emitida.", 400

            if factura.revision_estado == "PENDIENTE":
                return (
                    "La factura no puede modificarse hasta "
                    "resolver la revisión de renta pendiente.",
                    400,
                )

            lineas_formulario = [
                {
                    "concepto": factura.contrato.concepto_factura,
                    "importe": importe_a_texto_entrada(
                        factura.base
                    ),
                }
            ]

            while len(lineas_formulario) < 5:
                lineas_formulario.append(
                    {
                        "concepto": "",
                        "importe": "",
                    }
                )

            notas_formulario = ["", "", ""]

            return render_template(
                "facturacion/formulario.html",
                factura=factura,
                lineas_formulario=lineas_formulario,
                notas_formulario=notas_formulario,
                periodo_texto=periodo_texto,
                fecha_emision_texto=fecha_emision_texto,
                importe_a_texto=importe_a_texto,
                iva_porcentaje_texto=porcentaje_a_texto_entrada(
                    factura.contrato.iva_porcentaje
                ),
                retencion_porcentaje_texto=porcentaje_a_texto_entrada(
                    factura.contrato.retencion_porcentaje
                ),
            )

    except FacturacionError as exc:
        return str(exc), 400


@bp.post("/facturas/<int:contrato_id>/modificar")
def previsualizar_factura(contrato_id: int):
    """Valida los datos editados y muestra la factura."""

    periodo_texto = request.args.get(
        "periodo",
        "",
    ).strip()
    fecha_emision_texto = request.args.get(
        "fecha_emision",
        "",
    ).strip()

    try:
        periodo = texto_a_periodo(periodo_texto)
        fecha_emision = texto_a_fecha(
            fecha_emision_texto
        )
    except ValueError as exc:
        return str(exc), 400

    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            contrato = session.get(
                Contrato,
                contrato_id,
            )

            if contrato is None:
                return "Contrato no encontrado.", 404

            preparacion = preparar_periodo_facturacion(
                contratos=[contrato],
                periodo=periodo,
                fecha_emision=fecha_emision,
            )

            if not preparacion.locales:
                return (
                    "No existe una factura preparada "
                    "para este contrato y período.",
                    400,
                )

            factura = preparacion.locales[0]

            if factura.factura is not None:
                return "La factura ya ha sido emitida.", 400

            if factura.revision_estado == "PENDIENTE":
                return (
                    "La factura no puede modificarse hasta "
                    "resolver la revisión de renta pendiente.",
                    400,
                )

            conceptos = request.form.getlist(
                "linea_concepto"
            )
            importes_texto = request.form.getlist(
                "linea_importe"
            )

            if len(conceptos) != len(importes_texto):
                return (
                    "Las líneas de la factura no son válidas.",
                    400,
                )

            lineas: list[LineaFacturaEditada] = []

            for concepto, importe_texto in zip(
                conceptos,
                importes_texto,
                strict=True,
            ):
                concepto = concepto.strip()
                importe_texto = importe_texto.strip()

                if not concepto and not importe_texto:
                    continue

                if not concepto or not importe_texto:
                    return (
                        "Cada línea debe tener concepto "
                        "e importe.",
                        400,
                    )

                try:
                    importe = texto_a_importe(
                        importe_texto
                    )
                except ValueError as exc:
                    return str(exc), 400

                lineas.append(
                    LineaFacturaEditada(
                        concepto=concepto,
                        importe=importe,
                    )
                )

            if not lineas:
                return (
                    "La factura debe tener al menos "
                    "una línea.",
                    400,
                )

            try:
                iva_porcentaje = texto_a_porcentaje(
                    request.form.get(
                        "iva_porcentaje",
                        "",
                    )
                )
                retencion_porcentaje = (
                    texto_a_porcentaje(
                        request.form.get(
                            "retencion_porcentaje",
                            "",
                        )
                    )
                )
            except ValueError as exc:
                return str(exc), 400

            notas = [
                texto.strip()
                for texto in request.form.getlist(
                    "nota_texto"
                )
                if texto.strip()
            ]

            try:
                calculo = calcular_importes_factura(
                    importes=[
                        linea.importe
                        for linea in lineas
                    ],
                    iva_porcentaje=iva_porcentaje,
                    retencion_porcentaje=retencion_porcentaje,
                )
            except CalculoFacturaError as exc:
                return str(exc), 400

            factura_editada = FacturaEditada(
                lineas=lineas,
                notas=notas,
                iva_porcentaje=iva_porcentaje,
                retencion_porcentaje=retencion_porcentaje,
                base=calculo.base,
                iva_importe=calculo.iva_importe,
                retencion_importe=calculo.retencion_importe,
                total=calculo.total,
            )

            datos_documento = preparar_datos_documento_factura(
                factura=factura,
                factura_editada=factura_editada,
                fecha_emision=fecha_emision,
            )

            ruta_plantilla = get_invoice_template_path()

            if not ruta_plantilla.is_file():
                return (
                    "No se encuentra la plantilla de factura: "
                    f"{ruta_plantilla}",
                    500,
                )

            try:
                texto_plantilla = ruta_plantilla.read_text(
                    encoding="utf-8"
                )
            except OSError as exc:
                return (
                    "No se pudo leer la plantilla de factura: "
                    f"{exc}",
                    500,
                )

            plantilla = current_app.jinja_env.from_string(
                texto_plantilla
            )

            return plantilla.render(
                factura=datos_documento,
                importe_a_texto=importe_a_texto,
                porcentaje_a_texto=porcentaje_a_texto_entrada,
            )

    except FacturacionError as exc:
        return str(exc), 400



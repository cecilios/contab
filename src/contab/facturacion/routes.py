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
    send_file,
    url_for,
)
from dataclasses import dataclass

from contab.formato import (
    fecha_a_texto,
    fecha_a_texto_largo,
    importe_a_texto,
    importe_a_texto_entrada,
    nombre_mes,
    periodo_a_texto,
    periodo_a_texto_largo,
    porcentaje_a_texto_entrada,
    texto_a_fecha,
    texto_a_importe,
    texto_a_periodo,
    texto_a_porcentaje,
)
from contab.models import (
    Contrato,
    Factura,
    Inmueble,
    RevisionRenta,
)
from contab.config import (
    cargar_categorias_contables,
)
from contab.context import (
    get_database_name,
    get_invoice_template_path,
    get_session_factory,
    obtener_ruta_de_la_firma,
)
from contab.facturacion.services import (
    CalculoFacturaError,
    FacturacionError,
    FacturaEditada,
    LineaFacturaEditada,
    calcular_importes_factura,
    componer_destinatario,
    contabilizar_ingreso_sin_factura,
    emitir_factura,
    notas_automaticas_factura,
    preparar_datos_documento_factura,
    preparar_eliminacion_factura,
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
        error=error,
        database_name=get_database_name(),
        importe_a_texto=importe_a_texto,
        importe_a_texto_entrada=importe_a_texto_entrada,
        porcentaje_a_texto_entrada=porcentaje_a_texto_entrada,
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


def _factura_editada_desde_formulario(
    formulario,
) -> FacturaEditada:
    """Valida los datos del formulario y prepara la factura editada."""

    conceptos = formulario.getlist(
        "linea_concepto"
    )
    importes_texto = formulario.getlist(
        "linea_importe"
    )

    if len(conceptos) != len(importes_texto):
        raise ValueError("Las líneas de la factura no son válidas.")

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
            raise ValueError("Cada línea debe tener concepto e importe.")

        importe = texto_a_importe(
            importe_texto
        )

        lineas.append(
            LineaFacturaEditada(
                concepto=concepto,
                importe=importe,
            )
        )

    if not lineas:
        raise ValueError("La factura debe tener al menos una línea.")

    iva_porcentaje = texto_a_porcentaje(
        formulario.get(
            "iva_porcentaje",
            "",
        )
    )

    retencion_porcentaje = texto_a_porcentaje(
        formulario.get(
            "retencion_porcentaje",
            "",
        )
    )

    notas = [
        nota.strip()
        for nota in formulario.getlist("nota_texto")
        if nota.strip()
    ]

    calculo = calcular_importes_factura(
        importes=[
            linea.importe
            for linea in lineas
        ],
        iva_porcentaje=iva_porcentaje,
        retencion_porcentaje=retencion_porcentaje,
    )

    return FacturaEditada(
        lineas=lineas,
        notas=notas,
        iva_porcentaje=iva_porcentaje,
        retencion_porcentaje=retencion_porcentaje,
        base=calculo.base,
        iva_importe=calculo.iva_importe,
        retencion_importe=calculo.retencion_importe,
        total=calculo.total,
    )



@bp.get("/")
def listar():
    """Muestra la preparación de facturación de un período."""

    periodo_texto = request.args.get(
        "periodo",
        "",
    ).strip()

    if not periodo_texto:
        periodo, _ = _valores_iniciales_facturacion(
            date.today()
        )
        periodo_texto = periodo_a_texto(periodo)
    else:
        try:
            periodo = texto_a_periodo(
                periodo_texto
            )
        except ValueError as exc:
            return (
                _render_lista(
                    preparacion=None,
                    periodo_texto=periodo_texto,
                    fecha_emision_texto="",
                    error=str(exc),
                ),
                400,
            )

    fecha_emision = periodo
    fecha_emision_texto = fecha_a_texto(
        fecha_emision
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


@bp.get("/facturas")
def listar_facturas():
    """Muestra la tabla con las facturas persistidas."""

    anio_texto = request.args.get(
        "anio",
        str(date.today().year),
    ).strip()

    try:
        anio = int(anio_texto)
    except ValueError:
        return "El año no es válido.", 400

    inmueble_id_texto = request.args.get(
        "inmueble_id",
        "",
    ).strip()

    inmueble_id = None

    if inmueble_id_texto:
        try:
            inmueble_id = int(
                inmueble_id_texto
            )
        except ValueError:
            return "El inmueble no es válido.", 400

    session_factory = get_session_factory()

    with session_factory() as session:
        consulta = (
            select(Factura)
            .join(Factura.contrato)
            .join(Contrato.inmueble)
            .where(Factura.anio == anio)
        )

        if inmueble_id is not None:
            consulta = consulta.where(
                Contrato.inmueble_id
                == inmueble_id
            )

        consulta = consulta.order_by(
            Factura.fecha_emision.desc(),
            Factura.id.desc(),
        )

        facturas = list(
            session.scalars(consulta)
        )

        inmuebles = list(
            session.scalars(
                select(Inmueble)
                .where(Inmueble.tipo != "T")
                .order_by(Inmueble.referencia)
            )
        )

        destinatarios = {
            factura.id: " / ".join(
                destinatario.nombre
                for destinatario in factura.destinatarios
            )
            for factura in facturas
        }

        return render_template(
            "facturacion/facturas.html",
            facturas=facturas,
            destinatarios=destinatarios,
            inmuebles=inmuebles,
            anio_texto=anio_texto,
            inmueble_id=inmueble_id,
            database_name=get_database_name(),
            fecha_a_texto=fecha_a_texto,
            importe_a_texto=importe_a_texto,
        )


@bp.get("/facturas/<int:factura_id>")
def ver_factura(factura_id: int):
    """Muestra una factura persistida. Solo lectura."""

    session_factory = get_session_factory()

    with session_factory() as session:
        factura = session.get(
            Factura,
            factura_id,
        )

        if factura is None:
            return "Factura no encontrada.", 404

        destinatarios = sorted(
            factura.destinatarios,
            key=lambda destinatario: destinatario.orden,
        )

        lineas = sorted(
            factura.lineas,
            key=lambda linea: linea.orden,
        )

        notas = (
            factura.notas.splitlines()
            if factura.notas
            else []
        )

        return render_template(
            "facturacion/factura_detalle.html",
            factura=factura,
            lineas=lineas,
            notas=notas,
            destinatarios=destinatarios,
            database_name=get_database_name(),
            fecha_a_texto=fecha_a_texto,
            periodo_a_texto_largo=periodo_a_texto_largo,
            importe_a_texto=importe_a_texto,
            porcentaje_a_texto=porcentaje_a_texto_entrada,
        )


@bp.post("/facturas/<int:factura_id>/eliminar")
def eliminar_factura(factura_id: int):
    """Elimina una factura emitida y su registro contable asociado."""

    session_factory = get_session_factory()

    try:
        with session_factory() as session:
            with session.begin():
                factura = session.get(
                    Factura,
                    factura_id,
                )

                if factura is None:
                    return "Factura no encontrada.", 404

                eliminacion = preparar_eliminacion_factura(
                    factura
                )

                if eliminacion.movimiento is not None:
                    session.delete(
                        eliminacion.movimiento
                    )

                for linea in list(
                    eliminacion.factura.lineas
                ):
                    session.delete(linea)

                for destinatario in list(
                    eliminacion.factura.destinatarios
                ):
                    session.delete(destinatario)

                session.delete(
                    eliminacion.factura
                )

                session.flush()

                session.delete(
                    eliminacion.apunte
                )

    except FacturacionError as exc:
        return str(exc), 400

    return redirect(
        url_for(
            "facturacion.listar_facturas"
        )
    )


@bp.post("/contabilizar/<int:contrato_id>")
def contabilizar(contrato_id: int):
    """Contabiliza un ingreso de alquiler 'Otros' que no genera factura."""

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
    """Muestra el formulario editable de una factura preparada."""

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
                    "concepto": linea.concepto,
                    "importe": importe_a_texto_entrada(
                        linea.importe
                    ),
                }
                for linea in factura.lineas
            ]

            while len(lineas_formulario) < 5:
                lineas_formulario.append(
                    {
                        "concepto": "",
                        "importe": "",
                    }
                )

            notas_formulario = list(factura.notas)

            while len(notas_formulario) < 4:
                notas_formulario.append("")

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

            try:
                factura_editada = _factura_editada_desde_formulario(
                    request.form
                )
            except ValueError as exc:
                return str(exc), 400

            datos_documento = preparar_datos_documento_factura(
                factura=factura,
                factura_editada=factura_editada,
                fecha_emision=fecha_emision,
                periodo=periodo,
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
                contrato_id=contrato_id,
                periodo_texto=periodo_texto,
                fecha_emision_texto=fecha_emision_texto,
                importe_a_texto=importe_a_texto,
                importe_a_texto_entrada=importe_a_texto_entrada,
                porcentaje_a_texto=porcentaje_a_texto_entrada,
                porcentaje_a_texto_entrada=porcentaje_a_texto_entrada,
                fecha_a_texto_largo=fecha_a_texto_largo,
                firma_url=url_for("facturacion.firma_factura"),
                contabilizar_url=url_for(
                    "facturacion.contabilizar_factura",
                    contrato_id=contrato_id,
                ),
                notas_formulario=factura_editada.notas,
            )

    except FacturacionError as exc:
        return str(exc), 400


@bp.get("/facturas/firma")
def firma_factura():
    """Devuelve la firma asociada a la base de datos activa."""

    database_name = get_database_name()

    if database_name is None:
        return "No se ha seleccionado ninguna base de datos.", 400

    ruta = obtener_ruta_de_la_firma()

    if not ruta.is_file():
        return "No se encuentra la firma de la factura.", 404

    return send_file(
        ruta,
        mimetype="image/png",
    )


@bp.post("/facturas/<int:contrato_id>/contabilizar")
def contabilizar_factura(contrato_id: int):
    """Contabiliza una factura previamente previsualizada."""

    try:
        factura_editada = _factura_editada_desde_formulario(
            request.form
        )

        base_previsualizada = int(
            request.form["base_previsualizada"]
        )
        iva_previsualizado = int(
            request.form["iva_previsualizado"]
        )
        retencion_previsualizada = int(
            request.form["retencion_previsualizada"]
        )
        total_previsualizado = int(
            request.form["total_previsualizado"]
        )
    except (ValueError, KeyError) as exc:
        return str(exc), 400

    if (
        factura_editada.base != base_previsualizada
        or factura_editada.iva_importe
        != iva_previsualizado
        or factura_editada.retencion_importe
        != retencion_previsualizada
        or factura_editada.total != total_previsualizado
    ):
        return (
            "Los importes de la factura han cambiado. "
            "Vuelve a previsualizarla antes de contabilizar.",
            400,
        )

    periodo_texto = request.form["periodo"]
    fecha_emision_texto = request.form["fecha_emision"]

    try:
        periodo = texto_a_periodo(periodo_texto)
        fecha_emision = texto_a_fecha(fecha_emision_texto)
    except (KeyError, ValueError) as exc:
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
                        "La factura no puede contabilizarse hasta "
                        "resolver la revisión de renta pendiente.",
                        400,
                    )

                factura, apunte, movimiento = emitir_factura(
                    contrato=contrato,
                    periodo=periodo,
                    fecha_emision=fecha_emision,
                    categorias=categorias,
                    factura_editada=factura_editada,
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



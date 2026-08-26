"""Define las rutas web para consultar y mantener contratos."""

from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Blueprint, redirect, render_template, request, url_for
from sqlalchemy import select

from contab.context import get_database_name, get_session_factory

from contab.contratos.services import (
    ContratoError,
    crear_anexo_prorroga,
    crear_anexo_renta_permanente,
    crear_anexo_renta_temporal,
    crear_contrato,
    METODOS_REVISION,
)
from contab.models import (
    Contrato,
    ContratoInquilino,
    Inmueble,
    Inquilino,
    RentaContrato,
    RevisionRenta,
)


bp = Blueprint(
    "contratos",
    __name__,
    url_prefix="/contratos",
    template_folder="templates",
)


def _importe_a_centimos(valor: str) -> int:
    """Convierte un importe introducido por el usuario a céntimos."""
    texto = valor.strip().replace(",", ".")

    try:
        importe = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError("El importe indicado no es válido.") from exc

    return int(
        (importe * 100).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def _porcentaje_a_entero(valor: str) -> int:
    """Convierte un porcentaje a centésimas de porcentaje."""
    texto = valor.strip().replace(",", ".")

    try:
        porcentaje = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError("El porcentaje indicado no es válido.") from exc

    return int(
        (porcentaje * 100).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def _fecha(valor: str) -> date:
    """Convierte una fecha dd/mm/aaaa recibida desde un formulario."""
    try:
        return datetime.strptime(
            valor.strip(),
            "%d/%m/%Y",
        ).date()
    except ValueError as exc:
        raise ValueError(
            "La fecha indicada no es válida o no tiene el formato dd/mm/aaaa."
        ) from exc


def _inmuebles_formulario(session):
    """Obtiene los inmuebles activos para el formulario."""
    return session.scalars(
        select(Inmueble)
        .where(Inmueble.activo.is_(True))
        .order_by(Inmueble.referencia)
    ).all()


def _renta_inicial(contrato: Contrato) -> RentaContrato:
    """Devuelve la primera renta registrada para un contrato."""
    if not contrato.rentas:
        raise ContratoError(
            "El contrato no tiene una renta inicial registrada."
        )

    return min(
        contrato.rentas,
        key=lambda renta: renta.fecha_desde,
    )


def _renta_actual(contrato: Contrato) -> RentaContrato:
    """Devuelve la renta contractual más reciente del contrato."""
    if not contrato.rentas:
        raise ContratoError(
            "El contrato no tiene ninguna renta registrada."
        )

    return max(
        contrato.rentas,
        key=lambda renta: renta.fecha_desde,
    )


def _primera_revision(contrato: Contrato) -> RevisionRenta:
    """Devuelve la primera revisión prevista del contrato."""
    if not contrato.revisiones_renta:
        raise ContratoError(
            "El contrato no tiene una revisión inicial registrada."
        )

    return min(
        contrato.revisiones_renta,
        key=lambda revision: revision.fecha_prevista,
    )


def _fecha_a_texto(valor: date) -> str:
    """Convierte una fecha al formato visual dd/mm/aaaa."""
    return valor.strftime("%d/%m/%Y")


def _centimos_a_texto(valor: int) -> str:
    """Convierte céntimos a un importe con dos decimales."""
    return f"{valor / 100:.2f}".replace(".", ",")


def _datos_contrato_formulario(contrato: Contrato) -> dict[str, str]:
    """Prepara los datos actuales de un contrato para su edición."""
    renta = _renta_inicial(contrato)
    revision = _primera_revision(contrato)

    return {
        "inmueble_id": str(contrato.inmueble_id),
        "fecha_inicio": _fecha_a_texto(contrato.fecha_inicio),
        "fecha_vencimiento": _fecha_a_texto(
            contrato.fecha_vencimiento
        ),
        "fecha_inicio_facturacion": _fecha_a_texto(
            contrato.fecha_inicio_facturacion
        ),
        "fianza": _centimos_a_texto(contrato.fianza),
        "iva_porcentaje": _centimos_a_texto(
            contrato.iva_porcentaje
        ),
        "retencion_porcentaje": _centimos_a_texto(
            contrato.retencion_porcentaje
        ),
        "direccion_facturacion": contrato.direccion_facturacion,
        "codigo_postal_facturacion": (
            contrato.codigo_postal_facturacion or ""
        ),
        "poblacion_facturacion": contrato.poblacion_facturacion,
        "provincia_facturacion": contrato.provincia_facturacion,
        "concepto_factura": contrato.concepto_factura,
        "renta_inicial": _centimos_a_texto(renta.importe),
        "fecha_primera_revision": _fecha_a_texto(
            revision.fecha_prevista
        ),
        "metodo_revision": revision.metodo,
        "fecha_fin": (
            _fecha_a_texto(contrato.fecha_fin)
            if contrato.fecha_fin
            else ""
        ),
    }


def _reemplazar_titulares(
    session,
    contrato: Contrato,
    titulares_resueltos: list[tuple[Inquilino, int]],
) -> None:
    """Sustituye los titulares del contrato respetando su orden."""
    anteriores = list(contrato.titulares)

    for titular in anteriores:
        session.delete(titular)

    session.flush()

    for inquilino, orden in titulares_resueltos:
        contrato.titulares.append(
            ContratoInquilino(
                inquilino=inquilino,
                orden=orden,
            )
        )


def _validar_coherencia_historica_edicion(
    contrato: Contrato,
    fecha_inicio: date,
    fecha_vencimiento: date,
    fecha_inicio_facturacion: date,
    fecha_fin: date | None,
    fecha_primera_revision: date,
) -> None:
    """Impide que una edición deje incoherente el histórico del contrato."""
    renta_inicial = _renta_inicial(contrato)
    primera_revision = _primera_revision(contrato)

    for renta in contrato.rentas:
        if renta is renta_inicial:
            continue

        if renta.fecha_desde < fecha_inicio:
            raise ContratoError(
                "La nueva fecha de inicio es posterior a una renta "
                "ya registrada en el histórico."
            )

    for revision in contrato.revisiones_renta:
        if revision is primera_revision:
            continue

        if revision.fecha_prevista < fecha_inicio:
            raise ContratoError(
                "La nueva fecha de inicio es posterior a una revisión "
                "de renta ya registrada."
            )

    for ajuste in contrato.ajustes_renta:
        if ajuste.fecha_desde < fecha_inicio:
            raise ContratoError(
                "La nueva fecha de inicio es posterior a un ajuste "
                "de renta ya registrado."
            )

    for anexo in contrato.anexos:
        if anexo.fecha < fecha_inicio:
            raise ContratoError(
                "La nueva fecha de inicio es posterior a un anexo "
                "ya registrado."
            )

        if (
            anexo.tipo == "PRORROGA"
            and anexo.nueva_fecha_vencimiento is not None
            and anexo.nueva_fecha_vencimiento > fecha_vencimiento
        ):
            raise ContratoError(
                "La fecha de vencimiento no puede ser anterior "
                "al vencimiento establecido por una prórroga."
            )

    for factura in contrato.facturas:
        if factura.periodo < fecha_inicio_facturacion:
            raise ContratoError(
                "El nuevo inicio de facturación es posterior "
                "a una factura ya registrada."
            )

    if fecha_fin is None:
        return

    for renta in contrato.rentas:
        if renta is renta_inicial:
            continue

        if renta.fecha_desde > fecha_fin:
            raise ContratoError(
                "La fecha de resolución es anterior a una renta "
                "ya registrada."
            )

    for ajuste in contrato.ajustes_renta:
        if ajuste.fecha_hasta > fecha_fin:
            raise ContratoError(
                "La fecha de resolución es anterior a un ajuste "
                "de renta ya registrado."
            )

    for anexo in contrato.anexos:
        if anexo.fecha > fecha_fin:
            raise ContratoError(
                "La fecha de resolución es anterior a un anexo "
                "ya registrado."
            )

    for factura in contrato.facturas:
        if factura.periodo > fecha_fin:
            raise ContratoError(
                "La fecha de resolución es anterior a una factura "
                "ya registrada."
            )

def _titulares_formulario(datos) -> list[tuple[str, str, int]]:
    """Obtiene y valida los titulares introducidos en el formulario."""
    titulares = []

    for orden in range(1, 5):
        nombre = datos.get(
            f"titular_{orden}_nombre",
            "",
        ).strip()

        nif = datos.get(
            f"titular_{orden}_nif",
            "",
        ).strip()

        if not nombre and not nif:
            continue

        if not nombre or not nif:
            raise ValueError(
                f"El titular {orden} debe indicar nombre y NIF."
            )

        titulares.append((nombre, nif, orden))

    if not titulares:
        raise ValueError(
            "El contrato debe tener al menos un titular."
        )

    nifs = [nif for _, nif, _ in titulares]

    if len(set(nifs)) != len(nifs):
        raise ValueError(
            "No puede repetirse el mismo NIF entre los titulares."
        )

    return titulares


def _resolver_titulares(
    session,
    titulares_formulario: list[tuple[str, str, int]],
) -> list[tuple[Inquilino, int]]:
    """Busca o crea los inquilinos indicados en el formulario."""
    titulares = []

    for nombre, nif, orden in titulares_formulario:
        inquilino = session.scalar(
            select(Inquilino).where(
                Inquilino.nif == nif
            )
        )

        if inquilino is None:
            inquilino = Inquilino(
                nombre=nombre,
                nif=nif,
            )
            session.add(inquilino)

        elif inquilino.nombre != nombre:
            raise ContratoError(
                f"El NIF {nif} ya pertenece a "
                f"'{inquilino.nombre}', no a '{nombre}'."
            )

        titulares.append(
            (
                inquilino,
                orden,
            )
        )

    return titulares




"""Rutas ------------------------------------------------------------------------------"""

@bp.get("/")
def listar_contratos():
    """Muestra los contratos registrados."""
    session_factory = get_session_factory()

    with session_factory() as session:
        contratos = session.scalars(
            select(Contrato).order_by(
                Contrato.fecha_inicio.desc(),
                Contrato.id.desc(),
            )
        ).all()

        vigentes = [
            contrato
            for contrato in contratos
            if contrato.fecha_fin is None
        ]

        finalizados = [
            contrato
            for contrato in contratos
            if contrato.fecha_fin is not None
        ]

        return render_template(
            "contratos/lista.html",
            vigentes=vigentes,
            finalizados=finalizados,
            database_name=get_database_name(),
        )


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo_contrato():
    """Permite crear un contrato completo."""
    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            inmuebles = _inmuebles_formulario(session)

        return render_template(
            "contratos/formulario.html",
            titulo="Nuevo contrato",
            datos={},
            inmuebles=inmuebles,
            metodos_revision=METODOS_REVISION,
            error=None,
            database_name=get_database_name(),
        )

    try:
        inmueble_id = int(request.form["inmueble_id"])

        titulares_formulario = _titulares_formulario(
            request.form
        )

        fecha_inicio = _fecha(
            request.form["fecha_inicio"]
        )
        fecha_vencimiento = _fecha(
            request.form["fecha_vencimiento"]
        )
        fecha_inicio_facturacion = _fecha(
            request.form["fecha_inicio_facturacion"]
        )

        fianza = _importe_a_centimos(
            request.form["fianza"]
        )
        iva_porcentaje = _porcentaje_a_entero(
            request.form["iva_porcentaje"]
        )
        retencion_porcentaje = _porcentaje_a_entero(
            request.form["retencion_porcentaje"]
        )
        renta_inicial = _importe_a_centimos(
            request.form["renta_inicial"]
        )

        fecha_primera_revision = _fecha(
            request.form["fecha_primera_revision"]
        )

    except (KeyError, ValueError) as exc:
        with session_factory() as session:
            inmuebles = _inmuebles_formulario(session)

            return (
                render_template(
                    "contratos/formulario.html",
                    titulo="Nuevo contrato",
                    datos=request.form,
                    inmuebles=inmuebles,
                    metodos_revision=METODOS_REVISION,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )
        
    try:
        with session_factory() as session:
            with session.begin():
                inmueble = session.get(
                    Inmueble,
                    inmueble_id,
                )

                if inmueble is None:
                    raise ContratoError(
                        "El inmueble seleccionado no existe."
                    )

                titulares_resueltos = _resolver_titulares(
                    session,
                    titulares_formulario,
                )

                titulares = [
                    inquilino
                    for inquilino, _ in titulares_resueltos
                ]

                contrato = crear_contrato(
                    inmueble=inmueble,
                    titulares=titulares,
                    fecha_inicio=fecha_inicio,
                    fecha_vencimiento=fecha_vencimiento,
                    fecha_inicio_facturacion=(
                        fecha_inicio_facturacion
                    ),
                    fianza=fianza,
                    iva_porcentaje=iva_porcentaje,
                    retencion_porcentaje=(
                        retencion_porcentaje
                    ),
                    direccion_facturacion=(
                        request.form[
                            "direccion_facturacion"
                        ].strip()
                    ),
                    codigo_postal_facturacion=(
                        request.form[
                            "codigo_postal_facturacion"
                        ].strip()
                        or None
                    ),
                    poblacion_facturacion=(
                        request.form[
                            "poblacion_facturacion"
                        ].strip()
                    ),
                    provincia_facturacion=(
                        request.form[
                            "provincia_facturacion"
                        ].strip()
                    ),
                    concepto_factura=(
                        request.form[
                            "concepto_factura"
                        ].strip()
                    ),
                    renta_inicial=renta_inicial,
                    fecha_primera_revision=(
                        fecha_primera_revision
                    ),
                    metodo_revision=(
                        request.form[
                            "metodo_revision"
                        ].strip()
                    ),
                )

                session.add(contrato)

    except ContratoError as exc:
        with session_factory() as session:
            inmuebles = _inmuebles_formulario(session)

            return (
                render_template(
                    "contratos/formulario.html",
                    titulo="Nuevo contrato",
                    datos=request.form,
                    inmuebles=inmuebles,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )
        
    return redirect(
        url_for("contratos.listar_contratos")
    )


@bp.route("/<int:contrato_id>/editar", methods=["GET", "POST"])
def editar_contrato(contrato_id: int):
    """Permite corregir los datos de un contrato existente."""
    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            if contrato is None:
                return "Contrato no encontrado.", 404

            inmuebles = _inmuebles_formulario(session)

            datos = _datos_contrato_formulario(contrato)

            for posicion, titular in enumerate(
                sorted(
                    contrato.titulares,
                    key=lambda titular: titular.orden,
                ),
                start=1,
            ):
                datos[f"titular_{posicion}_nombre"] = titular.inquilino.nombre
                datos[f"titular_{posicion}_nif"] = titular.inquilino.nif

            return render_template(
                "contratos/formulario.html",
                titulo="Editar contrato",
                datos=datos,
                inmuebles=inmuebles,
                metodos_revision=METODOS_REVISION,
                error=None,
                database_name=get_database_name(),
            )

    try:
        inmueble_id = int(request.form["inmueble_id"])

        titulares_formulario = _titulares_formulario(
            request.form
        )

        fecha_inicio = _fecha(
            request.form["fecha_inicio"]
        )
        fecha_vencimiento = _fecha(
            request.form["fecha_vencimiento"]
        )
        fecha_inicio_facturacion = _fecha(
            request.form["fecha_inicio_facturacion"]
        )
        fecha_primera_revision = _fecha(
            request.form["fecha_primera_revision"]
        )

        fianza = _importe_a_centimos(
            request.form["fianza"]
        )
        iva_porcentaje = _porcentaje_a_entero(
            request.form["iva_porcentaje"]
        )
        retencion_porcentaje = _porcentaje_a_entero(
            request.form["retencion_porcentaje"]
        )
        renta_inicial = _importe_a_centimos(
            request.form["renta_inicial"]
        )
        fecha_fin_texto = request.form.get("fecha_fin", "").strip()

        fecha_fin = (
            _fecha(fecha_fin_texto)
            if fecha_fin_texto
            else None
        )

        if fecha_vencimiento < fecha_inicio:
            raise ValueError(
                "La fecha de vencimiento no puede ser anterior al inicio."
            )

        if fecha_inicio_facturacion < fecha_inicio:
            raise ValueError(
                "La facturación no puede comenzar antes del contrato."
            )

        if fecha_inicio_facturacion.day != 1:
            raise ValueError(
                "La fecha de inicio de facturación debe ser "
                "el día 1 del mes."
            )

        if fecha_fin is not None and fecha_fin < fecha_inicio:
            raise ValueError(
                "La fecha de finalización no puede ser anterior "
                "al inicio del contrato."
            )
    
        if fianza < 0:
            raise ValueError(
                "La fianza no puede ser negativa."
            )

        if iva_porcentaje < 0:
            raise ValueError(
                "El porcentaje de IVA no puede ser negativo."
            )

        if retencion_porcentaje < 0:
            raise ValueError(
                "El porcentaje de retención no puede ser negativo."
            )

        if renta_inicial < 0:
            raise ValueError(
                "La renta inicial no puede ser negativa."
            )

        if fecha_primera_revision.day != 1:
            raise ValueError(
                "La fecha prevista de revisión debe ser "
                "el día 1 del mes."
            )

        if fecha_primera_revision < fecha_inicio:
            raise ValueError(
                "La revisión no puede ser anterior "
                "al inicio del contrato."
            )

        if not request.form["metodo_revision"].strip():
            raise ValueError(
                "La revisión debe indicar un método de actualización."
            )

    except (KeyError, ValueError) as exc:
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            if contrato is None:
                return "Contrato no encontrado.", 404

            inmuebles = _inmuebles_formulario(session)

            return (
                render_template(
                    "contratos/formulario.html",
                    titulo="Editar contrato",
                    datos=request.form,
                    inmuebles=inmuebles,
                    metodos_revision=METODOS_REVISION,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )

    try:
        with session_factory() as session:
            with session.begin():
                contrato = session.get(
                    Contrato,
                    contrato_id,
                )

                if contrato is None:
                    raise LookupError

                inmueble = session.get(
                    Inmueble,
                    inmueble_id,
                )

                if inmueble is None:
                    raise ContratoError(
                        "El inmueble seleccionado no existe."
                    )

                renta = _renta_inicial(contrato)
                revision = _primera_revision(contrato)

                _validar_coherencia_historica_edicion(
                    contrato=contrato,
                    fecha_inicio=fecha_inicio,
                    fecha_vencimiento=fecha_vencimiento,
                    fecha_inicio_facturacion=fecha_inicio_facturacion,
                    fecha_fin=fecha_fin,
                    fecha_primera_revision=fecha_primera_revision,
                )

                contrato.inmueble = inmueble
                contrato.fecha_inicio = fecha_inicio
                contrato.fecha_vencimiento = fecha_vencimiento
                contrato.fecha_inicio_facturacion = (
                    fecha_inicio_facturacion
                )
                contrato.fecha_fin = fecha_fin
                contrato.fianza = fianza
                contrato.iva_porcentaje = iva_porcentaje
                contrato.retencion_porcentaje = (
                    retencion_porcentaje
                )
                contrato.direccion_facturacion = (
                    request.form[
                        "direccion_facturacion"
                    ].strip()
                )
                contrato.codigo_postal_facturacion = (
                    request.form[
                        "codigo_postal_facturacion"
                    ].strip()
                    or None
                )
                contrato.poblacion_facturacion = (
                    request.form[
                        "poblacion_facturacion"
                    ].strip()
                )
                contrato.provincia_facturacion = (
                    request.form[
                        "provincia_facturacion"
                    ].strip()
                )
                contrato.concepto_factura = (
                    request.form[
                        "concepto_factura"
                    ].strip()
                )

                renta.fecha_desde = fecha_inicio
                renta.importe = renta_inicial

                revision.fecha_prevista = (
                    fecha_primera_revision
                )
                revision.metodo = (
                    request.form[
                        "metodo_revision"
                    ].strip()
                )

                titulares_resueltos = _resolver_titulares(
                    session,
                    titulares_formulario,
                )

                _reemplazar_titulares(
                    session,
                    contrato,
                    titulares_resueltos,
                )

    except LookupError:
        return "Contrato no encontrado.", 404

    except ContratoError as exc:
        with session_factory() as session:
            inmuebles = _inmuebles_formulario(session)

            return (
                render_template(
                    "contratos/formulario.html",
                    titulo="Editar contrato",
                    datos=request.form,
                    inmuebles=inmuebles,
                    metodos_revision=METODOS_REVISION,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )

    return redirect(
        url_for("contratos.listar_contratos")
    )


@bp.route("/<int:contrato_id>/finalizar", methods=["GET", "POST"])
def finalizar_contrato(contrato_id: int):
    """Permite finalizar un contrato indicando su fecha de fin."""
    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            if contrato is None:
                return "Contrato no encontrado.", 404

            return render_template(
                "contratos/finalizar.html",
                contrato=contrato,
                error=None,
                database_name=get_database_name(),
            )

    try:
        fecha_fin = _fecha(request.form["fecha_fin"])
    except (KeyError, ValueError) as exc:
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            if contrato is None:
                return "Contrato no encontrado.", 404

            return (
                render_template(
                    "contratos/finalizar.html",
                    contrato=contrato,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )

    try:
        with session_factory() as session:
            with session.begin():
                contrato = session.get(Contrato, contrato_id)

                if contrato is None:
                    raise LookupError

                if fecha_fin < contrato.fecha_inicio:
                    raise ContratoError(
                        "La fecha de finalización no puede ser anterior "
                        "al inicio del contrato."
                    )

                contrato.fecha_fin = fecha_fin

    except LookupError:
        return "Contrato no encontrado.", 404

    except ContratoError as exc:
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            return (
                render_template(
                    "contratos/finalizar.html",
                    contrato=contrato,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )

    return redirect(
        url_for("contratos.listar_contratos")
    )


@bp.get("/<int:contrato_id>/anexo")
def seleccionar_tipo_anexo(contrato_id: int):
    """Permite elegir el tipo de anexo que se desea añadir."""
    session_factory = get_session_factory()

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        if contrato is None:
            return "Contrato no encontrado.", 404

        return render_template(
            "contratos/anexo_seleccion.html",
            contrato=contrato,
            database_name=get_database_name(),
        )


@bp.route(
    "/<int:contrato_id>/anexo/prorroga",
    methods=["GET", "POST"],
)
def formulario_anexo_prorroga(contrato_id: int):
    """Permite crear un anexo de prórroga."""
    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            if contrato is None:
                return "Contrato no encontrado.", 404

            return render_template(
                "contratos/anexo_prorroga.html",
                contrato=contrato,
                datos={},
                error=None,
                database_name=get_database_name(),
            )

    try:
        fecha = _fecha(request.form["fecha"])
        nueva_fecha_vencimiento = _fecha(
            request.form["nueva_fecha_vencimiento"]
        )
    except (KeyError, ValueError) as exc:
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            if contrato is None:
                return "Contrato no encontrado.", 404

            return (
                render_template(
                    "contratos/anexo_prorroga.html",
                    contrato=contrato,
                    datos=request.form,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )

    try:
        with session_factory() as session:
            with session.begin():
                contrato = session.get(Contrato, contrato_id)

                if contrato is None:
                    raise LookupError

                anexo = crear_anexo_prorroga(
                    contrato=contrato,
                    fecha=fecha,
                    nueva_fecha_vencimiento=nueva_fecha_vencimiento,
                    descripcion=(
                        request.form.get("descripcion", "").strip()
                        or None
                    ),
                )

                session.add(anexo)

    except LookupError:
        return "Contrato no encontrado.", 404

    except ContratoError as exc:
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            return (
                render_template(
                    "contratos/anexo_prorroga.html",
                    contrato=contrato,
                    datos=request.form,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )

    return redirect(
        url_for("contratos.listar_contratos")
    )


@bp.route(
    "/<int:contrato_id>/anexo/renta-permanente",
    methods=["GET", "POST"],
)
def formulario_anexo_renta_permanente(contrato_id: int):
    """Permite crear un anexo de cambio permanente de renta."""
    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            if contrato is None:
                return "Contrato no encontrado.", 404
                
            renta_actual = _renta_actual(contrato)

            return render_template(
                "contratos/anexo_renta_permanente.html",
                contrato=contrato,
                renta_actual=renta_actual,
                datos={},
                error=None,
                database_name=get_database_name(),
            )

    try:
        fecha = _fecha(request.form["fecha"])
        fecha_desde = _fecha(request.form["fecha_desde"])
        importe = _importe_a_centimos(
            request.form["importe"]
        )

    except (KeyError, ValueError) as exc:
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            if contrato is None:
                return "Contrato no encontrado.", 404

            renta_actual = _renta_actual(contrato)

            return (
                render_template(
                    "contratos/anexo_renta_permanente.html",
                    contrato=contrato,
                    renta_actual=renta_actual,
                    datos=request.form,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )

    try:
        with session_factory() as session:
            with session.begin():
                contrato = session.get(Contrato, contrato_id)

                if contrato is None:
                    raise LookupError

                anexo, renta = crear_anexo_renta_permanente(
                    contrato=contrato,
                    fecha=fecha,
                    fecha_desde=fecha_desde,
                    importe=importe,
                    descripcion=(
                        request.form.get("descripcion", "").strip()
                        or None
                    ),
                )

                session.add(anexo)

    except LookupError:
        return "Contrato no encontrado.", 404

    except ContratoError as exc:
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            renta_actual = _renta_actual(contrato)

            return (
                render_template(
                    "contratos/anexo_renta_permanente.html",
                    contrato=contrato,
                    renta_actual=renta_actual,
                    datos=request.form,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )

    return redirect(
        url_for("contratos.listar_contratos")
    )


@bp.route(
    "/<int:contrato_id>/anexo/renta-temporal",
    methods=["GET", "POST"],
)
def formulario_anexo_renta_temporal(contrato_id: int):
    """Permite crear un anexo de cambio temporal de renta."""
    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            if contrato is None:
                return "Contrato no encontrado.", 404
                
            renta_actual = _renta_actual(contrato)

            return render_template(
                "contratos/anexo_renta_temporal.html",
                contrato=contrato,
                renta_actual=renta_actual,
                datos={},
                error=None,
                database_name=get_database_name(),
            )

    try:
        fecha = _fecha(request.form["fecha"])
        fecha_desde = _fecha(request.form["fecha_desde"])
        fecha_hasta = _fecha(request.form["fecha_hasta"])

        tipo = request.form["tipo"]

        if tipo == "REDUCCION_PORCENTUAL":
            valor = _porcentaje_a_entero(
                request.form["valor"]
            )
        else:
            valor = _importe_a_centimos(
                request.form["valor"]
            )

    except (KeyError, ValueError) as exc:
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)

            if contrato is None:
                return "Contrato no encontrado.", 404
            
            renta_actual = _renta_actual(contrato)

            return (
                render_template(
                    "contratos/anexo_renta_temporal.html",
                    contrato=contrato,
                    datos=request.form,
                    renta_actual=renta_actual,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )

    try:
        with session_factory() as session:
            with session.begin():
                contrato = session.get(Contrato, contrato_id)

                if contrato is None:
                    raise LookupError

                anexo, ajuste = crear_anexo_renta_temporal(
                    contrato=contrato,
                    fecha=fecha,
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta,
                    tipo=tipo,
                    valor=valor,
                    descripcion=(
                        request.form.get("descripcion", "").strip()
                        or None
                    ),
                )

                session.add(anexo)

    except LookupError:
        return "Contrato no encontrado.", 404

    except ContratoError as exc:
        with session_factory() as session:
            contrato = session.get(Contrato, contrato_id)
            renta_actual = _renta_actual(contrato)

            return (
                render_template(
                    "contratos/anexo_renta_temporal.html",
                    contrato=contrato,
                    datos=request.form,
                    renta_actual=renta_actual,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )

    return redirect(
        url_for("contratos.listar_contratos")
    )


@bp.get("/<int:contrato_id>/anexos")
def historico_anexos(contrato_id: int):
    """Muestra el histórico de anexos de un contrato."""
    session_factory = get_session_factory()

    with session_factory() as session:
        contrato = session.get(Contrato, contrato_id)

        if contrato is None:
            return "Contrato no encontrado.", 404

        anexos = sorted(
            contrato.anexos,
            key=lambda anexo: (
                anexo.fecha,
                anexo.id or 0,
            ),
        )

        return render_template(
            "contratos/anexos.html",
            contrato=contrato,
            anexos=anexos,
            database_name=get_database_name(),
        )



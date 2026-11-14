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
from datetime import date

from contab.context import (
    get_database_name,
    get_session_factory,
)
from contab.formato import (
    fecha_a_texto,
    texto_a_fecha,
    importe_a_texto_entrada,
    porcentaje_a_texto_entrada,
)
from contab.models import Inmueble


"""Variables globales de este archivo -------------------------------------------------"""

bp = Blueprint(
    "inmuebles",
    __name__,
    url_prefix="/inmuebles",
    template_folder="templates",
)

TIPOS_INMUEBLE = {
    "T": "Inmueble subdividido",
    "P": "Piso",
    "L": "Local",
    "G": "Garaje",
}


""" Helpers ---------------------------------------------------------------------------"""

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
        ("tipo", "El tipo de inmueble es obligatorio."),
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

    tipo = datos["tipo"].strip()

    if tipo not in TIPOS_INMUEBLE:
        return {}, "El tipo de inmueble indicado no es válido."

    es_parte_inmueble = (
        "es_parte_inmueble" in datos
    )

    if tipo == "T":
        if es_parte_inmueble:
            return (
                {},
                "Un inmueble subdividido no puede formar "
                "parte de otro inmueble.",
            )

        if participacion != 10000:
            return (
                {},
                "Un inmueble subdividido debe tener una "
                "participación del 100 %.",
            )

    inmueble_padre_id = None

    if es_parte_inmueble:
        inmueble_padre_texto = datos.get(
            "inmueble_padre_id",
            "",
        ).strip()

        if not inmueble_padre_texto:
            return (
                {},
                "Debe seleccionar el inmueble subdividido "
                "al que pertenece.",
            )

        try:
            inmueble_padre_id = int(
                inmueble_padre_texto
            )
        except ValueError:
            return (
                {},
                "El inmueble subdividido seleccionado "
                "no es válido.",
            )

    valores = {
        "inmueble_padre_id": inmueble_padre_id,
        "referencia": datos["referencia"].strip(),
        "tipo": tipo,
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


def _datos_propiedad_iniciales(
    inmueble_padre_id: int | None,
) -> dict:
    """Prepara los datos de propiedad para un inmueble nuevo."""

    campos = (
        "porcentaje_titular",
        "tipo_derecho",
        "porcentaje_derecho",
        "fecha_adquisicion",
        "tipo_adquisicion",
        "importe_adquisicion",
        "gastos_adquisicion",
        "fecha_transmision",
    )

    if inmueble_padre_id is not None:
        return dict.fromkeys(campos)

    return {
        "porcentaje_titular": 10000,
        "tipo_derecho": "PLENA_PROPIEDAD",
        "porcentaje_derecho": 10000,
        "fecha_adquisicion": date.today(),
        "tipo_adquisicion": "ONEROSA",
        "importe_adquisicion": 0,
        "gastos_adquisicion": 0,
        "fecha_transmision": None,
    }


def _datos_propiedad_formulario(
    datos,
    inmueble_padre_id: int | None,
) -> dict:
    """Valida los campos de propiedad enviados por el formulario."""

    campos = (
        "porcentaje_titular",
        "tipo_derecho",
        "porcentaje_derecho",
        "fecha_adquisicion",
        "tipo_adquisicion",
        "importe_adquisicion",
        "gastos_adquisicion",
        "fecha_transmision",
    )

    if inmueble_padre_id is not None:
        return dict.fromkeys(campos)

    def porcentaje(campo):
        texto = datos.get(campo, "").strip().replace(",", ".")
        try:
            valor = Decimal(texto) * 100
        except InvalidOperation as exc:
            raise ValueError(
                f"El campo {campo} debe ser un porcentaje válido."
            ) from exc

        if (
            not valor.is_finite()
            or valor != valor.to_integral_value()
            or not 0 <= valor <= 10000
        ):
            raise ValueError(
                f"El campo {campo} debe estar entre 0 y 100 "
                "con un máximo de dos decimales."
            )

        return int(valor)

    def importe(campo):
        texto = datos.get(campo, "").strip().replace(",", ".")
        try:
            valor = Decimal(texto) * 100
        except InvalidOperation as exc:
            raise ValueError(
                f"El campo {campo} debe ser un importe válido."
            ) from exc

        if (
            not valor.is_finite()
            or valor < 0
            or valor != valor.to_integral_value()
        ):
            raise ValueError(
                f"El campo {campo} debe ser un importe "
                "no negativo con un máximo de dos decimales."
            )

        return int(valor)

    tipo_derecho = datos.get("tipo_derecho", "").strip()
    if tipo_derecho not in ("PLENA_PROPIEDAD", "USUFRUCTO"):
        raise ValueError("El tipo de derecho no es válido.")

    tipo_adquisicion = datos.get("tipo_adquisicion", "").strip()
    if tipo_adquisicion not in ("ONEROSA", "LUCRATIVA"):
        raise ValueError("El tipo de adquisición no es válido.")

    fecha_adquisicion = texto_a_fecha(
        datos.get("fecha_adquisicion", "")
    )

    texto_transmision = datos.get(
        "fecha_transmision", ""
    ).strip()

    fecha_transmision = (
        texto_a_fecha(texto_transmision)
        if texto_transmision
        else None
    )

    if (
        fecha_transmision is not None
        and fecha_transmision < fecha_adquisicion
    ):
        raise ValueError(
            "La fecha de transmisión no puede ser anterior "
            "a la fecha de adquisición."
        )

    return {
        "porcentaje_titular": porcentaje("porcentaje_titular"),
        "tipo_derecho": tipo_derecho,
        "porcentaje_derecho": porcentaje("porcentaje_derecho"),
        "fecha_adquisicion": fecha_adquisicion,
        "tipo_adquisicion": tipo_adquisicion,
        "importe_adquisicion": importe("importe_adquisicion"),
        "gastos_adquisicion": importe("gastos_adquisicion"),
        "fecha_transmision": fecha_transmision,
    }


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


def _validar_inmueble_padre(
    session,
    *,
    tipo: str,
    inmueble_padre_id: int | None,
    inmueble_id: int | None = None,
) -> str | None:
    """Valida la relación con un inmueble subdividido."""

    if inmueble_padre_id is None:
        return None

    if tipo == "T":
        return (
            "Un inmueble subdividido no puede formar "
            "parte de otro inmueble."
        )

    if inmueble_padre_id == inmueble_id:
        return (
            "Un inmueble no puede formar parte "
            "de sí mismo."
        )

    inmueble_padre = session.get(
        Inmueble,
        inmueble_padre_id,
    )

    if inmueble_padre is None:
        return (
            "El inmueble subdividido seleccionado "
            "no existe."
        )

    if inmueble_padre.tipo != "T":
        return (
            "El inmueble seleccionado como padre "
            "no es un inmueble subdividido."
        )

    return None


def _inmuebles_subdivididos_formulario(session):
    """Obtiene los inmuebles totales disponibles."""

    return session.scalars(
        select(Inmueble)
        .where(Inmueble.tipo == "T")
        .order_by(Inmueble.referencia)
    ).all()


def _render_formulario_inmueble(
    session,
    *,
    datos,
    titulo: str,
    error: str | None,
):
    """Renderiza el formulario con sus opciones."""

    return render_template(
        "inmuebles/nuevo.html",
        datos=datos,
        tipos_inmueble=TIPOS_INMUEBLE,
        inmuebles_subdivididos=(
            _inmuebles_subdivididos_formulario(session)
        ),
        error=error,
        titulo=titulo,
        database_name=get_database_name(),
    )



""" Funciones para atender a las rutas del servidor web -------------------------------"""

@bp.get("/")
def listar_inmuebles():
    """Muestra los inmuebles registrados."""

    session_factory = get_session_factory()

    with session_factory() as session:
        inmuebles = session.scalars(
            select(Inmueble).order_by(
                Inmueble.referencia
            )
        ).all()

        locales_por_padre: dict[
            int,
            list[Inmueble],
        ] = {}

        for inmueble in inmuebles:
            if inmueble.inmueble_padre_id is not None:
                locales_por_padre.setdefault(
                    inmueble.inmueble_padre_id,
                    [],
                ).append(inmueble)

        inmuebles_subdivididos = [
            inmueble
            for inmueble in inmuebles
            if inmueble.tipo == "T"
        ]

        grupos = [
            (
                inmueble_subdividido,
                locales_por_padre.get(
                    inmueble_subdividido.id,
                    [],
                ),
            )
            for inmueble_subdividido in inmuebles_subdivididos
        ]

        independientes = [
            inmueble
            for inmueble in inmuebles
            if (
                inmueble.tipo != "T"
                and inmueble.inmueble_padre_id is None
            )
        ]

        return render_template(
            "inmuebles/lista.html",
            grupos=grupos,
            independientes=independientes,
            tipos_inmueble=TIPOS_INMUEBLE,
            database_name=get_database_name(),
        )


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo_inmueble():
    """Permite introducir y guardar un nuevo inmueble."""

    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            return _render_formulario_inmueble(
                session,
                datos={},
                titulo="Nuevo inmueble",
                error=None,
            )

    valores, error = _validar_datos_inmueble(
        request.form
    )

    if error:
        with session_factory() as session:
            return (
                _render_formulario_inmueble(
                    session,
                    datos=request.form,
                    titulo="Nuevo inmueble",
                    error=error,
                ),
                400,
            )

    with session_factory() as session:
        with session.begin():
            error_padre = _validar_inmueble_padre(
                session,
                tipo=valores["tipo"],
                inmueble_padre_id=valores[
                    "inmueble_padre_id"
                ],
            )

            if error_padre:
                return (
                    _render_formulario_inmueble(
                        session,
                        datos=request.form,
                        titulo="Nuevo inmueble",
                        error=error_padre,
                    ),
                    400,
                )

            error_duplicado = _buscar_duplicado(
                session,
                valores["referencia"],
                valores["codigo_facturacion"],
            )

            if error_duplicado:
                return (
                    _render_formulario_inmueble(
                        session,
                        datos=request.form,
                        titulo="Nuevo inmueble",
                        error=error_duplicado,
                    ),
                    400,
                )

            try:
                valores.update(
                    _datos_propiedad_formulario(
                        request.form,
                        valores["inmueble_padre_id"],
                    )
                )
            except ValueError as exc:
                return (
                    _render_formulario_inmueble(
                        session,
                        datos=request.form,
                        titulo="Nuevo inmueble",
                        error=str(exc),
                    ),
                    400,
                )

            inmueble = Inmueble(**valores)
            session.add(inmueble)

    return redirect(
        url_for("inmuebles.listar_inmuebles")
    )


@bp.route("/<int:inmueble_id>/editar", methods=["GET", "POST"])
def editar_inmueble(inmueble_id: int):
    """Permite modificar los datos de un inmueble existente."""
    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            inmueble = session.get(Inmueble, inmueble_id)

            if inmueble is None:
                return "Inmueble no encontrado.", 404

            datos = {
                "referencia": inmueble.referencia,
                "tipo": inmueble.tipo,
                "codigo_facturacion": inmueble.codigo_facturacion,
                "descripcion": inmueble.descripcion,
                "direccion": inmueble.direccion,
                "codigo_postal": inmueble.codigo_postal or "",
                "poblacion": inmueble.poblacion,
                "provincia": inmueble.provincia,
                "ref_catastral": inmueble.ref_catastral or "",
                "seguro": inmueble.seguro or "",
                "participacion": (
                    f"{inmueble.participacion / 100:.2f}"
                    .replace(".", ",")
                ),
                "porcentaje_titular": (
                    porcentaje_a_texto_entrada(inmueble.porcentaje_titular)
                    if inmueble.porcentaje_titular is not None else ""
                ),
                "tipo_derecho": inmueble.tipo_derecho or "",
                "porcentaje_derecho": (
                    porcentaje_a_texto_entrada(inmueble.porcentaje_derecho)
                    if inmueble.porcentaje_derecho is not None else ""
                ),
                "fecha_adquisicion": (
                    fecha_a_texto(inmueble.fecha_adquisicion)
                    if inmueble.fecha_adquisicion else ""
                ),
                "tipo_adquisicion": inmueble.tipo_adquisicion or "",
                "importe_adquisicion": (
                    importe_a_texto_entrada(inmueble.importe_adquisicion)
                    if inmueble.importe_adquisicion is not None else ""
                ),
                "gastos_adquisicion": (
                    importe_a_texto_entrada(inmueble.gastos_adquisicion)
                    if inmueble.gastos_adquisicion is not None else ""
                ),
                "fecha_transmision": (
                    fecha_a_texto(inmueble.fecha_transmision)
                    if inmueble.fecha_transmision else ""
                ),

                "notas": inmueble.notas or "",
                "es_parte_inmueble": (
                    inmueble.inmueble_padre_id is not None
                ),
                "inmueble_padre_id": (
                    str(inmueble.inmueble_padre_id)
                    if inmueble.inmueble_padre_id is not None
                    else ""
                ),
            }

            return _render_formulario_inmueble(
                session,
                datos=datos,
                error=None,
                titulo="Editar inmueble",
            )

    valores, error = _validar_datos_inmueble(request.form)

    if error:
        with session_factory() as session:
            return (
                _render_formulario_inmueble(
                    session,
                    datos=request.form,
                    error=error,
                    titulo="Editar inmueble",
                ),
                400,
            )

    with session_factory() as session:
        with session.begin():
            inmueble = session.get(
                Inmueble,
                inmueble_id,
            )

            if inmueble is None:
                return "Inmueble no encontrado.", 404

            error_padre = _validar_inmueble_padre(
                session,
                tipo=valores["tipo"],
                inmueble_padre_id=valores[
                    "inmueble_padre_id"
                ],
                inmueble_id=inmueble.id,
            )

            if error_padre:
                return (
                    _render_formulario_inmueble(
                        session,
                        datos=request.form,
                        error=error_padre,
                        titulo="Editar inmueble",
                    ),
                    400,
                )

            error_duplicado = _buscar_duplicado(
                session,
                valores["referencia"],
                valores["codigo_facturacion"],
                excluir_id=inmueble.id,
            )

            if error_duplicado:
                return (
                    _render_formulario_inmueble(
                       session,
                        datos=request.form,
                        error=error_duplicado,
                        titulo="Editar inmueble",
                    ),
                    400,
                )

            if (inmueble.inmueble_padre_id
                != valores["inmueble_padre_id"]
            ):
                return (
                    _render_formulario_inmueble(
                        session,
                        datos=request.form,
                        error=(
                            "Por ahora no se puede cambiar "
                            "la pertenencia de un inmueble "
                            "a una propiedad subdividida."
                        ),
                        titulo="Editar inmueble",
                    ),
                    400,
                )

            # impedir cambios de tipo en inmuebles subdivididos con hijos
            if inmueble.tipo == "T" and valores["tipo"] != "T":
                tiene_hijos = session.scalar(
                    select(Inmueble.id)
                    .where(Inmueble.inmueble_padre_id == inmueble.id)
                    .limit(1)
                ) is not None

                if tiene_hijos:
                    return (
                        _render_formulario_inmueble(
                            session,
                            datos=request.form,
                            error=(
                                "No se puede cambiar el tipo de un "
                                "inmueble subdividido que tiene hijos."
                            ),
                            titulo="Editar inmueble",
                        ),
                        400,
                    )

            try:
                valores.update(
                    _datos_propiedad_formulario(
                        request.form,
                        valores["inmueble_padre_id"],
                    )
                )
            except ValueError as exc:
                return (
                    _render_formulario_inmueble(
                        session,
                        datos=request.form,
                        titulo="Editar inmueble",
                        error=str(exc),
                    ),
                    400,
                )

            for campo, valor in valores.items():
                setattr(inmueble, campo, valor)

    return redirect(
        url_for("inmuebles.listar_inmuebles")
    )


@bp.route("/<int:inmueble_id>/estado", methods=["GET", "POST"])
def cambiar_estado_inmueble(inmueble_id: int):
    """Permite activar o desactivar un inmueble previa confirmación."""
    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            inmueble = session.get(Inmueble, inmueble_id)

            if inmueble is None:
                return "Inmueble no encontrado.", 404

            accion = "Desactivar" if inmueble.activo else "Activar"

            return render_template(
                "inmuebles/estado.html",
                inmueble=inmueble,
                accion=accion,
                database_name=get_database_name(),
            )

    with session_factory() as session:
        with session.begin():
            inmueble = session.get(Inmueble, inmueble_id)

            if inmueble is None:
                return "Inmueble no encontrado.", 404

            inmueble.activo = not inmueble.activo

    return redirect(url_for("inmuebles.listar_inmuebles"))


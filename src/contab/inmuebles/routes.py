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
from contab.models import Inmueble
from contab.context import get_database_name, get_session_factory


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
            
            inmuebles_subdivididos = (
                _inmuebles_subdivididos_formulario(session)
            )

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


def test_crear_local_rechaza_padre_que_no_es_total() -> None:
    app = crear_app_test()
    client = app.test_client()

    client.post("/", data={"database": "test"})

    session_factory = app.extensions[
        "contab_databases"
    ]["test"]

    with session_factory() as session:
        padre_incorrecto = Inmueble(
            referencia="LOCAL-1",
            tipo="L",
            codigo_facturacion="A1",
            descripcion="Local independiente",
            direccion="Dirección",
            poblacion="Pontevedra",
            provincia="Pontevedra",
        )
        session.add(padre_incorrecto)
        session.commit()
        padre_id = padre_incorrecto.id

    response = client.post(
        "/inmuebles/nuevo",
        data={
            "tipo": "L",
            "referencia": "LOCAL-2",
            "codigo_facturacion": "A2",
            "descripcion": "Local subordinado",
            "direccion": "Dirección",
            "codigo_postal": "",
            "poblacion": "Pontevedra",
            "provincia": "Pontevedra",
            "ref_catastral": "",
            "seguro": "",
            "participacion": "50,00",
            "es_parte_inmueble": "on",
            "inmueble_padre_id": str(padre_id),
            "notas": "",
        },
    )

    assert response.status_code == 400
    assert (
        "no es un inmueble subdividido"
        in response.text
    )

    with session_factory() as session:
        local = session.scalar(
            select(Inmueble).where(
                Inmueble.referencia == "LOCAL-2"
            )
        )

        assert local is None


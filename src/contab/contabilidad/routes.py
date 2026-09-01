"""Define las rutas web para consultar y mantener apuntes contables."""

import hashlib
import hmac
import json

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from calendar import monthrange

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from contab.context import (
    get_database_name,
    get_session_factory,
)
from contab.models import ApunteContable, Inmueble

from contab.config import (
    cargar_categorias_contables,
    categorias_contables_activas,
)
from contab.contabilidad.services import (
    ContabilidadError,
    buscar_documentos_duplicados,
    crear_apunte_contable,
    eliminar_apunte_contable,
    modificar_apunte_contable,
    proponer_nombre_documento,
)


CAMPOS_VALIDACION = (
    "inmueble_id",
    "fecha",
    "clasificacion",
    "concepto",
    "periodo_desde",
    "periodo_hasta",
    "tratamiento",
    "base",
    "iva_importe",
    "retencion_importe",
    "nombre_documento",
    "tercero_nombre",
    "tercero_nif",
    "referencia_documento",
)

TRATAMIENTOS_APUNTE = {
    "CONTABILIZAR": "Contabilizar",
    "REPERCUTIR": "Trasladar gasto",
    "FACTURAR": "Facturar",
}

NATURALEZAS_APUNTE = {
    "INGRESO": "Ingreso",
    "GASTO": "Gasto",
}

bp = Blueprint(
    "contabilidad",
    __name__,
    url_prefix="/contabilidad",
    template_folder="templates",
)



def _clasificacion_a_texto(
    apunte: ApunteContable,
    categorias,
) -> str:
    """Obtiene el literal humano de la clasificación."""

    try:
        return _proponer_concepto(
            categorias,
            apunte.categoria,
            apunte.subcategoria or "",
        )
    except (KeyError, ValueError):
        if apunte.subcategoria:
            return (
                f"{apunte.categoria}."
                f"{apunte.subcategoria}"
            )

        return apunte.categoria


def _firma_formulario(datos) -> str:
    """Firma los datos que deben permanecer tras la validación."""

    contenido = {
        campo: datos.get(campo, "")
        for campo in CAMPOS_VALIDACION
    }

    texto = json.dumps(
        contenido,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    clave = current_app.secret_key

    if not clave:
        raise RuntimeError(
            "La aplicación no tiene configurada una clave secreta."
        )

    return hmac.new(
        clave.encode("utf-8"),
        texto.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _formulario_sigue_validado(datos) -> bool:
    """Comprueba que no se modificaron los datos validados."""

    firma_recibida = datos.get(
        "firma_validacion",
        "",
    )

    if not firma_recibida:
        return False

    firma_actual = _firma_formulario(datos)

    return hmac.compare_digest(
        firma_recibida,
        firma_actual,
    )


def _validar_nombre_documento(nombre: str) -> str:
    """Valida y normaliza el nombre del documento."""

    nombre = nombre.strip()

    if not nombre:
        raise ValueError(
            "El nombre del documento es obligatorio."
        )

    if "/" in nombre or "\\" in nombre:
        raise ValueError(
            "El nombre del documento no puede contener "
            "barras inclinadas."
        )

    return nombre


def _importe_a_texto(importe: int) -> str:
    """Convierte un importe en céntimos a texto."""

    euros, centimos = divmod(importe, 100)

    return f"{euros},{centimos:02d} €"


def _fecha(texto: str) -> date:
    """Convierte una fecha dd/mm/aaaa."""

    try:
        return datetime.strptime(
            texto.strip(),
            "%d/%m/%Y",
        ).date()
    except ValueError as exc:
        raise ValueError(
            "La fecha indicada no es válida o no tiene "
            "el formato dd/mm/aaaa."
        ) from exc


def _periodo(
    desde_texto: str,
    hasta_texto: str,
) -> tuple[date | None, date | None]:
    """Interpreta un período vacío, mensual o entre dos fechas."""

    desde_texto = desde_texto.strip()
    hasta_texto = hasta_texto.strip()

    if not desde_texto and not hasta_texto:
        return None, None

    if not desde_texto:
        raise ValueError(
            "El período no puede tener fecha final sin fecha inicial."
        )

    if not hasta_texto:
        try:
            mes = datetime.strptime(
                desde_texto,
                "%m/%Y",
            ).date()
        except ValueError as exc:
            raise ValueError(
                "Un período mensual debe tener el formato mm/aaaa. "
                "Para un intervalo deben indicarse ambas fechas."
            ) from exc

        ultimo_dia = monthrange(
            mes.year,
            mes.month,
        )[1]

        return (
            date(mes.year, mes.month, 1),
            date(mes.year, mes.month, ultimo_dia),
        )

    return (
        _fecha(desde_texto),
        _fecha(hasta_texto),
    )


def _periodo_para_formulario(
    periodo_desde: date | None,
    periodo_hasta: date | None,
) -> tuple[str, str]:
    """Convierte un período al formato del formulario."""

    if periodo_desde is None or periodo_hasta is None:
        return "", ""

    ultimo_dia = monthrange(
        periodo_desde.year,
        periodo_desde.month,
    )[1]

    if (
        periodo_desde.day == 1
        and periodo_hasta
        == date(
            periodo_desde.year,
            periodo_desde.month,
            ultimo_dia,
        )
    ):
        return (
            periodo_desde.strftime("%m/%Y"),
            "",
        )

    return (
        periodo_desde.strftime("%d/%m/%Y"),
        periodo_hasta.strftime("%d/%m/%Y"),
    )


def _periodo_a_texto(apunte: ApunteContable) -> str:
    """Muestra el período de un apunte de forma compacta."""

    desde, hasta = _periodo_para_formulario(
        apunte.periodo_desde,
        apunte.periodo_hasta,
    )

    if not desde:
        return ""

    if not hasta:
        return desde

    return f"{desde} a {hasta}"


def _proponer_concepto(
    categorias,
    categoria_codigo: str,
    subcategoria_codigo: str,
) -> str:
    """Obtiene el literal humano de una clasificación."""

    categoria = categorias[categoria_codigo]

    if not subcategoria_codigo:
        return categoria.nombre

    for subcategoria in categoria.subcategorias:
        if subcategoria.codigo == subcategoria_codigo:
            return subcategoria.nombre

    raise ValueError(
        "La subcategoría contable indicada no es válida."
    )


def _completar_concepto_automatico(
    concepto: str,
    periodo_desde: date | None,
    periodo_hasta: date | None,
) -> str:
    """Añade el período al concepto automático."""

    if periodo_desde is None or periodo_hasta is None:
        return concepto

    ultimo_dia = monthrange(
        periodo_desde.year,
        periodo_desde.month,
    )[1]

    es_mes_completo = (
        periodo_desde.day == 1
        and periodo_hasta
        == date(
            periodo_desde.year,
            periodo_desde.month,
            ultimo_dia,
        )
    )

    if es_mes_completo:
        return (
            f"{concepto} "
            f"{periodo_desde:%m/%Y}"
        )

    return (
        f"{concepto}. "
        f"{periodo_desde:%d/%m/%Y}"
        f" a {periodo_hasta:%d/%m/%Y}"
    )


def _preparar_campos_automaticos(
    *,
    inmueble: Inmueble,
    categorias,
    valores: dict,
    datos_formulario: dict,
) -> None:
    """Propone concepto y nombre sin sobrescribir cambios manuales."""

    concepto = valores["concepto"].strip()
    concepto_anterior = datos_formulario.get(
        "concepto_automatico",
        "",
    ).strip()

    concepto_base = _proponer_concepto(
        categorias,
        valores["categoria"],
        valores["subcategoria"],
    )

    concepto_es_automatico = (
        not concepto
        or concepto == concepto_anterior
    )

    if concepto_es_automatico:
        concepto = _completar_concepto_automatico(
            concepto_base,
            valores["periodo_desde"],
            valores["periodo_hasta"],
        )
        datos_formulario[
            "concepto_automatico"
        ] = concepto
    else:
        datos_formulario[
            "concepto_automatico"
        ] = ""

    valores["concepto"] = concepto
    datos_formulario["concepto"] = concepto

    nombre = valores["nombre_documento"].strip()
    nombre_anterior = datos_formulario.get(
        "nombre_documento_automatico",
        "",
    ).strip()

    if not nombre or nombre == nombre_anterior:
        nombre = proponer_nombre_documento(
            inmueble=inmueble,
            concepto=(
                concepto_base
                if concepto_es_automatico
                else concepto
            ),
            periodo_desde=valores["periodo_desde"],
            periodo_hasta=valores["periodo_hasta"],
        )
        datos_formulario[
            "nombre_documento_automatico"
        ] = nombre
    else:
        datos_formulario[
            "nombre_documento_automatico"
        ] = ""

    nombre = _validar_nombre_documento(nombre)

    valores["nombre_documento"] = nombre
    datos_formulario["nombre_documento"] = nombre


def _importe_a_centimos(texto: str) -> int:
    """Convierte un importe escrito en euros a céntimos."""

    texto = texto.strip().replace(",", ".")

    try:
        importe = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(
            "El importe indicado no es válido."
        ) from exc

    return int(
        (importe * 100).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def _separar_clasificacion(
    texto: str,
    categorias,
) -> tuple[str, str, str]:
    """Obtiene naturaleza, categoría y subcategoría."""

    partes = texto.strip().upper().split(".", maxsplit=1)
    categoria_codigo = partes[0]

    categoria = categorias.get(categoria_codigo)

    if categoria is None:
        raise ValueError(
            "La clasificación contable indicada no es válida."
        )

    subcategoria = (
        partes[1]
        if len(partes) == 2
        else ""
    )

    return (
        categoria.naturaleza,
        categoria_codigo,
        subcategoria,
    )


def _mostrar_formulario_apunte(
    *,
    titulo: str,
    datos,
    error: str | None,
    status_code: int = 200,
    permitir_movimiento: bool = False,
    aviso: str | None = None,
):
    """Muestra el formulario con sus opciones."""

    categorias = categorias_contables_activas(
        cargar_categorias_contables()
    )

    session_factory = get_session_factory()

    with session_factory() as session:
        inmuebles = session.scalars(
            select(Inmueble)
            .where(Inmueble.activo.is_(True))
            .order_by(Inmueble.referencia)
        ).all()

        contenido = render_template(
            "contabilidad/formulario.html",
            titulo=titulo,
            datos=datos,
            categorias=categorias,
            inmuebles=inmuebles,
            error=error,
            database_name=get_database_name(),
            permitir_movimiento=permitir_movimiento,
            aviso=aviso,
        )

    return contenido, status_code


def _importe_para_formulario(importe: int) -> str:
    """Convierte céntimos al formato utilizado en formularios."""

    euros, centimos = divmod(importe, 100)

    return f"{euros},{centimos:02d}"


def _comprobar_documento_duplicado(
    session,
    *,
    inmueble: Inmueble,
    valores: dict,
    excluir_id: int | None = None,
) -> str | None:
    """Bloquea duplicados locales o avisa de otros inmuebles."""

    duplicados = buscar_documentos_duplicados(
        session,
        tercero_nombre=valores["tercero_nombre"],
        tercero_nif=valores["tercero_nif"],
        referencia_documento=valores[
            "referencia_documento"
        ],
        excluir_id=excluir_id,
    )

    if not duplicados:
        return None

    if any(
        apunte.inmueble_id == inmueble.id
        for apunte in duplicados
    ):
        raise ContabilidadError(
            "Ya existe un apunte de este inmueble con "
            "la misma referencia y el mismo emisor."
        )

    referencias = sorted({
        apunte.inmueble.referencia
        for apunte in duplicados
    })

    return (
        "Ya existe un documento con la misma referencia "
        "y el mismo emisor en otro inmueble: "
        f"{', '.join(referencias)}. "
        "Puede guardarlo si corresponde repartir el "
        "documento entre varios inmuebles."
    )


def _datos_apunte_formulario(
    datos,
    categorias,
) -> tuple[int, dict]:
    """Interpreta y normaliza los datos enviados por el formulario."""

    inmueble_id = int(datos["inmueble_id"])
    fecha = _fecha(datos["fecha"])

    (
        naturaleza,
        categoria,
        subcategoria,
    ) = _separar_clasificacion(
        datos["clasificacion"],
        categorias,
    )

    periodo_desde, periodo_hasta = _periodo(
        datos.get("periodo_desde", ""),
        datos.get("periodo_hasta", ""),
    )

    valores = {
        "categorias": categorias,
        "fecha": fecha,
        "naturaleza": naturaleza,
        "categoria": categoria,
        "subcategoria": subcategoria,
        "concepto": datos["concepto"],
        "base": _importe_a_centimos(datos["base"]),
        "iva_importe": _importe_a_centimos(datos["iva_importe"]),
        "retencion_importe": _importe_a_centimos(datos["retencion_importe"]),
        "tercero_nombre": datos["tercero_nombre"],
        "tercero_nif": datos["tercero_nif"],
        "referencia_documento": datos["referencia_documento"],
        "ruta_documento": datos.get("ruta_documento", ""),
        "notas": datos.get("notas", ""),
        "periodo_desde": periodo_desde,
        "periodo_hasta": periodo_hasta,
        "tratamiento": datos.get("tratamiento", "CONTABILIZAR",),
        "nombre_documento": datos.get("nombre_documento", "",),
    }

    return inmueble_id, valores





@bp.get("/")
def listar_apuntes():
    """Muestra los apuntes ordenados y paginados."""

    pagina = request.args.get(
        "pagina",
        default=1,
        type=int,
    )

    pagina = max(pagina, 1)
    por_pagina = 25

    categorias = cargar_categorias_contables()
    session_factory = get_session_factory()

    with session_factory() as session:
        total = session.scalar(
            select(
                func.count(ApunteContable.id)
            )
        ) or 0

        total_paginas = max(
            1,
            (
                total
                + por_pagina
                - 1
            ) // por_pagina,
        )

        pagina = min(
            pagina,
            total_paginas,
        )

        apuntes = session.scalars(
            select(ApunteContable)
            .options(
                joinedload(ApunteContable.inmueble)
            )
            .order_by(
                ApunteContable.fecha.desc(),
                ApunteContable.id.desc(),
            )
            .offset(
                (pagina - 1) * por_pagina
            )
            .limit(por_pagina)
        ).all()

        return render_template(
            "contabilidad/lista.html",
            apuntes=apuntes,
            pagina=pagina,
            total_paginas=total_paginas,
            categorias=categorias,
            naturalezas=NATURALEZAS_APUNTE,
            tratamientos=TRATAMIENTOS_APUNTE,
            clasificacion_a_texto=(
                _clasificacion_a_texto
            ),
            importe_a_texto=_importe_a_texto,
            database_name=get_database_name(),
        )


@bp.route("/nuevo", methods=["GET", "POST"])
def nuevo_apunte():
    """Permite validar y crear un apunte contable."""

    if request.method == "GET":
        contenido, _ = _mostrar_formulario_apunte(
            titulo="Nuevo apunte contable",
            datos={
                "fecha": date.today().strftime("%d/%m/%Y"),
                "tratamiento": "CONTABILIZAR",
            },
            error=None,
        )

        return contenido

    categorias = cargar_categorias_contables()
    datos_formulario = dict(request.form)

    try:
        inmueble_id, valores = _datos_apunte_formulario(
            request.form,
            categorias,
        )

        accion = request.form.get("accion", "")

        if accion not in {"validar", "guardar"}:
            raise ValueError(
                "La acción solicitada no es válida."
            )

        if accion == "guardar":
            if not _formulario_sigue_validado(
                request.form
            ):
                raise ValueError(
                    "Los datos han cambiado desde la última "
                    "validación. Debe validarlos de nuevo."
                )

            valores["nombre_documento"] = (
                _validar_nombre_documento(
                    valores["nombre_documento"]
                )
            )

        session_factory = get_session_factory()

        with session_factory() as session:
            inmueble = session.get(
                Inmueble,
                inmueble_id,
            )

            if inmueble is None:
                raise ValueError(
                    "El inmueble seleccionado no existe."
                )

            if accion == "validar":
                _preparar_campos_automaticos(
                    inmueble=inmueble,
                    categorias=categorias,
                    valores=valores,
                    datos_formulario=datos_formulario,
                )

                apunte = crear_apunte_contable(
                    inmueble=inmueble,
                    **valores,
                )

                aviso = _comprobar_documento_duplicado(
                    session,
                    inmueble=inmueble,
                    valores=valores,
                )

                datos_formulario["nombre_documento"] = (
                    apunte.nombre_documento
                )
                datos_formulario["importe_a_pagar"] = (
                    _importe_para_formulario(
                        apunte.total
                    )
                )
                datos_formulario["firma_validacion"] = (
                    _firma_formulario(
                        datos_formulario
                    )
                )

                return _mostrar_formulario_apunte(
                    titulo="Nuevo apunte contable",
                    datos=datos_formulario,
                    error=None,
                    aviso=aviso,
                )

        with session_factory() as session:
            with session.begin():
                inmueble = session.get(
                    Inmueble,
                    inmueble_id,
                )

                if inmueble is None:
                    raise ValueError(
                        "El inmueble seleccionado no existe."
                    )

                _comprobar_documento_duplicado(
                    session,
                    inmueble=inmueble,
                    valores=valores,
                )

                apunte = crear_apunte_contable(
                    inmueble=inmueble,
                    **valores,
                )

                session.add(apunte)

    except (
        KeyError,
        ValueError,
        ContabilidadError,
    ) as exc:
        datos_formulario.pop(
            "firma_validacion",
            None,
        )
        datos_formulario.pop(
            "importe_a_pagar",
            None,
        )

        return _mostrar_formulario_apunte(
            titulo="Nuevo apunte contable",
            datos=datos_formulario,
            error=str(exc),
            status_code=400,
        )

    return redirect(
        url_for("contabilidad.listar_apuntes")
    )


@bp.route(
    "/<int:apunte_id>/editar",
    methods=["GET", "POST"],
)
def editar_apunte(apunte_id: int):
    """Permite validar y modificar un apunte contable."""

    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            apunte = session.get(
                ApunteContable,
                apunte_id,
            )

            if apunte is None:
                return "Apunte contable no encontrado.", 404

            clasificacion = apunte.categoria

            if apunte.subcategoria:
                clasificacion += (
                    f".{apunte.subcategoria}"
                )

            (
                periodo_desde,
                periodo_hasta,
            ) = _periodo_para_formulario(
                apunte.periodo_desde,
                apunte.periodo_hasta,
            )

            categorias = cargar_categorias_contables()

            concepto_base = _proponer_concepto(
                categorias,
                apunte.categoria,
                apunte.subcategoria or "",
            )

            concepto_esperado = _completar_concepto_automatico(
                concepto_base,
                apunte.periodo_desde,
                apunte.periodo_hasta,
            )

            concepto_es_automatico = (
                apunte.concepto == concepto_esperado
            )

            concepto_automatico = (
                concepto_esperado
                if concepto_es_automatico
                else ""
            )

            nombre_esperado = proponer_nombre_documento(
                inmueble=apunte.inmueble,
                concepto=(
                    concepto_base
                    if concepto_es_automatico
                    else apunte.concepto
                ),
                periodo_desde=apunte.periodo_desde,
                periodo_hasta=apunte.periodo_hasta,
            )

            nombre_automatico = (
                nombre_esperado
                if apunte.nombre_documento == nombre_esperado
                else ""
            )

            datos = {
                "inmueble_id": str(
                    apunte.inmueble_id
                ),
                "fecha": apunte.fecha.strftime(
                    "%d/%m/%Y"
                ),
                "clasificacion": clasificacion,
                "concepto": apunte.concepto,
                "periodo_desde": periodo_desde,
                "periodo_hasta": periodo_hasta,
                "tratamiento": apunte.tratamiento,
                "base": _importe_para_formulario(
                    apunte.base
                ),
                "iva_importe": (
                    _importe_para_formulario(
                        apunte.iva_importe
                    )
                ),
                "retencion_importe": (
                    _importe_para_formulario(
                        apunte.retencion_importe
                    )
                ),
                "importe_a_pagar": (
                    _importe_para_formulario(
                        apunte.total
                    )
                ),
                "nombre_documento": (
                    apunte.nombre_documento
                ),
                "tercero_nombre": (
                    apunte.tercero_nombre
                ),
                "tercero_nif": apunte.tercero_nif,
                "referencia_documento": (
                    apunte.referencia_documento
                ),
                "concepto_automatico": concepto_automatico,
                "nombre_documento_automatico": nombre_automatico,
            }

        contenido, _ = _mostrar_formulario_apunte(
            titulo="Editar apunte contable",
            datos=datos,
            error=None,
        )

        return contenido

    categorias = cargar_categorias_contables()
    datos_formulario = dict(request.form)

    try:
        inmueble_id, valores = _datos_apunte_formulario(
            request.form,
            categorias,
        )

        accion = request.form.get("accion", "")

        if accion not in {"validar", "guardar"}:
            raise ValueError(
                "La acción solicitada no es válida."
            )

        if accion == "guardar":
            if not _formulario_sigue_validado(
                request.form
            ):
                raise ValueError(
                    "Los datos han cambiado desde la última "
                    "validación. Debe validarlos de nuevo."
                )

            valores["nombre_documento"] = (
                _validar_nombre_documento(
                    valores["nombre_documento"]
                )
            )

        with session_factory() as session:
            apunte = session.get(
                ApunteContable,
                apunte_id,
            )

            if apunte is None:
                return (
                    "Apunte contable no encontrado.",
                    404,
                )

            inmueble = session.get(
                Inmueble,
                inmueble_id,
            )

            if inmueble is None:
                raise ValueError(
                    "El inmueble seleccionado no existe."
                )

            if accion == "validar":
                _preparar_campos_automaticos(
                    inmueble=inmueble,
                    categorias=categorias,
                    valores=valores,
                    datos_formulario=datos_formulario,
                )

                apunte_validado = crear_apunte_contable(
                    inmueble=inmueble,
                    **valores,
                )

                aviso = _comprobar_documento_duplicado(
                    session,
                    inmueble=inmueble,
                    valores=valores,
                    excluir_id=apunte_id,
                )

                datos_formulario["nombre_documento"] = (
                    apunte_validado.nombre_documento
                )
                datos_formulario["importe_a_pagar"] = (
                    _importe_para_formulario(
                        apunte_validado.total
                    )
                )
                datos_formulario["firma_validacion"] = (
                    _firma_formulario(
                        datos_formulario
                    )
                )

                return _mostrar_formulario_apunte(
                    titulo="Editar apunte contable",
                    datos=datos_formulario,
                    error=None,
                    aviso=aviso,
                )

        with session_factory() as session:
            with session.begin():
                apunte = session.get(
                    ApunteContable,
                    apunte_id,
                )

                if apunte is None:
                    return (
                        "Apunte contable no encontrado.",
                        404,
                    )

                inmueble = session.get(
                    Inmueble,
                    inmueble_id,
                )

                if inmueble is None:
                    raise ValueError(
                        "El inmueble seleccionado no existe."
                    )

                if "ruta_documento" not in request.form:
                    valores["ruta_documento"] = (
                        apunte.ruta_documento
                    )

                if "notas" not in request.form:
                    valores["notas"] = (
                        apunte.notas or ""
                    )

                _comprobar_documento_duplicado(
                    session,
                    inmueble=inmueble,
                    valores=valores,
                    excluir_id=apunte_id,
                )

                modificar_apunte_contable(
                    apunte=apunte,
                    inmueble=inmueble,
                    **valores,
                )

    except (
        KeyError,
        ValueError,
        ContabilidadError,
    ) as exc:
        datos_formulario.pop(
            "firma_validacion",
            None,
        )
        datos_formulario.pop(
            "importe_a_pagar",
            None,
        )

        return _mostrar_formulario_apunte(
            titulo="Editar apunte contable",
            datos=datos_formulario,
            error=str(exc),
            status_code=400,
        )

    return redirect(
        url_for("contabilidad.listar_apuntes")
    )


@bp.route(
    "/<int:apunte_id>/eliminar",
    methods=["GET", "POST"],
)
def eliminar_apunte(apunte_id: int):
    """Solicita confirmación y elimina un apunte."""

    session_factory = get_session_factory()

    if request.method == "GET":
        with session_factory() as session:
            apunte = session.get(
                ApunteContable,
                apunte_id,
            )

            if apunte is None:
                return "Apunte contable no encontrado.", 404

            movimientos_pendientes = sum(
                movimiento.estado == "PENDIENTE"
                for movimiento in apunte.movimientos_previstos
            )

            tiene_conciliados = any(
                movimiento.estado == "CONCILIADO"
                for movimiento in apunte.movimientos_previstos
            )

            return render_template(
                "contabilidad/eliminar.html",
                apunte=apunte,
                movimientos_pendientes=movimientos_pendientes,
                tiene_conciliados=tiene_conciliados,
                error=None,
                database_name=get_database_name(),
            )

    try:
        with session_factory() as session:
            with session.begin():
                apunte = session.get(
                    ApunteContable,
                    apunte_id,
                )

                if apunte is None:
                    return (
                        "Apunte contable no encontrado.",
                        404,
                    )

                eliminar_apunte_contable(
                    session,
                    apunte,
                )

    except ContabilidadError as exc:
        with session_factory() as session:
            apunte = session.get(
                ApunteContable,
                apunte_id,
            )

            if apunte is None:
                return "Apunte contable no encontrado.", 404

            movimientos_pendientes = sum(
                movimiento.estado == "PENDIENTE"
                for movimiento in apunte.movimientos_previstos
            )

            return (
                render_template(
                    "contabilidad/eliminar.html",
                    apunte=apunte,
                    movimientos_pendientes=movimientos_pendientes,
                    tiene_conciliados=True,
                    error=str(exc),
                    database_name=get_database_name(),
                ),
                400,
            )

    return redirect(
        url_for("contabilidad.listar_apuntes")
    )




"""Implementa la lógica de negocio de los apuntes contables."""

from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from calendar import monthrange

from contab.config import (
    CategoriaContable,
    validar_clasificacion_contable,
)
from contab.models import ApunteContable, Inmueble


class ContabilidadError(Exception):
    """Indica que no puede crearse un apunte contable válido."""


def _datos_apunte_contable(
    *,
    categorias: dict[str, CategoriaContable],
    fecha: date,
    naturaleza: str,
    categoria: str,
    concepto: str,
    base: int,
    subcategoria: str = "",
    iva_importe: int = 0,
    retencion_importe: int = 0,
    tercero_nombre: str = "",
    tercero_nif: str = "",
    referencia_documento: str = "",
    ruta_documento: str = "",
    notas: str = "",
    periodo_desde: date | None = None,
    periodo_hasta: date | None = None,
    tratamiento: str = "CONTABILIZAR",
    nombre_documento: str = "",
) -> dict[str, object]:
    """Valida y normaliza los datos de un apunte."""

    naturaleza = naturaleza.strip().upper()
    categoria = categoria.strip().upper()
    subcategoria = subcategoria.strip().upper()
    concepto = concepto.strip()
    tratamiento = tratamiento.strip().upper()
    nombre_documento = nombre_documento.strip()

    try:
        validar_clasificacion_contable(
            categorias,
            naturaleza,
            categoria,
            subcategoria,
        )
    except ValueError as exc:
        raise ContabilidadError(str(exc)) from exc

    if not concepto:
        raise ContabilidadError(
            "El concepto del apunte es obligatorio."
        )

    if base < 0:
        raise ContabilidadError(
            "La base del apunte no puede ser negativa."
        )

    if iva_importe < 0:
        raise ContabilidadError(
            "El IVA del apunte no puede ser negativo."
        )

    if retencion_importe < 0:
        raise ContabilidadError(
            "La retención del apunte no puede ser negativa."
        )

    total = base + iva_importe - retencion_importe

    if total < 0:
        raise ContabilidadError(
            "El total del apunte no puede ser negativo."
        )

    if (periodo_desde is None) != (periodo_hasta is None):
        raise ContabilidadError(
            "El período debe indicar las dos fechas o ninguna."
        )

    if (
        periodo_desde is not None
        and periodo_hasta < periodo_desde
    ):
        raise ContabilidadError(
            "El final del período no puede ser anterior al inicio."
        )

    if tratamiento not in {
        "CONTABILIZAR",
        "REPERCUTIR",
        "FACTURAR",
    }:
        raise ContabilidadError(
            "El tratamiento del apunte no es válido."
        )

    return {
        "fecha": fecha,
        "naturaleza": naturaleza,
        "categoria": categoria,
        "subcategoria": subcategoria or None,
        "concepto": concepto,
        "base": base,
        "iva_importe": iva_importe,
        "retencion_importe": retencion_importe,
        "total": total,
        "tercero_nombre": tercero_nombre.strip(),
        "tercero_nif": tercero_nif.strip().upper(),
        "referencia_documento": referencia_documento.strip(),
        "ruta_documento": ruta_documento.strip(),
        "notas": notas.strip() or None,
        "periodo_desde": periodo_desde,
        "periodo_hasta": periodo_hasta,
        "tratamiento": tratamiento,
        "nombre_documento": nombre_documento,
    }


def _texto_comparable(texto: str) -> str:
    """Normaliza un texto para comparaciones internas."""

    return " ".join(
        texto.strip().split()
    ).casefold()


def buscar_documentos_duplicados(
    session: Session,
    *,
    tercero_nombre: str,
    tercero_nif: str,
    referencia_documento: str,
    excluir_id: int | None = None,
) -> list[ApunteContable]:
    """Busca apuntes que parecen proceder del mismo documento."""

    referencia = _texto_comparable(
        referencia_documento
    )
    nombre = _texto_comparable(
        tercero_nombre
    )
    nif = _texto_comparable(
        tercero_nif
    )

    if not referencia:
        return []

    if not nif and not nombre:
        return []

    apuntes = session.scalars(
        select(ApunteContable)
        .order_by(ApunteContable.id)
    ).all()

    duplicados = []

    for apunte in apuntes:
        if (
            excluir_id is not None
            and apunte.id == excluir_id
        ):
            continue

        if (
            _texto_comparable(
                apunte.referencia_documento
            )
            != referencia
        ):
            continue

        apunte_nif = _texto_comparable(
            apunte.tercero_nif
        )
        apunte_nombre = _texto_comparable(
            apunte.tercero_nombre
        )

        if nif and apunte_nif:
            mismo_emisor = nif == apunte_nif
        else:
            mismo_emisor = (
                bool(nombre)
                and bool(apunte_nombre)
                and nombre == apunte_nombre
            )

        if mismo_emisor:
            duplicados.append(apunte)

    return duplicados


def _validar_tratamiento_inmueble(
    inmueble: Inmueble,
    fecha: date,
    tratamiento: str,
) -> None:
    """Comprueba que el inmueble admite el tratamiento elegido."""

    if tratamiento == "CONTABILIZAR":
        return

    if inmueble.tipo == "T":
        if tratamiento == "FACTURAR":
            raise ContabilidadError(
                "Un inmueble subdividido no puede tener "
                "apuntes destinados a facturación."
            )

        # REPERCUTIR significa distribuir entre los locales.
        return

    contratos_vigentes = [
        contrato
        for contrato in inmueble.contratos
        if contrato.fecha_inicio <= fecha
        and (
            contrato.fecha_fin is None
            or contrato.fecha_fin >= fecha
        )
    ]

    if not contratos_vigentes:
        raise ContabilidadError(
            "Para trasladar o facturar el gasto debe existir "
            "un contrato vigente en la fecha del apunte."
        )

    if len(contratos_vigentes) > 1:
        raise ContabilidadError(
            "El inmueble tiene más de un contrato vigente "
            "en la fecha del apunte."
        )



def proponer_nombre_documento(
    *,
    inmueble: Inmueble,
    concepto: str,
    periodo_desde: date | None = None,
    periodo_hasta: date | None = None,
) -> str:
    """Propone el nombre del documento soporte."""

    concepto = " ".join(concepto.strip().split())

    if not concepto:
        raise ContabilidadError(
            "El concepto del apunte es obligatorio."
        )

    if (periodo_desde is None) != (periodo_hasta is None):
        raise ContabilidadError(
            "El período debe indicar las dos fechas o ninguna."
        )

    if (
        periodo_desde is not None
        and periodo_hasta < periodo_desde
    ):
        raise ContabilidadError(
            "El final del período no puede ser anterior al inicio."
        )

    referencia = inmueble.referencia.strip()

    referencia = (
        referencia
        .replace("/", "-")
        .replace("\\", "-")
    )
    concepto = (
        concepto
        .replace("/", "-")
        .replace("\\", "-")
    )

    periodo = ""

    if periodo_desde is not None:
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
            periodo = periodo_desde.strftime(
                " %Y-%m"
            )
        else:
            periodo = (
                f" {periodo_desde:%Y-%m-%d}"
                f" a {periodo_hasta:%Y-%m-%d}"
            )

    return f"{referencia}-{concepto}{periodo}.pdf"


def crear_apunte_contable(
    *,
    inmueble: Inmueble,
    categorias: dict[str, CategoriaContable],
    fecha: date,
    naturaleza: str,
    categoria: str,
    concepto: str,
    base: int,
    subcategoria: str = "",
    iva_importe: int = 0,
    retencion_importe: int = 0,
    tercero_nombre: str = "",
    tercero_nif: str = "",
    referencia_documento: str = "",
    ruta_documento: str = "",
    notas: str = "",
    periodo_desde: date | None = None,
    periodo_hasta: date | None = None,
    tratamiento: str = "CONTABILIZAR",
    nombre_documento: str = "",
) -> ApunteContable:
    """Prepara un apunte contable validado sin persistirlo."""

    datos = _datos_apunte_contable(
        categorias=categorias,
        fecha=fecha,
        naturaleza=naturaleza,
        categoria=categoria,
        subcategoria=subcategoria,
        concepto=concepto,
        base=base,
        iva_importe=iva_importe,
        retencion_importe=retencion_importe,
        tercero_nombre=tercero_nombre,
        tercero_nif=tercero_nif,
        referencia_documento=referencia_documento,
        ruta_documento=ruta_documento,
        notas=notas,
        periodo_desde=periodo_desde,
        periodo_hasta=periodo_hasta,
        tratamiento=tratamiento,
        nombre_documento=nombre_documento,
    )

    _validar_tratamiento_inmueble(
        inmueble,
        fecha=datos["fecha"],
        tratamiento=datos["tratamiento"],
    )

    return ApunteContable(
        inmueble=inmueble,
        **datos,
    )


def eliminar_apunte_contable(
    session: Session,
    apunte: ApunteContable,
) -> None:
    """Elimina un apunte y sus movimientos todavía pendientes."""

    if any(
        movimiento.estado == "CONCILIADO"
        for movimiento in apunte.movimientos_previstos
    ):
        raise ContabilidadError(
            "No puede eliminarse un apunte que tiene "
            "movimientos conciliados."
        )

    for movimiento in list(
        apunte.movimientos_previstos
    ):
        session.delete(movimiento)

    session.delete(apunte)


def modificar_apunte_contable(
    *,
    apunte: ApunteContable,
    inmueble: Inmueble,
    categorias: dict[str, CategoriaContable],
    fecha: date,
    naturaleza: str,
    categoria: str,
    concepto: str,
    base: int,
    subcategoria: str = "",
    iva_importe: int = 0,
    retencion_importe: int = 0,
    tercero_nombre: str = "",
    tercero_nif: str = "",
    referencia_documento: str = "",
    ruta_documento: str = "",
    notas: str = "",
    periodo_desde: date | None = None,
    periodo_hasta: date | None = None,
    tratamiento: str = "CONTABILIZAR",
    nombre_documento: str = "",
) -> ApunteContable:
    """Modifica un apunte después de validar todos sus datos."""

    datos = _datos_apunte_contable(
        categorias=categorias,
        fecha=fecha,
        naturaleza=naturaleza,
        categoria=categoria,
        subcategoria=subcategoria,
        concepto=concepto,
        base=base,
        iva_importe=iva_importe,
        retencion_importe=retencion_importe,
        tercero_nombre=tercero_nombre,
        tercero_nif=tercero_nif,
        referencia_documento=referencia_documento,
        ruta_documento=ruta_documento,
        notas=notas,
        periodo_desde=periodo_desde,
        periodo_hasta=periodo_hasta,
        tratamiento=tratamiento,
        nombre_documento=nombre_documento,
    )

    _validar_tratamiento_inmueble(
        inmueble,
        fecha=datos["fecha"],
        tratamiento=datos["tratamiento"],
    )

    apunte.inmueble = inmueble

    for campo, valor in datos.items():
        setattr(apunte, campo, valor)

    return apunte



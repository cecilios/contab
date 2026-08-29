"""Implementa la lógica de negocio de los apuntes contables."""

from datetime import date
from sqlalchemy.orm import Session

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
) -> dict[str, object]:
    """Valida y normaliza los datos de un apunte."""

    naturaleza = naturaleza.strip().upper()
    categoria = categoria.strip().upper()
    subcategoria = subcategoria.strip().upper()
    concepto = concepto.strip()

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
    }



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
    )

    apunte.inmueble = inmueble

    for campo, valor in datos.items():
        setattr(apunte, campo, valor)

    return apunte



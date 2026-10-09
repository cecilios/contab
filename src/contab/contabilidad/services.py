"""Implementa la lógica de negocio de los apuntes contables."""

from datetime import date, timedelta
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
from calendar import monthrange

from contab.calculos import redondear_division
from contab.config import (
    CategoriaContable,
    validar_clasificacion_contable,
)
from contab.models import (
    ApunteContable,
    Contrato,
    DistribucionApunte,
    Inmueble,
)



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
    criterio_periodo: str | None = None,
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
    criterio_periodo = (
        criterio_periodo.strip().upper()
        if criterio_periodo is not None
        else None
    )

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

    if periodo_desde is None:
        if criterio_periodo is not None:
            raise ContabilidadError(
                "No puede indicarse un criterio de período "
                "sin indicar un período."
            )
    else:
        if criterio_periodo not in {
            "EXCLUIR_HASTA",
            "EXCLUIR_DESDE",
            "INCLUIR_AMBOS",
            "EXCLUIR_AMBOS",
        }:
            raise ContabilidadError(
                "El criterio del período no es válido."
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
        "criterio_periodo": criterio_periodo,
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


def _repartir_importe(
    importe: int,
    locales: list[Inmueble],
) -> list[int]:
    """Reparte un importe según participación conservando los céntimos."""

    repartos: list[int] = []
    acumulado = 0

    for local in locales[:-1]:
        reparto = redondear_division(
            importe * local.participacion,
            10000,
        )

        repartos.append(reparto)
        acumulado += reparto

    repartos.append(
        importe - acumulado
    )

    return repartos


def calcular_reparto_contratos(
    *,
    inmueble: Inmueble,
    importe: int,
    fecha: date,
    periodo_desde: date | None,
    periodo_hasta: date | None,
    criterio_periodo: str | None,
) -> tuple[list[tuple[Contrato, int]], int]:
    """Reparte un importe entre contratos y propietario según su período."""

    if periodo_desde is None:
        contratos = [
            contrato
            for contrato in inmueble.contratos
            if contrato.fecha_inicio <= fecha
            and (
                contrato.fecha_fin is None
                or contrato.fecha_fin >= fecha
            )
        ]

        if len(contratos) > 1:
            raise ContabilidadError(
                "Hay más de un contrato aplicable en la fecha del apunte."
            )

        if not contratos:
            return [], importe

        return [(contratos[0], importe)], 0

    if periodo_hasta is None or criterio_periodo is None:
        raise ContabilidadError(
            "El período y su criterio deben estar completos."
        )

    desde = periodo_desde
    hasta = periodo_hasta

    if criterio_periodo in {
        "EXCLUIR_DESDE",
        "EXCLUIR_AMBOS",
    }:
        desde += timedelta(days=1)

    if criterio_periodo in {
        "EXCLUIR_HASTA",
        "EXCLUIR_AMBOS",
    }:
        hasta -= timedelta(days=1)

    if desde > hasta:
        raise ContabilidadError(
            "El período no contiene días efectivos."
        )

    dias_totales = (
        hasta - desde
    ).days + 1

    contratos_con_dias: list[
        tuple[Contrato, int]
    ] = []

    intervalos: list[
        tuple[date, date]
    ] = []

    contratos = sorted(
        inmueble.contratos,
        key=lambda contrato: (
            contrato.fecha_inicio,
            contrato.id or 0,
        ),
    )

    for contrato in contratos:
        inicio = max(
            desde,
            contrato.fecha_inicio,
        )

        fin_contrato = (
            contrato.fecha_fin
            if contrato.fecha_fin is not None
            else hasta
        )

        fin = min(
            hasta,
            fin_contrato,
        )

        if inicio > fin:
            continue

        if intervalos and inicio <= intervalos[-1][1]:
            raise ContabilidadError(
                "Hay contratos solapados durante el período del apunte."
            )

        dias = (
            fin - inicio
        ).days + 1

        contratos_con_dias.append(
            (contrato, dias)
        )
        intervalos.append(
            (inicio, fin)
        )

    dias_contrato = sum(
        dias
        for _, dias in contratos_con_dias
    )

    dias_propietario = (
        dias_totales - dias_contrato
    )

    destinos: list[
        tuple[Contrato | None, int]
    ] = [
        (contrato, dias)
        for contrato, dias in contratos_con_dias
    ]

    if dias_propietario:
        destinos.append(
            (None, dias_propietario)
        )

    if not destinos:
        return [], importe

    reparto: list[
        tuple[Contrato, int]
    ] = []
    propietario = 0
    acumulado = 0

    for indice, (contrato, dias) in enumerate(
        destinos
    ):
        es_ultimo = (
            indice == len(destinos) - 1
        )

        if es_ultimo:
            parte = importe - acumulado
        else:
            parte = redondear_division(
                importe * dias,
                dias_totales,
            )
            acumulado += parte

        if contrato is None:
            propietario = parte
        elif parte:
            reparto.append(
                (contrato, parte)
            )

    return reparto, propietario


def _preparar_distribuciones(
    apunte: ApunteContable,
) -> None:
    """Distribuye un apunte de un inmueble subdividido entre sus locales."""

    inmueble = apunte.inmueble

    if inmueble.tipo != "T":
        return

    locales = sorted(
        inmueble.locales,
        key=lambda local: local.referencia,
    )

    if not locales:
        raise ContabilidadError(
            "Un inmueble subdividido debe tener locales "
            "para distribuir sus apuntes."
        )

    if sum(
        local.participacion
        for local in locales
    ) != 10000:
        raise ContabilidadError(
            "Las participaciones de los locales deben "
            "sumar el 100 %."
        )

    bases = _repartir_importe(
        apunte.base,
        locales,
    )
    ivas = _repartir_importe(
        apunte.iva_importe,
        locales,
    )
    retenciones = _repartir_importe(
        apunte.retencion_importe,
        locales,
    )

    for local, base, iva, retencion in zip(
        locales,
        bases,
        ivas,
        retenciones,
        strict=True,
    ):
        apunte.distribuciones.append(
            DistribucionApunte(
                inmueble=local,
                participacion=local.participacion,
                base=base,
                iva_importe=iva,
                retencion_importe=retencion,
                total=base + iva - retencion,
            )
        )


def _eliminar_distribuciones(
    session: Session,
    apunte: ApunteContable,
) -> None:
    """Elimina las distribuciones de un apunte."""

    for distribucion in list(
        apunte.distribuciones
    ):
        apunte.distribuciones.remove(
            distribucion
        )

        if inspect(distribucion).persistent:
            session.delete(distribucion)



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
    criterio_periodo: str | None = None,
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
        criterio_periodo=criterio_periodo,
        tratamiento=tratamiento,
        nombre_documento=nombre_documento,
    )

    apunte = ApunteContable(
        inmueble=inmueble,
        **datos,
    )

    _preparar_distribuciones(apunte)

    return apunte


def eliminar_apunte_contable(
    session: Session,
    apunte: ApunteContable,
) -> None:
    """Elimina un apunte y sus movimientos todavía pendientes."""

    if any(
        movimiento.estado in {
            "CONCILIADO",
            "PARCIAL",
        }
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

    _eliminar_distribuciones(
        session,
        apunte,
    )

    session.delete(apunte)


def validar_modificacion_con_movimientos(
    *,
    apunte: ApunteContable,
    inmueble: Inmueble,
    naturaleza: str,
    total: int,
) -> None:
    """Valida cambios incompatibles con movimientos ya conciliados."""

    tiene_movimientos_protegidos = any(
        movimiento.estado in {
            "CONCILIADO",
            "PARCIAL",
        }
        for movimiento in apunte.movimientos_previstos
    )

    cambia_datos_economicos = (
        inmueble is not apunte.inmueble
        or naturaleza != apunte.naturaleza
        or total != apunte.total
    )

    if (
        tiene_movimientos_protegidos
        and cambia_datos_economicos
    ):
        raise ContabilidadError(
            "No puede cambiarse el inmueble, la naturaleza "
            "o el importe de un apunte con un movimiento "
            "conciliado total o parcialmente."
        )


def modificar_apunte_contable(
    session: Session,
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
    criterio_periodo: str | None = None,
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
        criterio_periodo=criterio_periodo,
        tratamiento=tratamiento,
        nombre_documento=nombre_documento,
    )

    validar_modificacion_con_movimientos(
        apunte=apunte,
        inmueble=inmueble,
        naturaleza=datos["naturaleza"],
        total=datos["total"],
    )

    recalcular_distribuciones = (
        inmueble is not apunte.inmueble
        or datos["base"] != apunte.base
        or datos["iva_importe"] != apunte.iva_importe
        or datos["retencion_importe"]
        != apunte.retencion_importe
    )

    if recalcular_distribuciones:
        _eliminar_distribuciones(
            session,
            apunte,
        )

    if inspect(apunte).persistent:
        session.flush()

    apunte.inmueble = inmueble

    for campo, valor in datos.items():
        setattr(apunte, campo, valor)

    if recalcular_distribuciones:
        _preparar_distribuciones(apunte)

    for movimiento in apunte.movimientos_previstos:
        movimiento.inmueble = apunte.inmueble
        movimiento.naturaleza = apunte.naturaleza
        movimiento.concepto = apunte.concepto
        movimiento.importe_esperado = apunte.total
        movimiento.contraparte = apunte.tercero_nombre

    return apunte



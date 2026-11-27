"""Implementa la lógica de negocio relacionada con contratos y rentas."""

from calendar import monthrange
from datetime import date

from contab.models import (
    AjusteRenta,
    AnexoContrato,
    Contrato,
    ContratoInquilino,
    Inquilino,
    RentaContrato,
    RevisionRenta,
)

from contab.calculos import redondear_division


class RentaNoDisponibleError(Exception):
    """Indica que no existe una renta aplicable para la fecha solicitada."""

class RentaFacturableError(Exception):
    """Indica que no puede calcularse una renta facturable válida."""

class AjusteRentaError(Exception):
    """Indica que los datos de un ajuste de renta no son válidos."""

class RentaContratoError(Exception):
    """Indica que los datos de una renta contractual no son válidos."""

class RevisionRentaError(Exception):
    """Indica que los datos de una revisión de renta no son válidos."""

class ContratoError(Exception):
    """Indica que los datos o condiciones de un contrato no son válidos."""

METODOS_REVISION = {
    "IPC_NACIONAL": "IPC Nacional",
    "IPC_AUTONOMICO": "IPC Autonómico",
    "IRAV": "IRAV (Indice ref. anual para Viviendas)",
    "FIJO": "Fijo",
}



def _es_ultimo_dia_del_mes(fecha: date) -> bool:
    """Indica si una fecha corresponde al último día de su mes."""
    ultimo_dia = monthrange(
        fecha.year,
        fecha.month,
    )[1]

    return fecha.day == ultimo_dia


def _validar_numero_anexo(
    contrato: Contrato,
    numero: int,
) -> None:
    """Comprueba que el número sea válido y no esté utilizado."""

    if numero <= 0:
        raise ContratoError(
            "El número de anexo debe ser positivo."
        )

    if any(
        anexo.numero == numero
        for anexo in contrato.anexos
    ):
        raise ContratoError(
            "Ya existe un anexo con ese número para el contrato."
        )




def renta_vigente(contrato: Contrato, fecha: date) -> RentaContrato:
    """Devuelve la renta ordinaria vigente de un contrato en una fecha."""
    rentas_aplicables = (
        renta
        for renta in contrato.rentas
        if renta.fecha_desde <= fecha
    )

    try:
        return max(
            rentas_aplicables,
            key=lambda renta: renta.fecha_desde,
        )
    except ValueError as exc:
        raise RentaNoDisponibleError(
            f"No existe renta vigente para el contrato {contrato.id} "
            f"en la fecha {fecha.isoformat()}."
        ) from exc


def renta_facturable(contrato: Contrato, fecha: date) -> int:
    """Devuelve en céntimos la renta facturable de un contrato en una fecha."""
    renta = renta_vigente(contrato, fecha)
    importe = renta.importe

    ajustes = [
        ajuste
        for ajuste in contrato.ajustes_renta
        if (
            ajuste.fecha_desde
            <= fecha
            <= ajuste.fecha_hasta
        )
    ]

    if len(ajustes) > 1:
        raise RentaFacturableError(
            f"El contrato {contrato.id} tiene varios ajustes activos "
            f"en la fecha {fecha.isoformat()}."
        )

    if not ajustes:
        return importe

    ajuste = ajustes[0]

    if ajuste.tipo == "REDUCCION_PORCENTUAL":
        return redondear_division(
            importe * (10000 - ajuste.valor),
            10000,
        )

    if ajuste.tipo == "REDUCCION_FIJA":
        resultado = importe - ajuste.valor

        if resultado < 0:
            raise RentaFacturableError(
                "La reducción fija produce una renta facturable negativa."
            )

        return resultado

    if ajuste.tipo == "IMPORTE_FIJO":
        return ajuste.valor

    raise RentaFacturableError(
        f"Tipo de ajuste desconocido: {ajuste.tipo}."
    )


def crear_ajuste_renta(
    contrato: Contrato,
    fecha_desde: date,
    fecha_hasta: date,
    tipo: str,
    valor: int,
) -> AjusteRenta:
    """Valida y crea un ajuste temporal de renta sin persistirlo."""
    tipos_validos = {
        "REDUCCION_PORCENTUAL",
        "REDUCCION_FIJA",
        "IMPORTE_FIJO",
    }

    if tipo not in tipos_validos:
        raise AjusteRentaError(
            f"Tipo de ajuste desconocido: {tipo}."
        )

    if fecha_desde.day != 1:
        raise AjusteRentaError(
            "La fecha inicial del ajuste debe ser "
            "el primer día del mes."
        )

    if not _es_ultimo_dia_del_mes(fecha_hasta):
        raise AjusteRentaError(
            "La fecha final del ajuste debe ser "
            "el último día del mes."
        )

    if fecha_hasta < fecha_desde:
        raise AjusteRentaError(
            "La fecha final del ajuste no puede ser anterior "
            "a la inicial."
        )

    if fecha_desde < contrato.fecha_inicio:
        raise AjusteRentaError(
            "El ajuste no puede comenzar antes del inicio del contrato."
        )

    if tipo == "REDUCCION_PORCENTUAL":
        if valor < 0 or valor > 10000:
            raise AjusteRentaError(
                "La reducción porcentual debe estar "
                "entre 0 % y 100 %."
            )
    elif valor < 0:
        raise AjusteRentaError(
            "El valor de una reducción fija o importe fijo "
            "no puede ser negativo."
        )

    for ajuste in contrato.ajustes_renta:
        hay_solapamiento = (
            fecha_desde <= ajuste.fecha_hasta
            and fecha_hasta >= ajuste.fecha_desde
        )

        if hay_solapamiento:
            raise AjusteRentaError(
                "El ajuste se solapa con otro ajuste existente."
            )

    return AjusteRenta(
        contrato=contrato,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        tipo=tipo,
        valor=valor,
    )


def crear_renta_contrato(
    contrato: Contrato,
    fecha_desde: date,
    importe: int,
    notas: str | None = None,
) -> RentaContrato:
    """Valida y crea una renta contractual sin persistirla."""
    if importe < 0:
        raise RentaContratoError(
            "El importe de la renta no puede ser negativo."
        )

    if fecha_desde < contrato.fecha_inicio:
        raise RentaContratoError(
            "La renta no puede comenzar antes del inicio del contrato."
        )

    if not contrato.rentas:
        if fecha_desde != contrato.fecha_inicio:
            raise RentaContratoError(
                "La primera renta debe comenzar en la fecha de inicio del contrato."
            )
    elif fecha_desde.day != 1:
        raise RentaContratoError(
            "Las rentas posteriores deben comenzar el día 1 del mes."
        )

    if any(renta.fecha_desde == fecha_desde for renta in contrato.rentas):
        raise RentaContratoError(
            "Ya existe una renta con esa fecha de inicio."
        )

    return RentaContrato(
        contrato=contrato,
        fecha_desde=fecha_desde,
        importe=importe,
        notas=notas,
    )


def crear_revision_renta(
    contrato: Contrato,
    fecha_prevista: date,
    metodo: str,
    notas: str | None = None,
) -> RevisionRenta:
    """Valida y crea una revisión de renta pendiente sin persistirla."""
    if fecha_prevista.day != 1:
        raise RevisionRentaError(
            "La fecha prevista de revisión debe ser el día 1 del mes."
        )

    if fecha_prevista < contrato.fecha_inicio:
        raise RevisionRentaError(
            "La revisión no puede ser anterior al inicio del contrato."
        )

    if metodo not in METODOS_REVISION:
        raise RevisionRentaError(
            "El método de revisión indicado no es válido."
        )

    if any(
        revision.fecha_prevista == fecha_prevista
        for revision in contrato.revisiones_renta
    ):
        raise RevisionRentaError(
            "Ya existe una revisión prevista para esa fecha."
        )

    return RevisionRenta(
        contrato=contrato,
        fecha_prevista=fecha_prevista,
        metodo=metodo,
        estado="PENDIENTE",
        notas=notas,
    )

def resolver_revision_renta(
    revision: RevisionRenta,
    fecha_resolucion: date,
    aplicar: bool,
    porcentaje_aplicado: int | None,
) -> tuple[RentaContrato | None, RevisionRenta]:
    """Resuelve una revisión y prepara la renta y revisión siguientes."""
    if revision.estado != "PENDIENTE":
        raise RevisionRentaError(
            "Sólo puede resolverse una revisión pendiente."
        )

    if aplicar and porcentaje_aplicado is None:
        raise RevisionRentaError(
            "Una revisión aplicada debe indicar el porcentaje."
        )

    if not aplicar and porcentaje_aplicado is not None:
        raise RevisionRentaError(
            "Una revisión no aplicada no debe indicar porcentaje."
        )

    contrato = revision.contrato
    nueva_renta = None

    if aplicar:
        renta_anterior = renta_vigente(
            contrato,
            revision.fecha_prevista,
        )

        nuevo_importe = redondear_division(
            renta_anterior.importe * (10000 + porcentaje_aplicado),
            10000,
        )

        if nuevo_importe < 0:
            raise RevisionRentaError(
                "La revisión produciría una renta negativa."
            )

        nueva_renta = crear_renta_contrato(
            contrato=contrato,
            fecha_desde=revision.fecha_prevista,
            importe=nuevo_importe,
        )

        revision.estado = "APLICADA"
        revision.porcentaje_aplicado = porcentaje_aplicado
    else:
        revision.estado = "NO_APLICADA"
        revision.porcentaje_aplicado = None

    revision.fecha_resolucion = fecha_resolucion

    siguiente_fecha = revision.fecha_prevista.replace(
        year=revision.fecha_prevista.year + 1,
    )

    siguiente_revision = crear_revision_renta(
        contrato=contrato,
        fecha_prevista=siguiente_fecha,
        metodo=revision.metodo,
    )

    return nueva_renta, siguiente_revision


def renta_inicial(contrato: Contrato) -> RentaContrato:
    """Devuelve la primera renta registrada para un contrato."""
    if not contrato.rentas:
        raise ContratoError(
            "El contrato no tiene una renta inicial registrada."
        )

    return min(
        contrato.rentas,
        key=lambda renta: renta.fecha_desde,
    )


def primera_revision(
    contrato: Contrato,
) -> RevisionRenta | None:
    """Devuelve la primera revisión del contrato, si existe."""

    return min(
        contrato.revisiones_renta,
        key=lambda revision: revision.fecha_prevista,
        default=None,
    )


def identidad_contrato_protegida(
    contrato: Contrato,
) -> bool:
    """Indica si el histórico impide modificar la identidad contractual."""

    return any(
        (
            contrato.facturas,
            contrato.movimientos_previstos,
            contrato.imputaciones,
            contrato.solicitudes_reembolso,
            contrato.anexos,
        )
    )


def contrato_tiene_alquileres_registrados(
    contrato: Contrato,
) -> bool:
    """Indica si el contrato tiene alquileres facturados o contabilizados."""

    if contrato.facturas:
        return True

    return any(
        movimiento.apunte is not None
        and movimiento.apunte.naturaleza == "INGRESO"
        and movimiento.apunte.categoria == "ING_ALQUILERES"
        for movimiento in contrato.movimientos_previstos
    )


def primera_revision_protegida(
    contrato: Contrato,
) -> bool:
    """Indica si el histórico impide modificar la primera revisión."""

    return (
        len(contrato.revisiones_renta) > 1
        or any(
            revision.estado != "PENDIENTE"
            for revision in contrato.revisiones_renta
        )
    )


def renta_inicial_protegida(
    contrato: Contrato,
) -> bool:
    """Indica si el histórico impide modificar la renta inicial."""

    return (
        contrato_tiene_alquileres_registrados(contrato)
        or len(contrato.rentas) > 1
        or any(
            revision.estado != "PENDIENTE"
            for revision in contrato.revisiones_renta
        )
        or any(
            anexo.tipo == "CAMBIO_RENTA"
            for anexo in contrato.anexos
        )
    )


def fecha_inicio_contrato_protegida(
    contrato: Contrato,
) -> bool:
    """Indica si el histórico impide modificar el inicio del contrato."""

    return (
        identidad_contrato_protegida(contrato)
        or len(contrato.rentas) > 1
        or len(contrato.revisiones_renta) > 1
        or any(
            revision.estado != "PENDIENTE"
            for revision in contrato.revisiones_renta
        )
        or bool(contrato.ajustes_renta)
    )


def validar_condiciones_economicas_edicion(
    contrato: Contrato,
    importe_renta_inicial: int,
    fecha_primera_revision: date | None,
    metodo_revision: str,
    genera_factura: bool,
) -> None:
    """Protege las condiciones económicas iniciales del contrato."""

    renta = renta_inicial(contrato)

    if (
        importe_renta_inicial != renta.importe
        and renta_inicial_protegida(contrato)
    ):
        raise ContratoError(
            "No puede modificarse la renta inicial "
            "de un contrato con histórico de rentas."
        )

    revision = primera_revision(contrato)

    if (
        revision is not None
        and primera_revision_protegida(contrato)
        and (
            fecha_primera_revision != revision.fecha_prevista
            or metodo_revision != revision.metodo
        )
    ):
        raise ContratoError(
            "No pueden modificarse los datos de la primera revisión "
            "cuando existen revisiones resueltas o posteriores."
        )

    if (
        genera_factura != contrato.genera_factura
        and contrato_tiene_alquileres_registrados(contrato)
    ):
        raise ContratoError(
            "No puede modificarse la opción de generar factura "
            "de un contrato con alquileres registrados."
        )


def validar_identidad_contrato(
    contrato: Contrato,
    inmueble_id: int,
    inquilinos_ids: list[int],
) -> None:
    """Impide modificar la identidad de un contrato protegido."""

    if not identidad_contrato_protegida(contrato):
        return

    if inmueble_id != contrato.inmueble_id:
        raise ContratoError(
            "No puede modificarse el inmueble de un contrato "
            "con histórico contractual o económico."
        )

    titulares_actuales = {
        titular.inquilino_id
        for titular in contrato.titulares
    }

    titulares_propuestos = set(inquilinos_ids)

    if titulares_actuales != titulares_propuestos:
        raise ContratoError(
            "No pueden modificarse los titulares de un contrato "
            "con histórico contractual o económico."
        )


def validar_fecha_fin_contrato(
    contrato: Contrato,
    fecha_inicio: date,
    fecha_fin: date | None,
) -> None:
    """Comprueba que la finalización respeta el histórico del contrato."""

    if fecha_fin is None:
        return

    if fecha_fin < fecha_inicio:
        raise ContratoError(
            "La fecha de finalización no puede ser anterior "
            "al inicio del contrato."
        )

    renta_original = renta_inicial(contrato)

    for renta in contrato.rentas:
        if renta is renta_original:
            continue

        if renta.fecha_desde > fecha_fin:
            raise ContratoError(
                "La fecha de resolución es anterior a una renta "
                "ya registrada."
            )

    for revision in contrato.revisiones_renta:
        if (
            revision.estado != "PENDIENTE"
            and revision.fecha_prevista > fecha_fin
        ):
            raise ContratoError(
                "La fecha de resolución es anterior a una "
                "revisión de renta ya resuelta."
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

    for movimiento in contrato.movimientos_previstos:
        apunte = movimiento.apunte

        if (
            apunte is not None
            and apunte.naturaleza == "INGRESO"
            and apunte.categoria == "ING_ALQUILERES"
            and apunte.periodo_desde is not None
            and apunte.periodo_desde > fecha_fin
        ):
            raise ContratoError(
                "La fecha de resolución es anterior a un alquiler "
                "ya contabilizado."
            )


def validar_coherencia_historica_edicion(
    contrato: Contrato,
    fecha_inicio: date,
    fecha_vencimiento: date,
    fecha_inicio_facturacion: date,
    fecha_fin: date | None,
    fecha_primera_revision: date | None,
) -> None:
    """Impide que una edición deje incoherente el histórico del contrato."""

    renta_original = renta_inicial(contrato)
    revision_original = primera_revision(contrato)

    for renta in contrato.rentas:
        if renta is renta_original:
            continue

        if renta.fecha_desde < fecha_inicio:
            raise ContratoError(
                "La nueva fecha de inicio es posterior a una renta "
                "ya registrada en el histórico."
            )

    for revision in contrato.revisiones_renta:
        if revision is revision_original:
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

    if (
        fecha_inicio != contrato.fecha_inicio
        and fecha_inicio_contrato_protegida(contrato)
    ):
        raise ContratoError(
            "No puede modificarse la fecha de inicio "
            "de un contrato con histórico contractual o económico."
        )

    if (
        fecha_inicio_facturacion
        != contrato.fecha_inicio_facturacion
        and contrato_tiene_alquileres_registrados(contrato)
    ):
        raise ContratoError(
            "No puede modificarse la fecha de inicio de facturación "
            "de un contrato con alquileres registrados."
        )

    validar_fecha_fin_contrato(
        contrato=contrato,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )


def validar_datos_primera_revision(
    genera_factura: bool,
    fecha_primera_revision: date | None,
    metodo_revision: str,
) -> None:
    """Valida la obligatoriedad de los datos de revisión."""

    if (
        fecha_primera_revision is None
        and not metodo_revision
    ):
        if genera_factura:
            raise ContratoError(
                "Los contratos que generan factura deben "
                "indicar la primera revisión de renta."
            )

        return

    if fecha_primera_revision is None:
        raise ContratoError(
            "Debe indicarse la fecha de la primera revisión."
        )

    if not metodo_revision:
        raise ContratoError(
            "La revisión debe indicar un método de actualización."
        )


def validar_datos_contrato(
    *,
    fecha_inicio: date,
    fecha_vencimiento: date,
    fecha_inicio_facturacion: date,
    fecha_fin: date | None,
    fianza: int,
    iva_porcentaje: int,
    retencion_porcentaje: int,
    renta_inicial: int,
    genera_factura: bool,
    fecha_primera_revision: date | None,
    metodo_revision: str,
) -> None:
    """Valida las condiciones generales de un contrato."""

    if fecha_vencimiento < fecha_inicio:
        raise ContratoError(
            "La fecha de vencimiento no puede ser anterior al inicio."
        )

    if fecha_inicio_facturacion < fecha_inicio:
        raise ContratoError(
            "La facturación no puede comenzar antes del contrato."
        )

    if fecha_inicio_facturacion.day != 1:
        raise ContratoError(
            "La fecha de inicio de facturación debe ser "
            "el día 1 del mes."
        )

    if fecha_fin is not None and fecha_fin < fecha_inicio:
        raise ContratoError(
            "La fecha de finalización no puede ser anterior "
            "al inicio del contrato."
        )

    if fianza < 0:
        raise ContratoError(
            "La fianza no puede ser negativa."
        )

    if iva_porcentaje < 0:
        raise ContratoError(
            "El porcentaje de IVA no puede ser negativo."
        )

    if retencion_porcentaje < 0:
        raise ContratoError(
            "El porcentaje de retención no puede ser negativo."
        )

    if renta_inicial < 0:
        raise ContratoError(
            "El importe de la renta no puede ser negativo."
        )

    validar_datos_primera_revision(
        genera_factura=genera_factura,
        fecha_primera_revision=fecha_primera_revision,
        metodo_revision=metodo_revision,
    )

    if fecha_primera_revision is not None:
        if fecha_primera_revision.day != 1:
            raise ContratoError(
                "La fecha prevista de revisión debe ser "
                "el día 1 del mes."
            )

        if fecha_primera_revision < fecha_inicio:
            raise ContratoError(
                "La revisión no puede ser anterior "
                "al inicio del contrato."
            )

        if metodo_revision not in METODOS_REVISION:
            raise ContratoError(
                "El método de revisión indicado no es válido."
            )


def crear_contrato(
    inmueble,
    titulares: list[Inquilino],
    fecha_inicio: date,
    fecha_vencimiento: date,
    genera_factura: bool,
    fecha_inicio_facturacion: date,
    fianza: int,
    iva_porcentaje: int,
    retencion_porcentaje: int,
    direccion_facturacion: str,
    codigo_postal_facturacion: str | None,
    poblacion_facturacion: str,
    provincia_facturacion: str,
    concepto_factura: str,
    renta_inicial: int,
    fecha_primera_revision: date | None,
    metodo_revision: str,
) -> Contrato:
    """Valida y prepara un contrato completo sin persistirlo."""

    if not titulares:
        raise ContratoError(
            "El contrato debe tener al menos un titular."
        )

    validar_datos_contrato(
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=fecha_vencimiento,
        fecha_inicio_facturacion=fecha_inicio_facturacion,
        fecha_fin=None,
        fianza=fianza,
        iva_porcentaje=iva_porcentaje,
        retencion_porcentaje=retencion_porcentaje,
        renta_inicial=renta_inicial,
        genera_factura=genera_factura,
        fecha_primera_revision=fecha_primera_revision,
        metodo_revision=metodo_revision,
    )

    if inmueble.tipo == "T":
        raise ContratoError(
            "No puede crearse un contrato para un inmueble subdividido."
        )

    if not inmueble.activo:
        raise ContratoError(
            "No puede crearse un contrato para un inmueble inactivo."
        )

    for contrato_existente in inmueble.contratos:
        if (
            contrato_existente.fecha_fin is None
            or contrato_existente.fecha_fin >= fecha_inicio
        ):
            raise ContratoError(
                "El inmueble ya tiene un contrato que se solapa "
                "con el nuevo contrato."
            )

    contrato = Contrato(
        inmueble=inmueble,
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=fecha_vencimiento,
        genera_factura=genera_factura,
        fecha_inicio_facturacion=fecha_inicio_facturacion,
        fianza=fianza,
        iva_porcentaje=iva_porcentaje,
        retencion_porcentaje=retencion_porcentaje,
        direccion_facturacion=direccion_facturacion,
        codigo_postal_facturacion=codigo_postal_facturacion,
        poblacion_facturacion=poblacion_facturacion,
        provincia_facturacion=provincia_facturacion,
        concepto_factura=concepto_factura,
    )

    for orden, inquilino in enumerate(titulares, start=1):
        contrato.titulares.append(
            ContratoInquilino(
                inquilino=inquilino,
                orden=orden,
            )
        )

    try:
        crear_renta_contrato(
            contrato=contrato,
            fecha_desde=fecha_inicio,
            importe=renta_inicial,
        )

        if fecha_primera_revision is not None:
            crear_revision_renta(
                contrato=contrato,
                fecha_prevista=fecha_primera_revision,
                metodo=metodo_revision,
            )

    except (
        RentaContratoError,
        RevisionRentaError,
    ) as exc:
        raise ContratoError(str(exc)) from exc

    return contrato


def crear_anexo_prorroga(
    contrato: Contrato,
    fecha: date,
    nueva_fecha_vencimiento: date,
    numero: int,
    descripcion: str | None = None,
) -> AnexoContrato:
    """Crea un anexo de prórroga y actualiza el vencimiento del contrato."""
    if fecha < contrato.fecha_inicio:
        raise ContratoError(
            "La fecha del anexo no puede ser anterior al inicio del contrato."
        )

    if nueva_fecha_vencimiento <= contrato.fecha_vencimiento:
        raise ContratoError(
            "La nueva fecha de vencimiento debe ser posterior "
            "al vencimiento actual."
        )

    _validar_numero_anexo(contrato, numero)

    anexo = AnexoContrato(
        contrato=contrato,
        numero=numero,
        fecha=fecha,
        tipo="PRORROGA",
        nueva_fecha_vencimiento=nueva_fecha_vencimiento,
        descripcion=descripcion,
    )

    contrato.fecha_vencimiento = nueva_fecha_vencimiento

    return anexo


def crear_anexo_renta_permanente(
    contrato: Contrato,
    fecha: date,
    fecha_desde: date,
    importe: int,
    numero: int,
    descripcion: str | None = None,
) -> tuple[AnexoContrato, RentaContrato]:
    """Crea un anexo que establece una nueva renta permanente."""
    if fecha < contrato.fecha_inicio:
        raise ContratoError(
            "La fecha del anexo no puede ser anterior al inicio del contrato."
        )

    _validar_numero_anexo(contrato, numero)

    anexo = AnexoContrato(
        contrato=contrato,
        numero=numero,
        fecha=fecha,
        tipo="CAMBIO_RENTA",
        descripcion=descripcion,
    )

    try:
        renta = crear_renta_contrato(
            contrato=contrato,
            fecha_desde=fecha_desde,
            importe=importe,
        )
    except RentaContratoError as exc:
        raise ContratoError(str(exc)) from exc

    renta.anexo = anexo

    return anexo, renta


def crear_anexo_renta_temporal(
    contrato: Contrato,
    fecha: date,
    fecha_desde: date,
    fecha_hasta: date,
    tipo: str,
    valor: int,
    numero: int,
    descripcion: str | None = None,
) -> tuple[AnexoContrato, AjusteRenta]:
    """Crea un anexo que establece una modificación temporal de la renta."""
    if fecha < contrato.fecha_inicio:
        raise ContratoError(
            "La fecha del anexo no puede ser anterior al inicio del contrato."
        )

    _validar_numero_anexo(contrato, numero)

    anexo = AnexoContrato(
        contrato=contrato,
        numero=numero,
        fecha=fecha,
        tipo="CAMBIO_RENTA",
        descripcion=descripcion,
    )

    try:
        ajuste = crear_ajuste_renta(
            contrato=contrato,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            tipo=tipo,
            valor=valor,
        )
    except AjusteRentaError as exc:
        raise ContratoError(str(exc)) from exc

    ajuste.anexo = anexo

    return anexo, ajuste


def crear_anexo_carencia(
    contrato: Contrato,
    fecha: date,
    fecha_desde: date,
    fecha_hasta: date,
    numero: int,
    descripcion: str | None = None,
) -> AnexoContrato:
    """Crea un anexo que establece un período temporal de carencia."""

    if fecha < contrato.fecha_inicio:
        raise ContratoError(
            "La fecha del anexo no puede ser anterior al inicio del contrato."
        )

    if fecha_desde.day != 1:
        raise ContratoError(
            "La carencia debe comenzar el primer día del mes."
        )

    if not _es_ultimo_dia_del_mes(fecha_hasta):
        raise ContratoError(
            "La carencia debe terminar el último día del mes."
        )

    if fecha_hasta < fecha_desde:
        raise ContratoError(
            "La fecha final de la carencia no puede ser anterior "
            "a la fecha inicial."
        )

    if fecha_desde < contrato.fecha_inicio:
        raise ContratoError(
            "La carencia no puede comenzar antes del inicio del contrato."
        )

    for anexo in contrato.anexos:
        if anexo.tipo != "CARENCIA":
            continue

        if (
            anexo.fecha_desde is None
            or anexo.fecha_hasta is None
        ):
            continue

        hay_solapamiento = (
            fecha_desde <= anexo.fecha_hasta
            and fecha_hasta >= anexo.fecha_desde
        )

        if hay_solapamiento:
            raise ContratoError(
                "La carencia se solapa con otro período de carencia."
            )

    _validar_numero_anexo(contrato, numero)

    return AnexoContrato(
        contrato=contrato,
        numero=numero,
        fecha=fecha,
        tipo="CARENCIA",
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        descripcion=descripcion,
    )


def carencia_vigente(
    contrato: Contrato,
    periodo: date,
) -> AnexoContrato | None:
    """Devuelve la carencia contractual aplicable al período."""

    for anexo in contrato.anexos:
        if anexo.tipo != "CARENCIA":
            continue

        if (
            anexo.fecha_desde is None
            or anexo.fecha_hasta is None
        ):
            continue

        if (
            anexo.fecha_desde
            <= periodo
            <= anexo.fecha_hasta
        ):
            return anexo

    return None


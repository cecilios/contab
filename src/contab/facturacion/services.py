"""Implementa la lógica de negocio relacionada con la facturación."""

from datetime import date
from dataclasses import dataclass

from contab.calculos import redondear_division
from contab.config import CategoriaContable
from contab.contabilidad.services import crear_apunte_contable
from contab.conciliacion.services import crear_movimiento_desde_apunte
from contab.models import (
    ApunteContable,
    Contrato,
    Factura,
    FacturaLinea,
    MovimientoPrevisto,
    RevisionRenta,
)
from contab.contratos.services import (
    renta_facturable,
)


class CalculoFacturaError(Exception):
    """Indica que no puede obtenerse un cálculo válido de factura."""

class FacturacionError(Exception):
    """Indica que no puede generarse una factura válida."""



@dataclass(frozen=True)
class CalculoFactura:
    """Contiene los importes resultantes del cálculo de una factura."""

    base: int
    iva_importe: int
    retencion_importe: int
    total: int

@dataclass(frozen=True)
class RepercusionGasto:
    """Describe un gasto que debe repercutirse como línea de factura."""

    concepto: str
    importe: int

@dataclass(frozen=True)
class FacturaPreparada:
    """Datos calculados de una factura pendiente de emisión."""

    contrato: Contrato
    inmueble: object
    destinatario_nombre: str
    destinatario_nif: str
    direccion_facturacion: str
    codigo_postal_facturacion: str | None
    poblacion_facturacion: str
    provincia_facturacion: str
    base: int
    iva_importe: int
    retencion_importe: int
    total: int
    factura: Factura | None
    numero_factura: str

@dataclass(frozen=True)
class IngresoPreparado:
    """Datos calculados de un ingreso que no genera factura."""

    contrato: Contrato
    inmueble: object
    importe: int


@dataclass(frozen=True)
class PreparacionPeriodo:
    """Datos preparados para la facturación de un período."""

    periodo: date
    fecha_emision: date
    locales: tuple[FacturaPreparada, ...]
    otros: tuple[IngresoPreparado, ...]



def _ultimo_dia_mes(periodo: date) -> date:
    """Devuelve el último día del mes de un período."""

    if periodo.month == 12:
        siguiente_mes = date(periodo.year + 1, 1, 1)
    else:
        siguiente_mes = date(
            periodo.year,
            periodo.month + 1,
            1,
        )

    return date.fromordinal(
        siguiente_mes.toordinal() - 1
    )


def siguiente_numero_factura(
    contrato: Contrato,
    anio: int,
) -> tuple[int, str]:
    """Calcula la siguiente secuencia y número de factura del inmueble."""
    inmueble = contrato.inmueble

    secuencias = [
        factura.numero_secuencia
        for contrato_inmueble in inmueble.contratos
        for factura in contrato_inmueble.facturas
        if factura.anio == anio
    ]

    secuencia = max(secuencias, default=0) + 1

    numero = (
        f"{secuencia:02d}/"
        f"{anio}"
        f"{inmueble.codigo_facturacion}"
    )

    return secuencia, numero


def calcular_importes_factura(
    lineas: list[FacturaLinea],
    iva_porcentaje: int,
    retencion_porcentaje: int,
) -> CalculoFactura:
    """Calcula base, IVA, retención y total a partir de las líneas."""
    if iva_porcentaje < 0:
        raise CalculoFacturaError(
            "El porcentaje de IVA no puede ser negativo."
        )

    if retencion_porcentaje < 0:
        raise CalculoFacturaError(
            "El porcentaje de retención no puede ser negativo."
        )

    base = sum(linea.importe for linea in lineas)

    if base < 0:
        raise CalculoFacturaError(
            "Las líneas de factura no pueden producir una base negativa."
        )

    iva_importe = redondear_division(
        base * iva_porcentaje,
        10000,
    )

    retencion_importe = redondear_division(
        base * retencion_porcentaje,
        10000,
    )

    total = base + iva_importe - retencion_importe

    if total < 0:
        raise CalculoFacturaError(
            "El cálculo produce un total de factura negativo."
        )

    return CalculoFactura(
        base=base,
        iva_importe=iva_importe,
        retencion_importe=retencion_importe,
        total=total,
    )


def componer_destinatario(
    contrato: Contrato,
) -> tuple[str, str]:
    """Compone nombre y NIF de los titulares de un contrato."""

    titulares = sorted(
        contrato.titulares,
        key=lambda titular: titular.orden,
    )

    if not titulares:
        raise FacturacionError(
            "El contrato debe tener al menos un titular."
        )

    nombre = " / ".join(
        titular.inquilino.nombre
        for titular in titulares
    )
    nif = " / ".join(
        titular.inquilino.nif
        for titular in titulares
    )

    return nombre, nif


def crear_factura(
    contrato: Contrato,
    periodo: date,
    fecha_emision: date,
    ruta_pdf: str = "",
    revision_renta: RevisionRenta | None = None,
    diferencia_revision: int = 0,
    aviso_revision: str | None = None,
    repercusiones: list[RepercusionGasto] | None = None,
) -> Factura:
    """Prepara una factura ordinaria mensual sin persistirla."""
    if periodo.day != 1:
        raise FacturacionError(
            "El periodo facturado debe corresponder al día 1 del mes."
        )

    if periodo < contrato.fecha_inicio_facturacion:
        raise FacturacionError(
            "No puede facturarse un periodo anterior al inicio de facturación."
        )

    secuencia, numero = siguiente_numero_factura(
        contrato,
        periodo.year,
    )

    importe_renta = renta_facturable(
        contrato,
        periodo,
    )

    linea_renta = FacturaLinea(
        orden=1,
        tipo="RENTA",
        concepto=contrato.concepto_factura,
        importe=importe_renta,
    )
    lineas = [linea_renta]

    if diferencia_revision != 0:
        if revision_renta is None:
            raise FacturacionError(
                "Una diferencia de revisión debe estar vinculada a una revisión."
            )

        lineas.append(
            FacturaLinea(
                orden=2,
                tipo="DIFERENCIA_REVISION",
                concepto="Diferencia de revisión de renta",
                importe=diferencia_revision,
            )
        )

    if repercusiones:
        for repercusion in repercusiones:
            if repercusion.importe < 0:
                raise FacturacionError(
                    "El importe de un gasto repercutido no puede ser negativo."
                )

            if not repercusion.concepto.strip():
                raise FacturacionError(
                    "Todo gasto repercutido debe tener un concepto."
                )

            lineas.append(
                FacturaLinea(
                    orden=len(lineas) + 1,
                    tipo="REPERCUSION_GASTO",
                    concepto=repercusion.concepto,
                    importe=repercusion.importe,
                )
            )

    calculo = calcular_importes_factura(
        lineas=lineas,
        iva_porcentaje=contrato.iva_porcentaje,
        retencion_porcentaje=contrato.retencion_porcentaje,
    )

    factura = Factura(
        contrato=contrato,
        numero_secuencia=secuencia,
        anio=periodo.year,
        numero_factura=numero,
        fecha_emision=fecha_emision,
        periodo=periodo,
        base=calculo.base,
        iva_porcentaje=contrato.iva_porcentaje,
        iva_importe=calculo.iva_importe,
        retencion_porcentaje=contrato.retencion_porcentaje,
        retencion_importe=calculo.retencion_importe,
        total=calculo.total,
        ruta_pdf=ruta_pdf,
        revision_renta=revision_renta,
        aviso_revision=aviso_revision,
        estado="EMITIDA",
    )

    factura.lineas.extend(lineas)

    return factura


def preparar_registro_contable_factura(
    *,
    factura: Factura,
    categorias: dict[str, CategoriaContable],
) -> tuple[ApunteContable, MovimientoPrevisto]:
    """Prepara el apunte y movimiento previsto de una factura."""

    contrato = factura.contrato

    tercero_nombre, tercero_nif = componer_destinatario(contrato)

    periodo_desde = factura.periodo
    periodo_hasta = _ultimo_dia_mes(periodo_desde)

    apunte = crear_apunte_contable(
        inmueble=contrato.inmueble,
        categorias=categorias,
        fecha=factura.fecha_emision,
        naturaleza="INGRESO",
        categoria="ING_ALQUILERES",
        concepto=contrato.concepto_factura,
        base=factura.base,
        iva_importe=factura.iva_importe,
        retencion_importe=factura.retencion_importe,
        tercero_nombre=tercero_nombre,
        tercero_nif=tercero_nif,
        referencia_documento=factura.numero_factura,
        periodo_desde=periodo_desde,
        periodo_hasta=periodo_hasta,
    )

    movimiento = crear_movimiento_desde_apunte(
        apunte=apunte,
        contrato=contrato,
        fecha_prevista_desde=periodo_desde,
        fecha_prevista_hasta=periodo_hasta,
    )

    return apunte, movimiento


def preparar_periodo_facturacion(
    *,
    contratos: list[Contrato],
    periodo: date,
    fecha_emision: date,
) -> PreparacionPeriodo:
    """Prepara los ingresos de alquiler correspondientes a un período."""

    if periodo.day != 1:
        raise FacturacionError(
            "El periodo debe corresponder al día 1 del mes."
        )

    ultimo_dia = _ultimo_dia_mes(periodo)

    locales = []
    otros = []

    for contrato in contratos:
        if contrato.fecha_inicio > ultimo_dia:
            continue

        if (
            contrato.fecha_fin is not None
            and contrato.fecha_fin < periodo
        ):
            continue

        fecha_renta = max(
            periodo,
            contrato.fecha_inicio,
        )

        if contrato.genera_factura:
            if periodo < contrato.fecha_inicio_facturacion:
                continue

            factura = next(
                (
                    factura
                    for factura in contrato.facturas
                    if factura.periodo == periodo
                ),
                None,
            )

            if factura is None:
                _, numero_factura = siguiente_numero_factura(contrato, periodo.year)
                importe_renta = renta_facturable(
                    contrato,
                    fecha_renta,
                )

                linea = FacturaLinea(
                    orden=1,
                    tipo="RENTA",
                    concepto=contrato.concepto_factura,
                    importe=importe_renta,
                )

                calculo = calcular_importes_factura(
                    lineas=[linea],
                    iva_porcentaje=contrato.iva_porcentaje,
                    retencion_porcentaje=contrato.retencion_porcentaje,
                )
                base = calculo.base
                iva_importe = calculo.iva_importe
                retencion_importe = calculo.retencion_importe
                total = calculo.total
            else:
                numero_factura = factura.numero_factura
                base = factura.base
                iva_importe = factura.iva_importe
                retencion_importe = factura.retencion_importe
                total = factura.total

            destinatario_nombre, destinatario_nif = componer_destinatario(contrato)

            locales.append(
                FacturaPreparada(
                    contrato=contrato,
                    inmueble=contrato.inmueble,
                    factura=factura,
                    destinatario_nombre=destinatario_nombre,
                    destinatario_nif=destinatario_nif,
                    direccion_facturacion=contrato.direccion_facturacion,
                    codigo_postal_facturacion=contrato.codigo_postal_facturacion,
                    poblacion_facturacion=contrato.poblacion_facturacion,
                    provincia_facturacion=contrato.provincia_facturacion,
                    base=base,
                    iva_importe=iva_importe,
                    retencion_importe=retencion_importe,
                    total=total,
                    numero_factura=numero_factura,
                )
            )
        else:
            otros.append(
                IngresoPreparado(
                    contrato=contrato,
                    inmueble=contrato.inmueble,
                    importe=renta_facturable(
                        contrato,
                        fecha_renta,
                    ),
                )
            )

    return PreparacionPeriodo(
        periodo=periodo,
        fecha_emision=fecha_emision,
        locales=tuple(locales),
        otros=tuple(otros),
    )


def emitir_factura(
    *,
    contrato: Contrato,
    periodo: date,
    fecha_emision: date,
    categorias: dict[str, CategoriaContable],
) -> tuple[Factura, ApunteContable, MovimientoPrevisto]:
    """Prepara la emisión completa de una factura sin persistirla."""

    if any(
        factura.periodo == periodo
        for factura in contrato.facturas
    ):
        raise FacturacionError(
            "Ya existe una factura para este contrato y período."
        )

    factura = crear_factura(
        contrato=contrato,
        periodo=periodo,
        fecha_emision=fecha_emision,
    )

    apunte, movimiento = preparar_registro_contable_factura(
        factura=factura,
        categorias=categorias,
    )

    return factura, apunte, movimiento



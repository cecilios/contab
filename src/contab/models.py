"""Define los modelos ORM de la base de datos de Contab."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from datetime import date

from contab.database import Base


class Inmueble(Base):
    """Representa un inmueble o unidad arrendable gestionada por Contab."""

    __tablename__ = "inmueble"

    __table_args__ = (
        CheckConstraint(
            "participacion > 0 AND participacion <= 10000",
            name="ck_inmueble_participacion",
        ),
        CheckConstraint(
            "tipo IN ('T', 'P', 'L', 'G')",
            name="ck_inmueble_tipo",
        ),
        CheckConstraint(
            "tipo != 'T' "
            "OR ("
            "inmueble_padre_id IS NULL "
            "AND participacion = 10000"
            ")",
            name="ck_inmueble_total",
        ),
        CheckConstraint(
            "inmueble_padre_id IS NULL "
            "OR inmueble_padre_id != id",
            name="ck_inmueble_no_es_su_padre",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    inmueble_padre_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "inmueble.id",
            name="fk_inmueble_padre",
            ondelete="RESTRICT",
        ),
    )

    tipo: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    referencia: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    codigo_facturacion: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )

    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    direccion: Mapped[str] = mapped_column(Text, nullable=False)
    codigo_postal: Mapped[str | None] = mapped_column(Text)
    poblacion: Mapped[str] = mapped_column(Text, nullable=False)
    provincia: Mapped[str] = mapped_column(Text, nullable=False)

    ref_catastral: Mapped[str | None] = mapped_column(Text)
    seguro: Mapped[str | None] = mapped_column(Text)

    ruta_documentos: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    participacion: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10000,
    )

    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    notas: Mapped[str | None] = mapped_column(Text)

    inmueble_padre: Mapped["Inmueble | None"] = relationship(
        back_populates="locales",
        remote_side=[id],
        foreign_keys=[inmueble_padre_id],
    )

    locales: Mapped[list["Inmueble"]] = relationship(
        back_populates="inmueble_padre",
        foreign_keys=[inmueble_padre_id],
        passive_deletes="all",
    )

    contratos: Mapped[list["Contrato"]] = relationship(
        back_populates="inmueble",
        passive_deletes="all",
    )
    
    apuntes_contables: Mapped[
        list["ApunteContable"]
    ] = relationship(
        back_populates="inmueble",
        passive_deletes="all",
    )

    movimientos_previstos: Mapped[
        list["MovimientoPrevisto"]
    ] = relationship(
        back_populates="inmueble",
        passive_deletes="all",
    )



class Inquilino(Base):
    """Representa una persona física o jurídica titular de contratos."""

    __tablename__ = "inquilino"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    nombre: Mapped[str] = mapped_column(Text, nullable=False)

    nif: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )

    direccion: Mapped[str | None] = mapped_column(Text)
    codigo_postal: Mapped[str | None] = mapped_column(Text)
    poblacion: Mapped[str | None] = mapped_column(Text)
    provincia: Mapped[str | None] = mapped_column(Text)

    email: Mapped[str | None] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(Text)

    notas: Mapped[str | None] = mapped_column(Text)

    contratos: Mapped[list["ContratoInquilino"]] = relationship(
        back_populates="inquilino",
        passive_deletes="all",
    )


class Contrato(Base):
    """Representa un contrato de alquiler asociado a un inmueble."""

    __tablename__ = "contrato"

    __table_args__ = (
        CheckConstraint(
            "fecha_vencimiento >= fecha_inicio",
            name="ck_contrato_fecha_vencimiento",
        ),
        CheckConstraint(
            "fecha_fin IS NULL OR fecha_fin >= fecha_inicio",
            name="ck_contrato_fecha_fin",
        ),
        CheckConstraint(
            "fecha_inicio_facturacion >= fecha_inicio",
            name="ck_contrato_fecha_inicio_facturacion",
        ),
        CheckConstraint(
            "fianza >= 0",
            name="ck_contrato_fianza",
        ),
        CheckConstraint(
            "iva_porcentaje >= 0",
            name="ck_contrato_iva",
        ),
        CheckConstraint(
            "retencion_porcentaje >= 0",
            name="ck_contrato_retencion",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    inmueble_id: Mapped[int] = mapped_column(
        ForeignKey("inmueble.id", ondelete="RESTRICT"),
        nullable=False,
    )

    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    genera_factura: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    fecha_inicio_facturacion: Mapped[date] = mapped_column(Date, nullable=False)

    fianza: Mapped[int] = mapped_column(Integer, nullable=False)

    iva_porcentaje: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    retencion_porcentaje: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    direccion_facturacion: Mapped[str] = mapped_column(Text, nullable=False)
    codigo_postal_facturacion: Mapped[str | None] = mapped_column(Text)
    poblacion_facturacion: Mapped[str] = mapped_column(Text, nullable=False)
    provincia_facturacion: Mapped[str] = mapped_column(Text, nullable=False)

    concepto_factura: Mapped[str] = mapped_column(Text, nullable=False)
    notas: Mapped[str | None] = mapped_column(Text)

    inmueble: Mapped["Inmueble"] = relationship(
        back_populates="contratos",
    )

    titulares: Mapped[list["ContratoInquilino"]] = relationship(
        back_populates="contrato",
        passive_deletes="all",
    )

    rentas: Mapped[list["RentaContrato"]] = relationship(
        back_populates="contrato",
        passive_deletes="all",
    )

    revisiones_renta: Mapped[list["RevisionRenta"]] = relationship(
        back_populates="contrato",
        passive_deletes="all",
    )

    ajustes_renta: Mapped[list["AjusteRenta"]] = relationship(
        back_populates="contrato",
        passive_deletes="all",
    )
    
    anexos: Mapped[list["AnexoContrato"]] = relationship(
        back_populates="contrato",
        passive_deletes="all",
    )

    facturas: Mapped[list["Factura"]] = relationship(
        back_populates="contrato",
        passive_deletes="all",
    )

    movimientos_previstos: Mapped[
        list["MovimientoPrevisto"]
    ] = relationship(
        back_populates="contrato",
        passive_deletes="all",
    )


class ContratoInquilino(Base):
    """Relaciona un contrato con uno de sus titulares y establece su orden."""

    __tablename__ = "contrato_inquilino"

    __table_args__ = (
        CheckConstraint(
            "orden > 0",
            name="ck_contrato_inquilino_orden",
        ),
        UniqueConstraint(
            "contrato_id",
            "orden",
            name="uq_contrato_inquilino_orden",
        ),
    )

    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contrato.id", ondelete="RESTRICT"),
        primary_key=True,
    )

    inquilino_id: Mapped[int] = mapped_column(
        ForeignKey("inquilino.id", ondelete="RESTRICT"),
        primary_key=True,
    )

    orden: Mapped[int] = mapped_column(Integer, nullable=False)

    contrato: Mapped["Contrato"] = relationship(
        back_populates="titulares",
    )

    inquilino: Mapped["Inquilino"] = relationship(
        back_populates="contratos",
    )


class AnexoContrato(Base):
    """Representa una modificación contractual formalizada mediante anexo."""

    __tablename__ = "anexo_contrato"

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('CAMBIO_RENTA', 'PRORROGA')",
            name="ck_anexo_contrato_tipo",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contrato.id", ondelete="RESTRICT"),
        nullable=False,
    )

    fecha: Mapped[date] = mapped_column(Date, nullable=False)

    tipo: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    nueva_fecha_vencimiento: Mapped[date | None] = mapped_column(Date)

    descripcion: Mapped[str | None] = mapped_column(Text)

    contrato: Mapped["Contrato"] = relationship(
        back_populates="anexos",
    )

    rentas: Mapped[list["RentaContrato"]] = relationship(
        back_populates="anexo",
        passive_deletes="all",
    )

    ajustes_renta: Mapped[list["AjusteRenta"]] = relationship(
        back_populates="anexo",
        passive_deletes="all",
    )


class RentaContrato(Base):
    """Representa una renta ordinaria aplicable a un contrato desde un mes."""

    __tablename__ = "renta_contrato"

    __table_args__ = (
        CheckConstraint(
            "importe >= 0",
            name="ck_renta_contrato_importe",
        ),
        UniqueConstraint(
            "contrato_id",
            "fecha_desde",
            name="uq_renta_contrato_fecha_desde",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contrato.id", ondelete="RESTRICT"),
        nullable=False,
    )

    anexo_id: Mapped[int | None] = mapped_column(
        ForeignKey("anexo_contrato.id", ondelete="RESTRICT"),
    )

    fecha_desde: Mapped[date] = mapped_column(Date, nullable=False)
    importe: Mapped[int] = mapped_column(Integer, nullable=False)
    notas: Mapped[str | None] = mapped_column(Text)

    contrato: Mapped["Contrato"] = relationship(
        back_populates="rentas",
    )

    anexo: Mapped["AnexoContrato | None"] = relationship(
        back_populates="rentas",
    )
    

class RevisionRenta(Base):
    """Representa una revisión prevista o resuelta de la renta de un contrato."""

    __tablename__ = "revision_renta"

    __table_args__ = (
        CheckConstraint(
            "estado IN ('PENDIENTE', 'APLICADA', 'NO_APLICADA')",
            name="ck_revision_renta_estado",
        ),
        UniqueConstraint(
            "contrato_id",
            "fecha_prevista",
            name="uq_revision_renta_fecha_prevista",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contrato.id", ondelete="RESTRICT"),
        nullable=False,
    )

    fecha_prevista: Mapped[date] = mapped_column(Date, nullable=False)
    metodo: Mapped[str] = mapped_column(Text, nullable=False)

    estado: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="PENDIENTE",
    )

    porcentaje_aplicado: Mapped[int | None] = mapped_column(Integer)
    fecha_resolucion: Mapped[date | None] = mapped_column(Date)

    notas: Mapped[str | None] = mapped_column(Text)

    contrato: Mapped["Contrato"] = relationship(
        back_populates="revisiones_renta",
    )

    facturas: Mapped[list["Factura"]] = relationship(
        back_populates="revision_renta",
        passive_deletes="all",
    )


class AjusteRenta(Base):
    """Representa una modificación temporal de la renta facturable."""

    __tablename__ = "ajuste_renta"

    __table_args__ = (
        CheckConstraint(
            "fecha_hasta >= fecha_desde",
            name="ck_ajuste_renta_fechas",
        ),
        CheckConstraint(
            "tipo IN ('REDUCCION_PORCENTUAL', 'REDUCCION_FIJA', 'IMPORTE_FIJO')",
            name="ck_ajuste_renta_tipo",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contrato.id", ondelete="RESTRICT"),
        nullable=False,
    )

    anexo_id: Mapped[int | None] = mapped_column(
        ForeignKey("anexo_contrato.id", ondelete="RESTRICT"),
    )

    fecha_desde: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_hasta: Mapped[date] = mapped_column(Date, nullable=False)

    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    valor: Mapped[int] = mapped_column(Integer, nullable=False)

    notas: Mapped[str | None] = mapped_column(Text)

    contrato: Mapped["Contrato"] = relationship(
        back_populates="ajustes_renta",
    )

    anexo: Mapped["AnexoContrato | None"] = relationship(
        back_populates="ajustes_renta",
    )


class Factura(Base):
    """Representa una factura emitida por un contrato de alquiler."""

    __tablename__ = "factura"

    __table_args__ = (
        CheckConstraint(
            "numero_secuencia > 0",
            name="ck_factura_numero_secuencia",
        ),
        CheckConstraint(
            "anio > 0",
            name="ck_factura_anio",
        ),
        CheckConstraint(
            "base >= 0",
            name="ck_factura_base",
        ),
        CheckConstraint(
            "iva_porcentaje >= 0",
            name="ck_factura_iva_porcentaje",
        ),
        CheckConstraint(
            "iva_importe >= 0",
            name="ck_factura_iva_importe",
        ),
        CheckConstraint(
            "retencion_porcentaje >= 0",
            name="ck_factura_retencion_porcentaje",
        ),
        CheckConstraint(
            "retencion_importe >= 0",
            name="ck_factura_retencion_importe",
        ),
        CheckConstraint(
            "total >= 0",
            name="ck_factura_total",
        ),
        CheckConstraint(
            "estado IN ('EMITIDA', 'ANULADA')",
            name="ck_factura_estado",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contrato.id", ondelete="RESTRICT"),
        nullable=False,
    )

    numero_secuencia: Mapped[int] = mapped_column(Integer, nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)

    numero_factura: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )

    fecha_emision: Mapped[date] = mapped_column(Date, nullable=False)
    periodo: Mapped[date] = mapped_column(Date, nullable=False)

    base: Mapped[int] = mapped_column(Integer, nullable=False)

    iva_porcentaje: Mapped[int] = mapped_column(Integer, nullable=False)
    iva_importe: Mapped[int] = mapped_column(Integer, nullable=False)

    retencion_porcentaje: Mapped[int] = mapped_column(Integer, nullable=False)
    retencion_importe: Mapped[int] = mapped_column(Integer, nullable=False)

    total: Mapped[int] = mapped_column(Integer, nullable=False)

    revision_renta_id: Mapped[int | None] = mapped_column(
        ForeignKey("revision_renta.id", ondelete="RESTRICT"),
    )

    aviso_revision: Mapped[str | None] = mapped_column(Text)

    estado: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="EMITIDA",
    )

    ruta_pdf: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    notas: Mapped[str | None] = mapped_column(Text)

    contrato: Mapped["Contrato"] = relationship(
        back_populates="facturas",
    )

    revision_renta: Mapped["RevisionRenta | None"] = relationship(
        back_populates="facturas",
    )

    lineas: Mapped[list["FacturaLinea"]] = relationship(
        back_populates="factura",
        passive_deletes="all",
    )


class FacturaLinea(Base):
    """Representa un concepto económico incluido en una factura."""

    __tablename__ = "factura_linea"

    __table_args__ = (
        CheckConstraint(
            "tipo IN ("
            "'RENTA', "
            "'DIFERENCIA_REVISION', "
            "'REPERCUSION_GASTO', "
            "'OTRO'"
            ")",
            name="ck_factura_linea_tipo",
        ),
        UniqueConstraint(
            "factura_id",
            "orden",
            name="uq_factura_linea_orden",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    factura_id: Mapped[int] = mapped_column(
        ForeignKey("factura.id", ondelete="RESTRICT"),
        nullable=False,
    )

    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    concepto: Mapped[str] = mapped_column(Text, nullable=False)
    importe: Mapped[int] = mapped_column(Integer, nullable=False)

    factura: Mapped["Factura"] = relationship(
        back_populates="lineas",
    )


class ApunteContable(Base):
    """Representa un ingreso o gasto atribuido a un inmueble."""

    __tablename__ = "apunte_contable"

    __table_args__ = (
        CheckConstraint(
            "naturaleza IN ('INGRESO', 'GASTO')",
            name="ck_apunte_contable_naturaleza",
        ),
        CheckConstraint(
            "base >= 0",
            name="ck_apunte_contable_base",
        ),
        CheckConstraint(
            "iva_importe >= 0",
            name="ck_apunte_contable_iva",
        ),
        CheckConstraint(
            "retencion_importe >= 0",
            name="ck_apunte_contable_retencion",
        ),
        CheckConstraint(
            "total >= 0",
            name="ck_apunte_contable_total",
        ),
        CheckConstraint(
            """
            (
                periodo_desde IS NULL
                AND periodo_hasta IS NULL
            )
            OR
            (
                periodo_desde IS NOT NULL
                AND periodo_hasta IS NOT NULL
            )
            """,
            name="ck_apunte_contable_periodo_completo",
        ),
        CheckConstraint(
            """
            periodo_desde IS NULL
            OR periodo_hasta >= periodo_desde
            """,
            name="ck_apunte_contable_periodo_orden",
        ),
        CheckConstraint(
            """
            tratamiento IN (
                'CONTABILIZAR',
                'REPERCUTIR',
                'FACTURAR'
            )
            """,
            name="ck_apunte_contable_tratamiento",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    inmueble_id: Mapped[int] = mapped_column(
        ForeignKey("inmueble.id", ondelete="RESTRICT"),
        nullable=False,
    )

    fecha: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    naturaleza: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    categoria: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    subcategoria: Mapped[str | None] = mapped_column(Text)

    concepto: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    periodo_desde: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    periodo_hasta: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    tratamiento: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="CONTABILIZAR",
    )

    nombre_documento: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    base: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    iva_importe: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    retencion_importe: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    total: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    tercero_nombre: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    tercero_nif: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    referencia_documento: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    ruta_documento: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    notas: Mapped[str | None] = mapped_column(Text)

    inmueble: Mapped["Inmueble"] = relationship(
        back_populates="apuntes_contables",
    )

    movimientos_previstos: Mapped[
        list["MovimientoPrevisto"]
    ] = relationship(
        back_populates="apunte",
        passive_deletes="all",
    )


class MovimientoPrevisto(Base):
    """Representa un cobro o pago esperado para conciliación."""

    __tablename__ = "movimiento_previsto"

    __table_args__ = (
        CheckConstraint(
            "naturaleza IN ('INGRESO', 'GASTO')",
            name="ck_movimiento_previsto_naturaleza",
        ),
        CheckConstraint(
            "importe_esperado >= 0",
            name="ck_movimiento_previsto_importe",
        ),
        CheckConstraint(
            "estado IN ('PENDIENTE', 'CONCILIADO')",
            name="ck_movimiento_previsto_estado",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    inmueble_id: Mapped[int] = mapped_column(
        ForeignKey("inmueble.id", ondelete="RESTRICT"),
        nullable=False,
    )

    contrato_id: Mapped[int | None] = mapped_column(
        ForeignKey("contrato.id", ondelete="RESTRICT"),
    )

    apunte_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "apunte_contable.id",
            ondelete="RESTRICT",
        ),
    )

    fecha_prevista: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    naturaleza: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    concepto: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    importe_esperado: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    contraparte: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    estado: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="PENDIENTE",
    )

    notas: Mapped[str | None] = mapped_column(Text)

    inmueble: Mapped["Inmueble"] = relationship(
        back_populates="movimientos_previstos",
    )

    contrato: Mapped["Contrato | None"] = relationship(
        back_populates="movimientos_previstos",
    )

    apunte: Mapped["ApunteContable | None"] = relationship(
        back_populates="movimientos_previstos",
    )



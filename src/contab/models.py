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
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

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

    contratos: Mapped[list["Contrato"]] = relationship(
        back_populates="inmueble",
    )


class Inquilino(Base):
    """Representa una persona física o jurídica titular de contratos."""

    __tablename__ = "inquilino"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    nif: Mapped[str] = mapped_column(Text, nullable=False)

    direccion: Mapped[str | None] = mapped_column(Text)
    codigo_postal: Mapped[str | None] = mapped_column(Text)
    poblacion: Mapped[str | None] = mapped_column(Text)
    provincia: Mapped[str | None] = mapped_column(Text)

    email: Mapped[str | None] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(Text)

    notas: Mapped[str | None] = mapped_column(Text)

    contratos: Mapped[list["ContratoInquilino"]] = relationship(
        back_populates="inquilino",
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
        ForeignKey("inmueble.id"),
        nullable=False,
    )

    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
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
    )

    rentas: Mapped[list["RentaContrato"]] = relationship(
        back_populates="contrato",
    )

    revisiones_renta: Mapped[list["RevisionRenta"]] = relationship(
        back_populates="contrato",
    )

    ajustes_renta: Mapped[list["AjusteRenta"]] = relationship(
        back_populates="contrato",
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
        ForeignKey("contrato.id"),
        primary_key=True,
    )
    inquilino_id: Mapped[int] = mapped_column(
        ForeignKey("inquilino.id"),
        primary_key=True,
    )

    orden: Mapped[int] = mapped_column(Integer, nullable=False)

    contrato: Mapped["Contrato"] = relationship(
        back_populates="titulares",
    )
    inquilino: Mapped["Inquilino"] = relationship(
        back_populates="contratos",
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
        ForeignKey("contrato.id"),
        nullable=False,
    )

    fecha_desde: Mapped[date] = mapped_column(Date, nullable=False)
    importe: Mapped[int] = mapped_column(Integer, nullable=False)
    notas: Mapped[str | None] = mapped_column(Text)

    contrato: Mapped["Contrato"] = relationship(
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
        ForeignKey("contrato.id"),
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
        ForeignKey("contrato.id"),
        nullable=False,
    )

    fecha_desde: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_hasta: Mapped[date] = mapped_column(Date, nullable=False)

    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    valor: Mapped[int] = mapped_column(Integer, nullable=False)

    notas: Mapped[str | None] = mapped_column(Text)

    contrato: Mapped["Contrato"] = relationship(
        back_populates="ajustes_renta",
    )



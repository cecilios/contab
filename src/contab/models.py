"""Define los modelos ORM de la base de datos de Contab."""

from sqlalchemy import Boolean, CheckConstraint, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

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

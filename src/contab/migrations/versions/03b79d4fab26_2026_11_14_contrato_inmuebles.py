"""2026-11-14 contrato inmuebles

Revision ID: 03b79d4fab26
Revises: de94e2b6abe8
Create Date: 2026-11-14 10:18:59.149128
"""

from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "03b79d4fab26"
down_revision: Union[str, Sequence[str], None] = "de94e2b6abe8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Añade los datos de propiedad y fiscales."""

    op.create_table(
        "datos_fiscales_inmueble",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "inmueble_id",
            sa.Integer(),
            sa.ForeignKey("inmueble.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ejercicio", sa.Integer(), nullable=False),
        sa.Column("valor_catastral", sa.Integer(), nullable=False),
        sa.Column("valor_suelo", sa.Integer(), nullable=False),
        sa.Column("valor_construccion", sa.Integer(), nullable=False),
        sa.Column("amortizacion_aplicada", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "ejercicio BETWEEN 1 AND 9999",
            name="ck_datos_fiscales_inmueble_ejercicio",
        ),
        sa.CheckConstraint(
            "valor_catastral >= 0 "
            "AND valor_suelo >= 0 "
            "AND valor_construccion >= 0 "
            "AND amortizacion_aplicada >= 0",
            name="ck_datos_fiscales_inmueble_importes",
        ),
        sa.UniqueConstraint(
            "inmueble_id",
            "ejercicio",
            name="uq_datos_fiscales_inmueble_ejercicio",
        ),
    )

    # Los anexos históricos reciben el número 1.
    # No dejamos ningún valor por defecto en la BD.
    op.add_column(
        "anexo_contrato",
        sa.Column("numero", sa.Integer(), nullable=True),
    )

    op.execute(
        "UPDATE anexo_contrato SET numero = 1"
    )

    with op.batch_alter_table("anexo_contrato") as batch:
        batch.alter_column(
            "numero",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch.create_check_constraint(
            "ck_anexo_contrato_numero",
            "numero > 0",
        )
        batch.create_unique_constraint(
            "uq_anexo_contrato_numero",
            ["contrato_id", "numero"],
        )

    # La cadena vacía es un valor válido para destino.
    op.add_column(
        "contrato",
        sa.Column(
            "destino",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )

    # Datos de propiedad: nullable porque los locales
    # hijos no tienen datos fiscales propios.
    op.add_column(
        "inmueble",
        sa.Column(
            "porcentaje_titular",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "inmueble",
        sa.Column(
            "tipo_derecho",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "inmueble",
        sa.Column(
            "porcentaje_derecho",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "inmueble",
        sa.Column(
            "fecha_adquisicion",
            sa.Date(),
            nullable=True,
        ),
    )
    op.add_column(
        "inmueble",
        sa.Column(
            "tipo_adquisicion",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "inmueble",
        sa.Column(
            "importe_adquisicion",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "inmueble",
        sa.Column(
            "gastos_adquisicion",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "inmueble",
        sa.Column(
            "fecha_transmision",
            sa.Date(),
            nullable=True,
        ),
    )

    # Solamente los inmuebles independientes y T
    # reciben datos iniciales de propiedad.
    # Los locales hijos permanecen a NULL.
    op.get_bind().execute(
        sa.text(
            """
            UPDATE inmueble
            SET porcentaje_titular = 10000,
                tipo_derecho = 'PLENA_PROPIEDAD',
                porcentaje_derecho = 10000,
                fecha_adquisicion = :fecha,
                tipo_adquisicion = 'ONEROSA',
                importe_adquisicion = 0,
                gastos_adquisicion = 0
            WHERE inmueble_padre_id IS NULL
            """
        ),
        {"fecha": date.today().isoformat()},
    )

    # Las restricciones se crean después de
    # inicializar los registros preexistentes.
    with op.batch_alter_table("inmueble") as batch:
        batch.create_check_constraint(
            "ck_inmueble_datos_propiedad",
            "("
            "inmueble_padre_id IS NULL "
            "AND porcentaje_titular IS NOT NULL "
            "AND porcentaje_titular BETWEEN 0 AND 10000 "
            "AND tipo_derecho IS NOT NULL "
            "AND tipo_derecho IN ('PLENA_PROPIEDAD', 'USUFRUCTO') "
            "AND porcentaje_derecho IS NOT NULL "
            "AND porcentaje_derecho BETWEEN 0 AND 10000 "
            "AND fecha_adquisicion IS NOT NULL "
            "AND tipo_adquisicion IS NOT NULL "
            "AND tipo_adquisicion IN ('ONEROSA', 'LUCRATIVA') "
            "AND importe_adquisicion IS NOT NULL "
            "AND importe_adquisicion >= 0 "
            "AND gastos_adquisicion IS NOT NULL "
            "AND gastos_adquisicion >= 0"
            ") OR ("
            "inmueble_padre_id IS NOT NULL "
            "AND porcentaje_titular IS NULL "
            "AND tipo_derecho IS NULL "
            "AND porcentaje_derecho IS NULL "
            "AND fecha_adquisicion IS NULL "
            "AND tipo_adquisicion IS NULL "
            "AND importe_adquisicion IS NULL "
            "AND gastos_adquisicion IS NULL "
            "AND fecha_transmision IS NULL"
            ")",
        )

        batch.create_check_constraint(
            "ck_inmueble_fechas_propiedad",
            "fecha_transmision IS NULL "
            "OR fecha_transmision >= fecha_adquisicion",
        )


def downgrade() -> None:
    """Revierte la ampliación fiscal del esquema."""

    with op.batch_alter_table("inmueble") as batch:
        batch.drop_constraint(
            "ck_inmueble_fechas_propiedad",
            type_="check",
        )
        batch.drop_constraint(
            "ck_inmueble_datos_propiedad",
            type_="check",
        )
        batch.drop_column("fecha_transmision")
        batch.drop_column("gastos_adquisicion")
        batch.drop_column("importe_adquisicion")
        batch.drop_column("tipo_adquisicion")
        batch.drop_column("fecha_adquisicion")
        batch.drop_column("porcentaje_derecho")
        batch.drop_column("tipo_derecho")
        batch.drop_column("porcentaje_titular")

    op.drop_column("contrato", "destino")

    with op.batch_alter_table("anexo_contrato") as batch:
        batch.drop_constraint(
            "uq_anexo_contrato_numero",
            type_="unique",
        )
        batch.drop_constraint(
            "ck_anexo_contrato_numero",
            type_="check",
        )
        batch.drop_column("numero")

    op.drop_table("datos_fiscales_inmueble")

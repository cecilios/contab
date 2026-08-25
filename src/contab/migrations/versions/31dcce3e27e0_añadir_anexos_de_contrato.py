"""añadir anexos de contrato

Revision ID: 31dcce3e27e0
Revises: e6d9f81c754e
Create Date: 2026-08-24 10:47:36.306636

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31dcce3e27e0'
down_revision: Union[str, Sequence[str], None] = 'e6d9f81c754e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Añade soporte para anexos de contrato."""
    op.create_table(
        "anexo_contrato",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contrato_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column(
            "nueva_fecha_vencimiento",
            sa.Date(),
            nullable=True,
        ),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('CAMBIO_RENTA', 'PRORROGA')",
            name="ck_anexo_contrato_tipo",
        ),
        sa.ForeignKeyConstraint(
            ["contrato_id"],
            ["contrato.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("ajuste_renta") as batch_op:
        batch_op.add_column(
            sa.Column(
                "anexo_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_ajuste_renta_anexo_id",
            "anexo_contrato",
            ["anexo_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("renta_contrato") as batch_op:
        batch_op.add_column(
            sa.Column(
                "anexo_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_renta_contrato_anexo_id",
            "anexo_contrato",
            ["anexo_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """Elimina el soporte para anexos de contrato."""
    with op.batch_alter_table("renta_contrato") as batch_op:
        batch_op.drop_constraint(
            "fk_renta_contrato_anexo_id",
            type_="foreignkey",
        )
        batch_op.drop_column("anexo_id")

    with op.batch_alter_table("ajuste_renta") as batch_op:
        batch_op.drop_constraint(
            "fk_ajuste_renta_anexo_id",
            type_="foreignkey",
        )
        batch_op.drop_column("anexo_id")

    op.drop_table("anexo_contrato")


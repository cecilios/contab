"""2026-10-15 gastos facturables

Revision ID: eef2237d7d54
Revises: b391f7694ec0
Create Date: 2026-10-15 13:39:02.968376

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = 'eef2237d7d54'
down_revision: Union[str, Sequence[str], None] = 'b391f7694ec0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    """Añade la relación entre imputaciones y líneas de factura."""

    with op.batch_alter_table("imputacion_contrato") as batch_op:
        batch_op.add_column(
            sa.Column(
                "factura_linea_id",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.create_unique_constraint(
            "uq_imputacion_contrato_factura_linea",
            ["factura_linea_id"],
        )

        batch_op.create_foreign_key(
            "fk_imputacion_contrato_factura_linea",
            "factura_linea",
            ["factura_linea_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """Elimina la relación entre imputaciones y líneas de factura."""

    with op.batch_alter_table("imputacion_contrato") as batch_op:
        batch_op.drop_constraint(
            "fk_imputacion_contrato_factura_linea",
            type_="foreignkey",
        )

        batch_op.drop_constraint(
            "uq_imputacion_contrato_factura_linea",
            type_="unique",
        )

        batch_op.drop_column("factura_linea_id")

"""Añadir tipo de inmueble y marca de facturación

Revision ID: bec8b4e68350
Revises: 31dcce3e27e0
Create Date: 2026-08-26 19:12:58.718598

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bec8b4e68350'
down_revision: Union[str, Sequence[str], None] = '31dcce3e27e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "inmueble",
        sa.Column(
            "tipo",
            sa.Text(),
            nullable=False,
            server_default="L",
        ),
    )

    op.add_column(
        "contrato",
        sa.Column(
            "genera_factura",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    with op.batch_alter_table("inmueble") as batch_op:
        batch_op.create_check_constraint(
            "ck_inmueble_tipo",
            "tipo IN ('P', 'L', 'G')",
        )
        batch_op.alter_column(
            "tipo",
            server_default=None,
        )

    with op.batch_alter_table("contrato") as batch_op:
        batch_op.alter_column(
            "genera_factura",
            server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table("contrato") as batch_op:
        batch_op.drop_column("genera_factura")

    with op.batch_alter_table("inmueble") as batch_op:
        batch_op.drop_constraint(
            "ck_inmueble_tipo",
            type_="check",
        )
        batch_op.drop_column("tipo")

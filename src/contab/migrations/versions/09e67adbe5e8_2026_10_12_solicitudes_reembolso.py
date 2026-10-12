"""2026-10-12 solicitudes reembolso

Revision ID: 09e67adbe5e8
Revises: 2f77985632ce
Create Date: 2026-10-12 10:19:42.816415

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = '09e67adbe5e8'
down_revision: Union[str, Sequence[str], None] = '2f77985632ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table(
        "movimiento_previsto",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "solicitud_reembolso_id",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.create_unique_constraint(
            "uq_movimiento_previsto_solicitud_reembolso",
            ["solicitud_reembolso_id"],
        )

        batch_op.create_foreign_key(
            "fk_movimiento_previsto_solicitud_reembolso",
            "solicitud_reembolso",
            ["solicitud_reembolso_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table(
        "movimiento_previsto",
        schema=None,
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_movimiento_previsto_solicitud_reembolso",
            type_="foreignkey",
        )

        batch_op.drop_constraint(
            "uq_movimiento_previsto_solicitud_reembolso",
            type_="unique",
        )

        batch_op.drop_column(
            "solicitud_reembolso_id"
        )

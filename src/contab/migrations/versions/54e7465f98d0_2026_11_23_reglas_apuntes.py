"""2026-11-23 reglas apuntes

Revision ID: 54e7465f98d0
Revises: 03b79d4fab26
Create Date: 2026-11-23 15:38:51.035050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = '54e7465f98d0'
down_revision: Union[str, Sequence[str], None] = '03b79d4fab26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Exige exactamente un origen por movimiento previsto."""
    with op.batch_alter_table("movimiento_previsto") as batch_op:
        batch_op.create_check_constraint(
            "ck_movimiento_previsto_origen",
            """
            (
                apunte_id IS NOT NULL
                AND solicitud_reembolso_id IS NULL
            )
            OR
            (
                apunte_id IS NULL
                AND solicitud_reembolso_id IS NOT NULL
            )
            """,
        )


def downgrade() -> None:
    """Retira la restricción de origen."""
    with op.batch_alter_table("movimiento_previsto") as batch_op:
        batch_op.drop_constraint(
            "ck_movimiento_previsto_origen",
            type_="check",
        )

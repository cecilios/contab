"""2026-15-cambios-para-conciliacion-manual

Revision ID: 747c5aaf52f9
Revises: c83a4c231453
Create Date: 2026-09-15 17:27:23.507645

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = '747c5aaf52f9'
down_revision: Union[str, Sequence[str], None] = 'c83a4c231453'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("movimiento_previsto") as batch_op:
        batch_op.add_column(
            sa.Column(
                "metodo_conciliacion",
                sa.Text(),
                nullable=True,
            )
        )

    batch_op.create_check_constraint(
        "ck_movimiento_previsto_metodo_conciliacion",
        """
        metodo_conciliacion IS NULL
        OR metodo_conciliacion IN ('INDIVIDUAL', 'MANUAL')
        """,
    )

    op.execute(
        """
        UPDATE movimiento_previsto
        SET metodo_conciliacion = 'INDIVIDUAL'
        WHERE estado = 'CONCILIADO'
          AND EXISTS (
              SELECT 1
              FROM conciliacion
              WHERE conciliacion.movimiento_previsto_id =
                    movimiento_previsto.id
          )
        """
    )

def downgrade() -> None:
    """Elimina el método de conciliación de los movimientos previstos."""

    with op.batch_alter_table(
        "movimiento_previsto",
        schema=None,
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_movimiento_previsto_metodo_conciliacion",
            type_="check",
        )

        batch_op.drop_column(
            "metodo_conciliacion"
        )




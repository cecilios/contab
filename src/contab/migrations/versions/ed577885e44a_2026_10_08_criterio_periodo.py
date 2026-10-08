"""añadir criterio_periodo en ApunteContable

Revision ID: ed577885e44a
Revises: fa067471c781
Create Date: 2026-10-08 11:50:23.104534

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = 'ed577885e44a'
down_revision: Union[str, Sequence[str], None] = 'fa067471c781'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Añade el criterio de cómputo de los períodos."""

    op.add_column(
        "apunte_contable",
        sa.Column(
            "criterio_periodo",
            sa.Text(),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE apunte_contable
        SET criterio_periodo = 'INCLUIR_AMBOS'
        WHERE periodo_desde IS NOT NULL
          AND periodo_hasta IS NOT NULL
        """
    )

    with op.batch_alter_table(
        "apunte_contable",
        recreate="always",
    ) as batch_op:
        batch_op.create_check_constraint(
            "ck_apunte_contable_criterio_periodo",
            """
            (
                periodo_desde IS NULL
                AND periodo_hasta IS NULL
                AND criterio_periodo IS NULL
            )
            OR
            (
                periodo_desde IS NOT NULL
                AND periodo_hasta IS NOT NULL
                AND criterio_periodo IS NOT NULL
                AND criterio_periodo IN (
                    'EXCLUIR_HASTA',
                    'EXCLUIR_DESDE',
                    'INCLUIR_AMBOS',
                    'EXCLUIR_AMBOS'
                )
            )
            """,
        )

def downgrade() -> None:
    """Elimina el criterio de cómputo de los períodos."""

    with op.batch_alter_table(
        "apunte_contable",
        recreate="always",
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_apunte_contable_criterio_periodo",
            type_="check",
        )

        batch_op.drop_column(
            "criterio_periodo",
        )


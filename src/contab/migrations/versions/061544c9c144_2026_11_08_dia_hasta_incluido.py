"""2026-11-08 dia hasta incluido

Revision ID: 061544c9c144
Revises: abb6f40056ca
Create Date: 2026-11-08 13:39:34.418795

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = '061544c9c144'
down_revision: Union[str, Sequence[str], None] = 'abb6f40056ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Sustituye el criterio textual por un booleano nullable."""

    op.add_column(
        "apunte_contable",
        sa.Column(
            "dia_hasta_incluido",
            sa.Boolean(),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE apunte_contable
        SET dia_hasta_incluido =
            CASE criterio_periodo
                WHEN 'INCLUIR_AMBOS' THEN 1
                WHEN 'EXCLUIR_HASTA' THEN 0
                ELSE NULL
            END
        """
    )

    with op.batch_alter_table("apunte_contable") as batch_op:
        batch_op.drop_constraint(
            "ck_apunte_contable_criterio_periodo",
            type_="check",
        )

        batch_op.drop_column("criterio_periodo")

        batch_op.create_check_constraint(
            "ck_apunte_contable_dia_hasta_incluido",
            """
            (
                periodo_desde IS NULL
                AND periodo_hasta IS NULL
                AND dia_hasta_incluido IS NULL
            )
            OR
            (
                periodo_desde IS NOT NULL
                AND periodo_hasta IS NOT NULL
                AND dia_hasta_incluido IS NOT NULL
                AND dia_hasta_incluido IN (0, 1)
            )
            """,
        )


def downgrade() -> None:
    """Restaura el criterio textual conservando sus valores."""

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
        SET criterio_periodo =
            CASE dia_hasta_incluido
                WHEN 1 THEN 'INCLUIR_AMBOS'
                WHEN 0 THEN 'EXCLUIR_HASTA'
                ELSE NULL
            END
        """
    )

    with op.batch_alter_table("apunte_contable") as batch_op:
        batch_op.drop_constraint(
            "ck_apunte_contable_dia_hasta_incluido",
            type_="check",
        )

        batch_op.drop_column("dia_hasta_incluido")

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

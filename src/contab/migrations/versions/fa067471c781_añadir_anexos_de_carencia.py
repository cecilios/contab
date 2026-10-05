"""añadir anexos de carencia

Revision ID: fa067471c781
Revises: 2bfe0e7876a3
Create Date: 2026-10-05 11:44:04.214795

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = 'fa067471c781'
down_revision: Union[str, Sequence[str], None] = '2bfe0e7876a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Añade soporte para períodos de carencia contractuales."""

    with op.batch_alter_table(
        "anexo_contrato",
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "fecha_desde",
                sa.Date(),
                nullable=True,
            )
        )

        batch_op.add_column(
            sa.Column(
                "fecha_hasta",
                sa.Date(),
                nullable=True,
            )
        )

        batch_op.drop_constraint(
            "ck_anexo_contrato_tipo",
            type_="check",
        )

        batch_op.create_check_constraint(
            "ck_anexo_contrato_tipo",
            "tipo IN ("
            "'CAMBIO_RENTA', "
            "'PRORROGA', "
            "'CARENCIA'"
            ")",
        )

        batch_op.create_check_constraint(
            "ck_anexo_contrato_carencia_fechas",
            "("
            "tipo = 'CARENCIA' "
            "AND fecha_desde IS NOT NULL "
            "AND fecha_hasta IS NOT NULL"
            ") OR ("
            "tipo != 'CARENCIA' "
            "AND fecha_desde IS NULL "
            "AND fecha_hasta IS NULL"
            ")",
        )

        batch_op.create_check_constraint(
            "ck_anexo_contrato_periodo",
            "fecha_hasta IS NULL "
            "OR fecha_desde IS NULL "
            "OR fecha_hasta >= fecha_desde",
        )


def downgrade() -> None:
    """Elimina el soporte para períodos de carencia contractuales."""

    with op.batch_alter_table(
        "anexo_contrato",
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_anexo_contrato_periodo",
            type_="check",
        )

        batch_op.drop_constraint(
            "ck_anexo_contrato_carencia_fechas",
            type_="check",
        )

        batch_op.drop_constraint(
            "ck_anexo_contrato_tipo",
            type_="check",
        )

        batch_op.create_check_constraint(
            "ck_anexo_contrato_tipo",
            "tipo IN ('CAMBIO_RENTA', 'PRORROGA')",
        )

        batch_op.drop_column("fecha_hasta")
        batch_op.drop_column("fecha_desde")


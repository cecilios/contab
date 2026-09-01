"""ampliar apuntes contables

Revision ID: 8ee51ae4946d
Revises: 41f3945c3f9a
Create Date: 2026-08-31 13:25:19.032577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = '8ee51ae4946d'
down_revision: Union[str, Sequence[str], None] = '41f3945c3f9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Añade período, tratamiento y documento al apunte contable."""
    op.add_column(
        "apunte_contable",
        sa.Column(
            "periodo_desde",
            sa.Date(),
            nullable=True,
        ),
    )
    op.add_column(
        "apunte_contable",
        sa.Column(
            "periodo_hasta",
            sa.Date(),
            nullable=True,
        ),
    )
    op.add_column(
        "apunte_contable",
        sa.Column(
            "tratamiento",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "apunte_contable",
        sa.Column(
            "nombre_documento",
            sa.Text(),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE apunte_contable
        SET tratamiento = 'CONTABILIZAR',
            nombre_documento = ''
        """
    )

    with op.batch_alter_table(
        "apunte_contable",
        recreate="always",
    ) as batch_op:
        batch_op.alter_column(
            "tratamiento",
            existing_type=sa.Text(),
            nullable=False,
        )
        batch_op.alter_column(
            "nombre_documento",
            existing_type=sa.Text(),
            nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_apunte_contable_periodo_completo",
            "(periodo_desde IS NULL "
            "AND periodo_hasta IS NULL) "
            "OR (periodo_desde IS NOT NULL "
            "AND periodo_hasta IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_apunte_contable_periodo_orden",
            "periodo_desde IS NULL "
            "OR periodo_hasta >= periodo_desde",
        )
        batch_op.create_check_constraint(
            "ck_apunte_contable_tratamiento",
            "tratamiento IN "
            "('CONTABILIZAR', 'REPERCUTIR', 'FACTURAR')",
        )


def downgrade() -> None:
    """Elimina los datos adicionales del apunte contable."""
    with op.batch_alter_table(
        "apunte_contable",
        recreate="always",
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_apunte_contable_tratamiento",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_apunte_contable_periodo_orden",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_apunte_contable_periodo_completo",
            type_="check",
        )
        batch_op.drop_column("nombre_documento")
        batch_op.drop_column("tratamiento")
        batch_op.drop_column("periodo_hasta")
        batch_op.drop_column("periodo_desde")

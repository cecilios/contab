"""cambiar-movimiento-previsto

Revision ID: 0ae6f256cd56
Revises: ccfe6d430eda
Create Date: 2026-09-12 12:18:31.628029

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = '0ae6f256cd56'
down_revision: Union[str, Sequence[str], None] = 'ccfe6d430eda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Amplía fechas y estados de los movimientos previstos."""

    with op.batch_alter_table(
        "movimiento_previsto"
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "fecha_prevista_desde",
                sa.Date(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "fecha_prevista_hasta",
                sa.Date(),
                nullable=True,
            )
        )

    # La fecha anterior representaba un día concreto.
    op.execute(
        sa.text(
            """
            UPDATE movimiento_previsto
            SET
                fecha_prevista_desde = fecha_prevista,
                fecha_prevista_hasta = fecha_prevista
            """
        )
    )

    with op.batch_alter_table(
        "movimiento_previsto"
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_movimiento_previsto_importe",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_movimiento_previsto_estado",
            type_="check",
        )

        batch_op.create_check_constraint(
            "ck_movimiento_previsto_importe",
            "importe_esperado > 0",
        )
        batch_op.create_check_constraint(
            "ck_movimiento_previsto_estado",
            """
            estado IN (
                'PENDIENTE',
                'PARCIAL',
                'CONCILIADO',
                'CANCELADO'
            )
            """,
        )
        batch_op.create_check_constraint(
            "ck_movimiento_previsto_fechas_completas",
            """
            fecha_prevista_hasta IS NULL
            OR fecha_prevista_desde IS NOT NULL
            """,
        )
        batch_op.create_check_constraint(
            "ck_movimiento_previsto_fechas_orden",
            """
            fecha_prevista_desde IS NULL
            OR fecha_prevista_hasta IS NULL
            OR fecha_prevista_hasta >= fecha_prevista_desde
            """,
        )

        batch_op.drop_column(
            "fecha_prevista"
        )

def downgrade() -> None:
    """Restaura la fecha única del modelo anterior."""

    conexion = op.get_bind()

    incompatibles = conexion.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM movimiento_previsto
            WHERE
                fecha_prevista_desde IS NULL
                OR estado IN ('PARCIAL', 'CANCELADO')
            """
        )
    ).scalar_one()

    if incompatibles:
        raise RuntimeError(
            "No puede revertirse la migración porque existen "
            "movimientos sin fecha o con estados nuevos."
        )

    with op.batch_alter_table(
        "movimiento_previsto"
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "fecha_prevista",
                sa.Date(),
                nullable=True,
            )
        )

    op.execute(
        sa.text(
            """
            UPDATE movimiento_previsto
            SET fecha_prevista = fecha_prevista_desde
            """
        )
    )

    with op.batch_alter_table(
        "movimiento_previsto"
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_movimiento_previsto_fechas_orden",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_movimiento_previsto_fechas_completas",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_movimiento_previsto_estado",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_movimiento_previsto_importe",
            type_="check",
        )

        batch_op.create_check_constraint(
            "ck_movimiento_previsto_estado",
            "estado IN ('PENDIENTE', 'CONCILIADO')",
        )
        batch_op.create_check_constraint(
            "ck_movimiento_previsto_importe",
            "importe_esperado >= 0",
        )

        batch_op.alter_column(
            "fecha_prevista",
            existing_type=sa.Date(),
            nullable=False,
        )

        batch_op.drop_column(
            "fecha_prevista_hasta"
        )
        batch_op.drop_column(
            "fecha_prevista_desde"
        )

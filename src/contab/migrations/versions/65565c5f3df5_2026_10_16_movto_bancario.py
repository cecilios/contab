"""2026-10-16 movto bancario

Revision ID: 65565c5f3df5
Revises: eef2237d7d54
Create Date: 2026-10-16 12:30:25.120417

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = '65565c5f3df5'
down_revision: Union[str, Sequence[str], None] = 'eef2237d7d54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    """Permite conciliaciones bancarias parciales."""

    with op.batch_alter_table(
        "movimiento_bancario"
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_movimiento_bancario_estado",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_movimiento_bancario_estado",
            "estado IN ("
            "'PENDIENTE', "
            "'PARCIAL', "
            "'CONCILIADO', "
            "'DESCARTADO'"
            ")",
        )


def downgrade() -> None:
    """Restaura los estados anteriores si no existen parciales."""

    conexion = op.get_bind()

    cantidad_parciales = conexion.scalar(
        sa.text(
            "SELECT COUNT(*) "
            "FROM movimiento_bancario "
            "WHERE estado = 'PARCIAL'"
        )
    )

    if cantidad_parciales:
        raise RuntimeError(
            "No se puede revertir la migración: "
            "existen movimientos bancarios parcialmente conciliados."
        )

    with op.batch_alter_table(
        "movimiento_bancario"
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_movimiento_bancario_estado",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_movimiento_bancario_estado",
            "estado IN ("
            "'PENDIENTE', "
            "'CONCILIADO', "
            "'DESCARTADO'"
            ")",
        )


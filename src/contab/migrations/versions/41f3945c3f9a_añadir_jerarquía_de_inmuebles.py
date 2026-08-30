"""Añadir jerarquía de inmuebles

Revision ID: 41f3945c3f9a
Revises: a34a1fa7fe25
Create Date: 2026-08-30 15:28:26.898368

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = '41f3945c3f9a'
down_revision: Union[str, Sequence[str], None] = 'a34a1fa7fe25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Añade la jerarquía de inmuebles."""

    with op.batch_alter_table(
        "inmueble",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "inmueble_padre_id",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.drop_constraint(
            "ck_inmueble_tipo",
            type_="check",
        )

        batch_op.create_check_constraint(
            "ck_inmueble_tipo",
            "tipo IN ('T', 'P', 'L', 'G')",
        )

        batch_op.create_check_constraint(
            "ck_inmueble_no_es_su_padre",
            "inmueble_padre_id IS NULL "
            "OR inmueble_padre_id != id",
        )

        batch_op.create_check_constraint(
            "ck_inmueble_total",
            "tipo != 'T' OR ("
            "inmueble_padre_id IS NULL "
            "AND participacion = 10000"
            ")",
        )

        batch_op.create_foreign_key(
            "fk_inmueble_padre",
            "inmueble",
            ["inmueble_padre_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """Elimina la jerarquía de inmuebles."""

    with op.batch_alter_table(
        "inmueble",
        schema=None,
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_inmueble_padre",
            type_="foreignkey",
        )

        batch_op.drop_constraint(
            "ck_inmueble_total",
            type_="check",
        )

        batch_op.drop_constraint(
            "ck_inmueble_no_es_su_padre",
            type_="check",
        )

        batch_op.drop_constraint(
            "ck_inmueble_tipo",
            type_="check",
        )

        batch_op.create_check_constraint(
            "ck_inmueble_tipo",
            "tipo IN ('P', 'L', 'G')",
        )

        batch_op.drop_column(
            "inmueble_padre_id",
        )


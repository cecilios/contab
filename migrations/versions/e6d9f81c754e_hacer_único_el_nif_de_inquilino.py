"""Hacer único el NIF de inquilino

Revision ID: e6d9f81c754e
Revises: dd64d6ded800
Create Date: 2026-08-22 19:34:56.353592

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6d9f81c754e'
down_revision: Union[str, Sequence[str], None] = 'dd64d6ded800'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Hace único el NIF de los inquilinos."""
    with op.batch_alter_table("inquilino") as batch_op:
        batch_op.create_unique_constraint(
            "uq_inquilino_nif",
            ["nif"],
        )


def downgrade() -> None:
    """Elimina la unicidad del NIF de los inquilinos."""
    with op.batch_alter_table("inquilino") as batch_op:
        batch_op.drop_constraint(
            "uq_inquilino_nif",
            type_="unique",
        )

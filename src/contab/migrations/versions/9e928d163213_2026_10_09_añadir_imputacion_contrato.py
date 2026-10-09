"""2026-10-09 añadir Imputacion-contrato

Revision ID: 9e928d163213
Revises: b8f0d5a2848b
Create Date: 2026-10-09 15:44:56.687562

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = '9e928d163213'
down_revision: Union[str, Sequence[str], None] = 'b8f0d5a2848b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea las imputaciones de gastos a contratos."""

    op.create_table('imputacion_contrato',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('apunte_id', sa.Integer(), nullable=True),
    sa.Column('distribucion_apunte_id', sa.Integer(), nullable=True),
    sa.Column('contrato_id', sa.Integer(), nullable=False),
    sa.Column('importe', sa.Integer(), nullable=False),
    sa.CheckConstraint('\n            (\n                apunte_id IS NOT NULL\n                AND distribucion_apunte_id IS NULL\n            )\n            OR\n            (\n                apunte_id IS NULL\n                AND distribucion_apunte_id IS NOT NULL\n            )\n            ', name='ck_imputacion_contrato_origen'),
    sa.CheckConstraint('importe > 0', name='ck_imputacion_contrato_importe'),
    sa.ForeignKeyConstraint(['apunte_id'], ['apunte_contable.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['contrato_id'], ['contrato.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['distribucion_apunte_id'], ['distribucion_apunte.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('apunte_id', 'contrato_id', name='uq_imputacion_contrato_apunte'),
    sa.UniqueConstraint('distribucion_apunte_id', 'contrato_id', name='uq_imputacion_contrato_distribucion')
    )


def downgrade() -> None:
    """Elimina las imputaciones de gastos a contratos."""

    op.drop_table('imputacion_contrato')

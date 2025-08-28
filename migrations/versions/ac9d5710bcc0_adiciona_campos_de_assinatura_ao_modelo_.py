"""Adiciona campos de assinatura ao modelo User

Revision ID: ac9d5710bcc0
Revises: 
Create Date: 2025-08-28 03:02:39.450801
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ac9d5710bcc0'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # adiciona colunas ao User
    op.add_column('user', sa.Column('plan_type', sa.String(length=50), nullable=True))
    op.add_column('user', sa.Column('subscription_status', sa.String(length=50), nullable=True))
    op.add_column('user', sa.Column('trial_ends_at', sa.DateTime(), nullable=True))


def downgrade():
    # remove colunas se der rollback
    op.drop_column('user', 'trial_ends_at')
    op.drop_column('user', 'subscription_status')
    op.drop_column('user', 'plan_type')

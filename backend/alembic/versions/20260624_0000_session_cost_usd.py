"""session cost_usd

Revision ID: a1b2c3d4e5f6
Revises: 89a17aa10606
Create Date: 2026-06-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '89a17aa10606'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'sessions',
        sa.Column('cost_usd', sa.Numeric(12, 6), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('sessions', 'cost_usd')

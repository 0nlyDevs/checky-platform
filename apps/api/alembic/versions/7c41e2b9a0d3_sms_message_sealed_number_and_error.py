"""sms message sealed number and error

Revision ID: 7c41e2b9a0d3
Revises: 85d355a0a5a7
Create Date: 2026-11-03 04:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c41e2b9a0d3'
down_revision: Union[str, Sequence[str], None] = '85d355a0a5a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('sms_message', sa.Column('phone_sealed', sa.Text(), nullable=True), schema='app')
    op.add_column('sms_message', sa.Column('error', sa.String(length=200), nullable=True), schema='app')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sms_message', 'error', schema='app')
    op.drop_column('sms_message', 'phone_sealed', schema='app')

"""journalist profile with press card

Revision ID: c3a91f5d7e20
Revises: 364df0386f20
Create Date: 2026-11-03 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c3a91f5d7e20'
down_revision: Union[str, Sequence[str], None] = '364df0386f20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'journalist_profile',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('phone', sa.String(length=24), nullable=False),
        sa.Column('outlet', sa.String(length=160), nullable=False),
        sa.Column('card_number', sa.String(length=60), nullable=True),
        sa.Column('card_key', sa.String(length=400), nullable=False),
        sa.Column('card_filename', sa.String(length=255), nullable=False),
        sa.Column('card_mime', sa.String(length=120), nullable=False),
        sa.Column('card_size_bytes', sa.Integer(), nullable=False),
        sa.Column('card_sha256', sa.String(length=64), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
        schema='app',
    )
    op.create_index(op.f('ix_app_journalist_profile_card_sha256'), 'journalist_profile', ['card_sha256'], unique=False, schema='app')


def downgrade() -> None:
    op.drop_table('journalist_profile', schema='app')

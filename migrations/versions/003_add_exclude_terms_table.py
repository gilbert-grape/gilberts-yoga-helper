"""Add exclude_terms table for negative keyword filtering.

Creates exclude_terms table to store keywords that should exclude
listings from search results.

Revision ID: 003_exclude_terms
Revises: 002_app_settings
Create Date: 2026-01-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_exclude_terms'
down_revision: Union[str, None] = '002_app_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create exclude_terms table
    op.create_table(
        'exclude_terms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('term', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('term'),
    )
    op.create_index(op.f('ix_exclude_terms_id'), 'exclude_terms', ['id'], unique=False)
    op.create_index(op.f('ix_exclude_terms_term'), 'exclude_terms', ['term'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_exclude_terms_term'), table_name='exclude_terms')
    op.drop_index(op.f('ix_exclude_terms_id'), table_name='exclude_terms')
    op.drop_table('exclude_terms')

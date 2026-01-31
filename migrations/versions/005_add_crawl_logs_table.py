"""Add crawl_logs table for crawl history tracking.

Creates crawl_logs table to store history of all crawl executions,
whether started manually or via cronjob.

Revision ID: 005_crawl_logs
Revises: 14ad29168b84
Create Date: 2026-01-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005_crawl_logs'
down_revision: Union[str, None] = '14ad29168b84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create crawl_logs table
    op.create_table(
        'crawl_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='running'),
        sa.Column('sources_attempted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sources_succeeded', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sources_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_listings', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('new_matches', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duplicate_matches', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_seconds', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('trigger', sa.String(20), nullable=False, server_default='manual'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed', 'cancelled')",
            name='check_crawl_status_valid'
        ),
        sa.CheckConstraint(
            "trigger IN ('manual', 'cronjob')",
            name='check_crawl_trigger_valid'
        ),
    )
    op.create_index(op.f('ix_crawl_logs_id'), 'crawl_logs', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_crawl_logs_id'), table_name='crawl_logs')
    op.drop_table('crawl_logs')

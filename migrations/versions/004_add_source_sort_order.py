"""Add sort_order column to sources table.

Allows users to define the order in which sources are crawled.

Revision ID: 004_source_sort_order
Revises: 003_exclude_terms
Create Date: 2026-01-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004_source_sort_order'
down_revision: Union[str, None] = '003_exclude_terms'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add sort_order column with default value 0
    op.add_column('sources', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))

    # Update existing sources to have sequential sort_order based on id
    # This ensures existing sources have a defined order
    op.execute("""
        UPDATE sources
        SET sort_order = (
            SELECT COUNT(*)
            FROM sources AS s2
            WHERE s2.id < sources.id
        )
    """)


def downgrade() -> None:
    op.drop_column('sources', 'sort_order')

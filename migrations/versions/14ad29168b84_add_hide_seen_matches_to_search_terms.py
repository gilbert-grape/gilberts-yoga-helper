"""add_hide_seen_matches_to_search_terms

Revision ID: 14ad29168b84
Revises: 981cdbe59202
Create Date: 2026-01-30 08:24:43.142486

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '14ad29168b84'
down_revision: Union[str, None] = '981cdbe59202'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'search_terms',
        sa.Column('hide_seen_matches', sa.Boolean(), nullable=False, server_default='1')
    )


def downgrade() -> None:
    op.drop_column('search_terms', 'hide_seen_matches')

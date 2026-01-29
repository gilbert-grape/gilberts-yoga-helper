"""Add sort_order to search_terms

Revision ID: fd3a4370ed78
Revises: 002_app_settings
Create Date: 2026-01-29 09:27:19.132730

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd3a4370ed78'
down_revision: Union[str, None] = '002_app_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add sort_order column with server_default for existing rows
    with op.batch_alter_table('search_terms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
        batch_op.create_index(batch_op.f('ix_search_terms_sort_order'), ['sort_order'], unique=False)

    # Initialize sort_order based on existing id order
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE search_terms
        SET sort_order = (
            SELECT COUNT(*) FROM search_terms AS st2 WHERE st2.id < search_terms.id
        )
    """))


def downgrade() -> None:
    with op.batch_alter_table('search_terms', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_search_terms_sort_order'))
        batch_op.drop_column('sort_order')

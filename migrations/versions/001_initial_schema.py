"""Initial schema for Gebrauchtwaffen Aggregator.

Creates all tables: search_terms, sources, matches

Revision ID: 001_initial
Revises:
Create Date: 2026-01-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create search_terms table
    op.create_table(
        'search_terms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('term', sa.String(length=255), nullable=False),
        sa.Column('match_type', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("match_type IN ('exact', 'similar')", name='check_match_type_valid'),
    )
    op.create_index(op.f('ix_search_terms_id'), 'search_terms', ['id'], unique=False)
    op.create_index(op.f('ix_search_terms_term'), 'search_terms', ['term'], unique=True)

    # Create sources table
    op.create_table(
        'sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('base_url', sa.String(length=500), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_crawl_at', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sources_id'), 'sources', ['id'], unique=False)
    op.create_index(op.f('ix_sources_name'), 'sources', ['name'], unique=True)

    # Create matches table
    op.create_table(
        'matches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('search_term_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('price', sa.String(length=50), nullable=True),
        sa.Column('url', sa.String(length=1000), nullable=False),
        sa.Column('image_url', sa.String(length=1000), nullable=True),
        sa.Column('is_new', sa.Boolean(), nullable=False),
        sa.Column('external_id', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(['search_term_id'], ['search_terms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_matches_external_id'), 'matches', ['external_id'], unique=False)
    op.create_index(op.f('ix_matches_id'), 'matches', ['id'], unique=False)
    op.create_index(op.f('ix_matches_search_term_id'), 'matches', ['search_term_id'], unique=False)
    op.create_index(op.f('ix_matches_source_id'), 'matches', ['source_id'], unique=False)


def downgrade() -> None:
    # Drop matches table and indexes
    op.drop_index(op.f('ix_matches_source_id'), table_name='matches')
    op.drop_index(op.f('ix_matches_search_term_id'), table_name='matches')
    op.drop_index(op.f('ix_matches_id'), table_name='matches')
    op.drop_index(op.f('ix_matches_external_id'), table_name='matches')
    op.drop_table('matches')

    # Drop sources table and indexes
    op.drop_index(op.f('ix_sources_name'), table_name='sources')
    op.drop_index(op.f('ix_sources_id'), table_name='sources')
    op.drop_table('sources')

    # Drop search_terms table and indexes
    op.drop_index(op.f('ix_search_terms_term'), table_name='search_terms')
    op.drop_index(op.f('ix_search_terms_id'), table_name='search_terms')
    op.drop_table('search_terms')

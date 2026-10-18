"""aree di precarico per punto di ritiro

Revision ID: 075
Revises: 074
Create Date: 2026-10-15 12:00:00.000000

collection_point_preload_area: le aree in cui un punto di ritiro viene
precaricato, per CAP e/o poligono. Un punto con aree usa quelle; senza aree vale
l'accepts_preloads della zona di copertura.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '075'
down_revision: Union[str, None] = '074'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'collection_point_preload_area',
    sa.Column('collection_point_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('caps', sa.JSON(), nullable=False),
    sa.Column('polygon', sa.JSON(), nullable=True),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['collection_point_id'], ['collection_point.id']),
    sa.ForeignKeyConstraint(['company_id'], ['company.id']),
    sa.PrimaryKeyConstraint('id'),
  )
  op.create_index(
    op.f('ix_collection_point_preload_area_collection_point_id'),
    'collection_point_preload_area',
    ['collection_point_id'],
    unique=False,
  )


def downgrade() -> None:
  op.drop_index(
    op.f('ix_collection_point_preload_area_collection_point_id'), table_name='collection_point_preload_area'
  )
  op.drop_table('collection_point_preload_area')

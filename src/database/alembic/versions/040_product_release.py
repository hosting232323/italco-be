"""Product Release

Revision ID: 040
Revises: 039
Create Date: 2026-05-01 11:44:11.632672

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '040'
down_revision: Union[str, None] = '039'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('product', sa.Column('transport_id', sa.Integer(), nullable=True))
  op.add_column('product', sa.Column('release_transport_id', sa.Integer(), nullable=True))
  op.add_column('product', sa.Column('release_collection_point_id', sa.Integer(), nullable=True))
  op.alter_column('product', 'collection_point_id', existing_type=sa.INTEGER(), nullable=True)
  op.create_foreign_key(None, 'product', 'transport', ['transport_id'], ['id'])
  op.create_foreign_key(None, 'product', 'collection_point', ['release_collection_point_id'], ['id'])
  op.create_foreign_key(None, 'product', 'transport', ['release_transport_id'], ['id'])


def downgrade() -> None:
  op.drop_constraint(None, 'product', type_='foreignkey')
  op.drop_constraint(None, 'product', type_='foreignkey')
  op.drop_constraint(None, 'product', type_='foreignkey')
  op.alter_column('product', 'collection_point_id', existing_type=sa.INTEGER(), nullable=False)
  op.drop_column('product', 'release_collection_point_id')
  op.drop_column('product', 'release_transport_id')
  op.drop_column('product', 'transport_id')

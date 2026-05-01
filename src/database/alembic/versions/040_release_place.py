"""Release Place

Revision ID: 040
Revises: 039
Create Date: 2026-04-20 01:02:31.068764

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '040'
down_revision: Union[str, None] = '039'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'schedule_item_release_place',
    sa.Column('schedule_item_id', sa.Integer(), nullable=False),
    sa.Column('collection_point_id', sa.Integer(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['collection_point_id'],
      ['collection_point.id'],
    ),
    sa.ForeignKeyConstraint(
      ['schedule_item_id'],
      ['schedule_item.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
  )

  op.execute('ALTER TYPE scheduletype RENAME TO scheduletype_old')
  op.execute("""
    CREATE TYPE scheduletype_new AS ENUM (
      'ORDER',
      'RELEASE_PLACE',
      'COLLECTION_POINT'
    )
  """)
  op.execute("""
    ALTER TABLE schedule_item
    ALTER COLUMN operation_type TYPE scheduletype_new
    USING (
      CASE operation_type::text
        WHEN 'COLLECTIONPOINT' THEN 'COLLECTION_POINT'
        ELSE operation_type::text
      END
    )::scheduletype_new
  """)
  op.execute('DROP TYPE scheduletype_old')
  op.execute('ALTER TYPE scheduletype_new RENAME TO scheduletype')

  op.add_column('product', sa.Column('on_transport', sa.Boolean(), nullable=True))
  op.add_column('product', sa.Column('release_place_id', sa.Integer(), nullable=False))
  op.alter_column('product', 'collection_point_id', existing_type=sa.INTEGER(), nullable=True)
  op.create_foreign_key(None, 'product', 'collection_point', ['release_place_id'], ['id'])


def downgrade() -> None:
  op.drop_table('schedule_item_release_place')

  op.drop_constraint(None, 'product', type_='foreignkey')
  op.alter_column('product', 'collection_point_id', existing_type=sa.INTEGER(), nullable=False)
  op.drop_column('product', 'release_place_id')
  op.drop_column('product', 'on_transport')

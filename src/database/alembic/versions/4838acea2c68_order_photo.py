"""Order photo

Revision ID: 4838acea2c68
Revises: cdc2b6bb47b8
Create Date: 2025-05-15 10:46:52.827778

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '4838acea2c68'
down_revision: Union[str, None] = 'cdc2b6bb47b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table('photo',
    sa.Column('photo', sa.LargeBinary(), nullable=False),
    sa.Column('mime_type', sa.String(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['order.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  op.drop_column('order', 'photo_mime_type')
  op.drop_column('order', 'photo')


def downgrade() -> None:
  op.add_column('order', sa.Column('photo', postgresql.BYTEA(), autoincrement=False, nullable=True))
  op.add_column('order', sa.Column('photo_mime_type', sa.VARCHAR(), autoincrement=False, nullable=True))
  op.drop_table('photo')

"""Photo link

Revision ID: 016
Revises: 015
Create Date: 2025-12-07 20:01:29.999122

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '016'
down_revision: Union[str, None] = '015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.drop_column('photo', 'photo')
  op.drop_column('photo', 'mime_type')
  op.alter_column('photo', 'path', new_column_name='link')
  op.alter_column('photo', 'link', existing_type=sa.String(), nullable=False)


def downgrade() -> None:
  op.add_column('photo', sa.Column('photo', postgresql.BYTEA(), autoincrement=False, nullable=True))
  op.add_column('photo', sa.Column('mime_type', sa.VARCHAR(), autoincrement=False, nullable=False))
  op.alter_column('photo', 'link', existing_type=sa.String(), nullable=True)
  op.alter_column('photo', 'link', new_column_name='path')

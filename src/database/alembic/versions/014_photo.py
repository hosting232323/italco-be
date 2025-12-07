"""Photo

Revision ID: 014
Revises: 013
Create Date: 2025-12-02 15:14:30.016910

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('photo', sa.Column('path', sa.String(), nullable=True))
  op.alter_column('photo', 'photo', existing_type=postgresql.BYTEA(), nullable=True)


def downgrade() -> None:
  op.drop_column('photo', 'path')
  op.alter_column('photo', 'photo', existing_type=postgresql.BYTEA(), nullable=False)

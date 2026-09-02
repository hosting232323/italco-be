"""rename user nickname to email

Revision ID: 056
Revises: 055
Create Date: 2026-09-02 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = '056'
down_revision: Union[str, None] = '055'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.alter_column('user', 'nickname', new_column_name='email')


def downgrade() -> None:
  op.alter_column('user', 'email', new_column_name='nickname')

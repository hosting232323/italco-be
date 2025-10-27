"""Email nickname

Revision ID: 56f8abead30f
Revises: 981eba745ab5
Create Date: 2025-10-22 15:59:02.745065

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '56f8abead30f'
down_revision: Union[str, None] = '981eba745ab5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('italco_user', sa.Column('nickname', sa.String(), nullable=True))
  op.alter_column('italco_user', 'email', existing_type=sa.VARCHAR(), nullable=True)

  op.execute('UPDATE italco_user SET nickname = email')
  op.execute('UPDATE italco_user SET email = NULL')

  op.alter_column('italco_user', 'nickname', nullable=False)
  op.drop_constraint(op.f('italco_user_email_key'), 'italco_user', type_='unique')
  op.create_unique_constraint(None, 'italco_user', ['nickname'])
  op.drop_column('italco_user', 'pass_token')
  op.rename_table('italco_user', 'user')


def downgrade() -> None:
  op.rename_table('user', 'italco_user')
  op.add_column('italco_user', sa.Column('pass_token', sa.VARCHAR(), autoincrement=False, nullable=True))
  op.drop_constraint(None, 'italco_user', type_='unique')
  op.create_unique_constraint(
    op.f('italco_user_email_key'), 'italco_user', ['email'], postgresql_nulls_not_distinct=False
  )
  op.alter_column('italco_user', 'email', existing_type=sa.VARCHAR(), nullable=False)
  op.drop_column('italco_user', 'nickname')

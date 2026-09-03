"""motivation column

Revision ID: 056
Revises: 055
Create Date: 2026-09-02 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '056'
down_revision: Union[str, None] = '055'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('order', sa.Column('motivation', sa.String(), nullable=True))
  op.execute(
    sa.text(
      'UPDATE "order" o SET motivation = m.text '
      'FROM (SELECT DISTINCT ON (order_id) order_id, text FROM motivation '
      'ORDER BY order_id, created_at DESC) m '
      'WHERE o.id = m.order_id'
    )
  )
  op.drop_table('motivation')


def downgrade() -> None:
  op.create_table(
    'motivation',
    sa.Column('text', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('delay', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('anomaly', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('status', postgresql.ENUM(name='orderstatus', create_type=False), autoincrement=False, nullable=False),
    sa.Column('order_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('company_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['order.id'], name=op.f('motivation_order_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('motivation_pkey')),
  )
  op.drop_column('order', 'motivation')

"""History

Revision ID: 037
Revises: 036
Create Date: 2026-03-30 12:26:19.004557

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '037'
down_revision: Union[str, None] = '036'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'history',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('status', sa.JSON(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['order.id']),
    sa.PrimaryKeyConstraint('id'),
  )

  connection = op.get_bind()
  connection.execute(
    sa.text("""
      INSERT INTO history (status, order_id, created_at, updated_at)
      SELECT
        json_build_object(
          'type', 'status',
          'value', status::text
        ),
        order_id,
        created_at,
        updated_at
      FROM status
      WHERE status IS NOT NULL
    """)
  )

  op.drop_table('status')


def downgrade() -> None:
  op.create_table(
    'status',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column(
      'status',
      postgresql.ENUM(
        'ACQUIRED',
        'BOOKED',
        'BOOKING',
        'DELIVERED',
        'NOT_DELIVERED',
        'REDELIVERY',
        'REPLACEMENT',
        'CANCELLED',
        'URGENT',
        'VERIFICATION',
        'CANCELLED_TO_BE_REFUNDED',
        'DELETED',
        'SCHEDULED',
        'AT_WAREHOUSE',
        'TO_RESCHEDULE',
        name='orderstatus',
      ),
      nullable=False,
    ),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['order.id']),
    sa.PrimaryKeyConstraint('id'),
  )
  op.drop_table('history')

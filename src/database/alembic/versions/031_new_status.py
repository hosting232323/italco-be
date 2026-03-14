"""new status

Revision ID: 031
Revises: 030
Create Date: 2026-03-14 12:23:21.486798

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '031'
down_revision: Union[str, None] = '030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('order', sa.Column('confirmed', sa.Boolean(), nullable=True))
  op.alter_column(
    'order',
    'external_status',
    existing_type=postgresql.ENUM(
      'NEW',
      'CONFIRMED',
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
      'AT_WAREHOUSE',
      'TO_RESCHEDULE',
      name='orderstatus',
    ),
    type_=sa.Enum(
      'NEW',
      'CONFIRMED',
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
      name='euronicsstatus',
    ),
    existing_nullable=True,
  )


def downgrade() -> None:
  op.alter_column(
    'order',
    'external_status',
    existing_type=sa.Enum(
      'NEW',
      'CONFIRMED',
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
      name='euronicsstatus',
    ),
    type_=postgresql.ENUM(
      'NEW',
      'CONFIRMED',
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
      'AT_WAREHOUSE',
      'TO_RESCHEDULE',
      name='orderstatus',
    ),
    existing_nullable=True,
  )
  op.drop_column('order', 'confirmed')

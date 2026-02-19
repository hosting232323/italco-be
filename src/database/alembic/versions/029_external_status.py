"""External status

Revision ID: 029
Revises: 028
Create Date: 2026-02-19 11:00:07.713340

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '029'
down_revision: Union[str, None] = '028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column(
    'order',
    sa.Column(
      'external_status',
      sa.Enum(
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
      nullable=True,
    ),
  )


def downgrade() -> None:
  op.drop_column('order', 'external_status')

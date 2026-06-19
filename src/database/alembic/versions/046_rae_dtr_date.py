"""Rae dtr date

Revision ID: 046
Revises: 045
Create Date: 2026-06-19 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '046'
down_revision: Union[str, None] = '045'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('rae_product', sa.Column('dtr_date', sa.Date(), nullable=True))

  op.execute("""
    WITH base AS (
      SELECT
        rp.id AS rae_product_id,
        s.date AS schedule_date,
        ROW_NUMBER() OVER (
          PARTITION BY rp.id
          ORDER BY s.id
        ) AS rn
      FROM rae_product rp
      JOIN "order" o ON o.id = rp.order_id
      JOIN schedule_item_order sio ON sio.order_id = o.id
      JOIN schedule_item si ON si.id = sio.schedule_item_id AND si.operation_type = 'ORDER'
      JOIN schedule s ON s.id = si.schedule_id
    )
    UPDATE rae_product rp
    SET dtr_date = base.schedule_date
    FROM base
    WHERE rp.id = base.rae_product_id AND base.rn = 1
  """)


def downgrade() -> None:
  op.drop_column('rae_product', 'dtr_date')

"""Link to rae product

Revision ID: 041
Revises: 040
Create Date: 2026-05-24 13:53:53.491107

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '041'
down_revision: Union[str, None] = '040'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('rae_product', sa.Column('link', sa.String(), nullable=True))
  op.add_column('rae_product', sa.Column('emission_date', sa.DateTime(), nullable=True))
  op.add_column('rae_product', sa.Column('number', sa.Integer(), nullable=True))
  op.add_column('rae_product', sa.Column('order_id', sa.Integer(), nullable=True))

  op.execute("""
    UPDATE rae_product rp
    SET order_id = p.order_id
    FROM product p
    WHERE p.rae_product_id = rp.id
  """)

  # Rae di Euronics Santa Caterina
  op.execute("""
    UPDATE rae_product
    SET order_id = 12038
    WHERE id IN (124, 118)
  """)

  # Rae di Idea Monopoli
  op.execute("""
    UPDATE rae_product
    SET order_id = 18003
    WHERE id IN (169, 191)
  """)

  op.execute("""
    WITH base AS (
      SELECT
        rp.id AS rae_product_id,
        s.created_at AS schedule_created_at,
        ROW_NUMBER() OVER (
          PARTITION BY s.id
          ORDER BY rp.id
        ) - 1 AS offset
      FROM rae_product rp
      JOIN product p ON p.rae_product_id = rp.id
      JOIN "order" o ON o.id = p.order_id
      JOIN schedule_item_order sio ON sio.order_id = o.id
      JOIN schedule_item si ON si.id = sio.schedule_item_id
      JOIN schedule s ON s.id = si.schedule_id
    )
    UPDATE rae_product rp
    SET emission_date = base.schedule_created_at + (base.offset || ' minutes')::interval,
        status = 'EMITTED'
    FROM base
    WHERE rp.id = base.rae_product_id
  """)

  op.execute("""
    WITH numbered AS (
      SELECT
        id,
        ROW_NUMBER() OVER (
          PARTITION BY user_id, EXTRACT(YEAR FROM created_at)
          ORDER BY created_at, id
        ) AS number
      FROM rae_product
      WHERE user_id IN (42, 43, 44, 45)
    )
    UPDATE rae_product rp
    SET number = numbered.number
    FROM numbered
    WHERE rp.id = numbered.id
  """)

  op.execute("""
    WITH ranked AS (
      SELECT
        rp.id AS rae_product_id,
        (
          SELECT COUNT(rp2.id)
          FROM rae_product rp2
          JOIN "order" o2 ON rp2.order_id = o2.id
          JOIN schedule_item_order sio2 ON sio2.order_id = o2.id
          JOIN schedule_item si2 ON si2.id = sio2.schedule_item_id
          JOIN schedule s2 ON s2.id = si2.schedule_id
          WHERE rp2.status != 'GENERATED'
            AND rp2.user_id = rp.user_id
            AND EXTRACT(YEAR FROM s2.date) = EXTRACT(YEAR FROM CURRENT_DATE)
            AND s2.date <= s.date
            AND (
              s2.date < s.date
              OR (s2.date = s.date AND rp2.emission_date <= rp.emission_date)
            )
        ) AS preceding_count
      FROM rae_product rp
      JOIN "order" o ON o.id = rp.order_id
      JOIN schedule_item_order sio ON sio.order_id = o.id
      JOIN schedule_item si ON si.id = sio.schedule_item_id
      JOIN schedule s ON s.id = si.schedule_id
      WHERE rp.user_id NOT IN (42, 43, 44, 45)
        AND rp.status != 'GENERATED'
    )
    UPDATE rae_product rp
    SET number = ranked.preceding_count + 1
    FROM ranked
    WHERE rp.id = ranked.rae_product_id
  """)

  op.alter_column('rae_product', 'order_id', nullable=False, existing_type=sa.Integer())
  op.create_foreign_key(None, 'rae_product', 'order', ['order_id'], ['id'])


def downgrade() -> None:
  op.drop_constraint('fk_rae_product_order', 'rae_product', type_='foreignkey')
  op.drop_column('rae_product', 'order_id')
  op.drop_column('rae_product', 'number')
  op.drop_column('rae_product', 'link')
  op.drop_column('rae_product', 'emission_date')

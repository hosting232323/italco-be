"""deduplicate service users and create shared rate limit counters

Revision ID: 066
Revises: 065
Create Date: 2026-10-26 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '066'
down_revision: Union[str, None] = '065'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  # Keep the most recently updated association (and therefore its current
  # customer price), move product references, then remove duplicate rows.
  op.execute(
    sa.text("""
    WITH ranked AS (
      SELECT id,
        FIRST_VALUE(id) OVER (
          PARTITION BY service_id, user_id
          ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
        ) AS keep_id,
        ROW_NUMBER() OVER (
          PARTITION BY service_id, user_id
          ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
        ) AS row_num
      FROM service_user
    )
    UPDATE product SET service_user_id = ranked.keep_id
    FROM ranked WHERE product.service_user_id = ranked.id AND ranked.row_num > 1
  """)
  )
  op.execute(
    sa.text("""
    WITH ranked AS (
      SELECT id, ROW_NUMBER() OVER (
        PARTITION BY service_id, user_id
        ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
      ) AS row_num
      FROM service_user
    )
    DELETE FROM service_user USING ranked
    WHERE service_user.id = ranked.id AND ranked.row_num > 1
  """)
  )
  op.create_unique_constraint('uq_service_user_service_user', 'service_user', ['service_id', 'user_id'])
  op.create_table(
    'rate_limit_counter',
    sa.Column('scope', sa.String(), nullable=False),
    sa.Column('ip', sa.String(), nullable=False),
    sa.Column('bucket_start', sa.BigInteger(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('scope', 'ip', 'bucket_start', name='uq_rate_limit_counter_scope_ip_bucket'),
  )


def downgrade() -> None:
  op.drop_table('rate_limit_counter')
  op.drop_constraint('uq_service_user_service_user', 'service_user', type_='unique')

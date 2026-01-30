"""update user info

Revision ID: 023
Revises: 022
Create Date: 2026-01-26 15:36:15.866135

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '023'
down_revision: Union[str, None] = '022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.alter_column('customer_user_info', 'city', existing_type=sa.String(), nullable=True)
  op.alter_column('customer_user_info', 'address', existing_type=sa.String(), nullable=True)
  op.alter_column('customer_user_info', 'tax_code', existing_type=sa.String(), nullable=True)
  op.alter_column('customer_user_info', 'company_name', existing_type=sa.String(), nullable=True)
  op.add_column('customer_user_info', sa.Column('email', sa.String(), nullable=True))
  op.execute("""
    INSERT INTO customer_user_info (user_id, email)
    SELECT id, email
    FROM "user"
    WHERE email IS NOT NULL
  """)
  op.drop_column('user', 'email')


def downgrade() -> None:
  op.add_column('user', sa.Column('email', sa.String(), autoincrement=False, nullable=True))
  op.execute("""
    UPDATE "user" u
    SET email = c.email
    FROM customer_user_info c
    WHERE u.id = c.user_id
  """)
  op.drop_column('customer_user_info', 'email')
  op.alter_column('customer_user_info', 'company_name', existing_type=sa.String(), nullable=False)
  op.alter_column('customer_user_info', 'tax_code', existing_type=sa.String(), nullable=False)
  op.alter_column('customer_user_info', 'address', existing_type=sa.String(), nullable=False)
  op.alter_column('customer_user_info', 'city', existing_type=sa.String(), nullable=False)

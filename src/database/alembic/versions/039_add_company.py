"""add company

Revision ID: 039
Revises: 038
Create Date: 2026-04-07 17:33:57.697326

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '039'
down_revision: Union[str, None] = '038'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'company',
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
  )

  op.add_column('service', sa.Column('user_id', sa.Integer(), nullable=True))

  op.execute("""
    UPDATE service
    SET user_id = (
      SELECT id FROM "user"
      WHERE nickname = 'admin'
      LIMIT 1
    )
  """)

  op.alter_column('service', 'user_id', nullable=False)
  op.create_foreign_key(None, 'service', 'user', ['user_id'], ['id'])

  op.add_column('user', sa.Column('company_id', sa.Integer(), nullable=True))

  op.execute("INSERT INTO company (name) VALUES ('Ares Logistics')")

  op.execute("""
    UPDATE "user"
    SET company_id = (SELECT id FROM company LIMIT 1)
  """)

  op.alter_column('user', 'company_id', nullable=False)
  op.create_foreign_key(None, 'user', 'company', ['company_id'], ['id'])

  op.execute("ALTER TYPE userrole ADD VALUE 'SUPER_ADMIN'")

  op.add_column('collection_point', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'collection_point', 'company', ['company_id'], ['id'])
  op.add_column('constraints', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'constraints', 'company', ['company_id'], ['id'])
  op.add_column('customer_group', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'customer_group', 'company', ['company_id'], ['id'])
  op.add_column('customer_rule', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'customer_rule', 'company', ['company_id'], ['id'])
  op.add_column('customer_user_info', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'customer_user_info', 'company', ['company_id'], ['id'])
  op.add_column('delivery_group', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'delivery_group', 'company', ['company_id'], ['id'])
  op.add_column('delivery_user_info', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'delivery_user_info', 'company', ['company_id'], ['id'])
  op.add_column('geographic_code', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'geographic_code', 'company', ['company_id'], ['id'])
  op.add_column('geographic_zone', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'geographic_zone', 'company', ['company_id'], ['id'])
  op.add_column('history', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'history', 'company', ['company_id'], ['id'])
  op.add_column('log', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'log', 'company', ['company_id'], ['id'])
  op.add_column('motivation', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'motivation', 'company', ['company_id'], ['id'])
  op.add_column('order', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'order', 'company', ['company_id'], ['id'])
  op.add_column('photo', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'photo', 'company', ['company_id'], ['id'])
  op.add_column('product', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'product', 'company', ['company_id'], ['id'])
  op.add_column('rae_product', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'rae_product', 'company', ['company_id'], ['id'])
  op.add_column('rae_product_group', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'rae_product_group', 'company', ['company_id'], ['id'])
  op.add_column('schedule', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'schedule', 'company', ['company_id'], ['id'])
  op.add_column('schedule_item', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'schedule_item', 'company', ['company_id'], ['id'])
  op.add_column('schedule_item_collection_point', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'schedule_item_collection_point', 'company', ['company_id'], ['id'])
  op.add_column('schedule_item_order', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'schedule_item_order', 'company', ['company_id'], ['id'])
  op.add_column('service', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'service', 'company', ['company_id'], ['id'])
  op.add_column('service_user', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'service_user', 'company', ['company_id'], ['id'])
  op.add_column('transport', sa.Column('company_id', sa.Integer(), nullable=False))
  op.create_foreign_key(None, 'transport', 'company', ['company_id'], ['id'])


def downgrade() -> None:
  op.drop_constraint(None, 'user', type_='foreignkey')
  op.drop_column('user', 'company_id')
  op.drop_constraint(None, 'service', type_='foreignkey')
  op.drop_column('service', 'user_id')
  op.drop_table('company')
  op.drop_constraint(None, 'transport', type_='foreignkey')
  op.drop_column('transport', 'company_id')
  op.drop_constraint(None, 'service_user', type_='foreignkey')
  op.drop_column('service_user', 'company_id')
  op.drop_constraint(None, 'service', type_='foreignkey')
  op.drop_column('service', 'company_id')
  op.drop_constraint(None, 'schedule_item_order', type_='foreignkey')
  op.drop_column('schedule_item_order', 'company_id')
  op.drop_constraint(None, 'schedule_item_collection_point', type_='foreignkey')
  op.drop_column('schedule_item_collection_point', 'company_id')
  op.drop_constraint(None, 'schedule_item', type_='foreignkey')
  op.drop_column('schedule_item', 'company_id')
  op.drop_constraint(None, 'schedule', type_='foreignkey')
  op.drop_column('schedule', 'company_id')
  op.drop_constraint(None, 'rae_product_group', type_='foreignkey')
  op.drop_column('rae_product_group', 'company_id')
  op.drop_constraint(None, 'rae_product', type_='foreignkey')
  op.drop_column('rae_product', 'company_id')
  op.drop_constraint(None, 'product', type_='foreignkey')
  op.drop_column('product', 'company_id')
  op.drop_constraint(None, 'photo', type_='foreignkey')
  op.drop_column('photo', 'company_id')
  op.drop_constraint(None, 'order', type_='foreignkey')
  op.drop_column('order', 'company_id')
  op.drop_constraint(None, 'motivation', type_='foreignkey')
  op.drop_column('motivation', 'company_id')
  op.drop_constraint(None, 'log', type_='foreignkey')
  op.drop_column('log', 'company_id')
  op.drop_constraint(None, 'history', type_='foreignkey')
  op.drop_column('history', 'company_id')
  op.drop_constraint(None, 'geographic_zone', type_='foreignkey')
  op.drop_column('geographic_zone', 'company_id')
  op.drop_constraint(None, 'geographic_code', type_='foreignkey')
  op.drop_column('geographic_code', 'company_id')
  op.drop_constraint(None, 'delivery_user_info', type_='foreignkey')
  op.drop_column('delivery_user_info', 'company_id')
  op.drop_constraint(None, 'delivery_group', type_='foreignkey')
  op.drop_column('delivery_group', 'company_id')
  op.drop_constraint(None, 'customer_user_info', type_='foreignkey')
  op.drop_column('customer_user_info', 'company_id')
  op.drop_constraint(None, 'customer_rule', type_='foreignkey')
  op.drop_column('customer_rule', 'company_id')
  op.drop_constraint(None, 'customer_group', type_='foreignkey')
  op.drop_column('customer_group', 'company_id')
  op.drop_constraint(None, 'constraints', type_='foreignkey')
  op.drop_column('constraints', 'company_id')
  op.drop_constraint(None, 'collection_point', type_='foreignkey')
  op.drop_column('collection_point', 'company_id')

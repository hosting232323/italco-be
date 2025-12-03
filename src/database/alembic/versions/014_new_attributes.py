"""new attributes

Revision ID: 014
Revises: 013
Create Date: 2025-12-05 12:10:39.296758

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table('customer_user',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('customer_group_id', sa.Integer(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['customer_group_id'], ['customer_group.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  op.create_table('delivery_user',
    sa.Column('lat', sa.Numeric(precision=11, scale=8), nullable=True),
    sa.Column('lon', sa.Numeric(precision=11, scale=8), nullable=True),
    sa.Column('location', sa.String(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  op.add_column('collection_point', sa.Column('customer_user_id', sa.Integer(), nullable=False))
  op.drop_constraint(op.f('collection_point_user_id_fkey'), 'collection_point', type_='foreignkey')
  op.create_foreign_key(None, 'collection_point', 'customer_user', ['customer_user_id'], ['id'])
  op.drop_column('collection_point', 'user_id')
  op.add_column('customer_rule', sa.Column('customer_user_id', sa.Integer(), nullable=False))
  op.drop_constraint(op.f('customer_rule_user_id_fkey'), 'customer_rule', type_='foreignkey')
  op.create_foreign_key(None, 'customer_rule', 'customer_user', ['customer_user_id'], ['id'])
  op.drop_column('customer_rule', 'user_id')
  op.add_column('service_user', sa.Column('customer_user_id', sa.Integer(), nullable=False))
  op.drop_constraint(op.f('service_user_user_id_fkey'), 'service_user', type_='foreignkey')
  op.create_foreign_key(None, 'service_user', 'customer_user', ['customer_user_id'], ['id'])
  op.drop_column('service_user', 'user_id')
  op.add_column('transport', sa.Column('location', sa.String(), nullable=True))
  op.drop_constraint(op.f('italco_user_customer_group_id_fkey'), 'user', type_='foreignkey')
  op.drop_column('user', 'lat')
  op.drop_column('user', 'lon')
  op.drop_column('user', 'customer_group_id')


def downgrade() -> None:
  op.add_column('user', sa.Column('customer_group_id', sa.INTEGER(), autoincrement=False, nullable=True))
  op.add_column('user', sa.Column('lon', sa.NUMERIC(precision=11, scale=8), autoincrement=False, nullable=True))
  op.add_column('user', sa.Column('lat', sa.NUMERIC(precision=11, scale=8), autoincrement=False, nullable=True))
  op.create_foreign_key(op.f('italco_user_customer_group_id_fkey'), 'user', 'customer_group', ['customer_group_id'], ['id'])
  op.drop_column('transport', 'location')
  op.add_column('service_user', sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False))
  op.drop_constraint(None, 'service_user', type_='foreignkey')
  op.create_foreign_key(op.f('service_user_user_id_fkey'), 'service_user', 'user', ['user_id'], ['id'])
  op.drop_column('service_user', 'customer_user_id')
  op.add_column('customer_rule', sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False))
  op.drop_constraint(None, 'customer_rule', type_='foreignkey')
  op.create_foreign_key(op.f('customer_rule_user_id_fkey'), 'customer_rule', 'user', ['user_id'], ['id'])
  op.drop_column('customer_rule', 'customer_user_id')
  op.add_column('collection_point', sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False))
  op.drop_constraint(None, 'collection_point', type_='foreignkey')
  op.create_foreign_key(op.f('collection_point_user_id_fkey'), 'collection_point', 'user', ['user_id'], ['id'])
  op.drop_column('collection_point', 'customer_user_id')
  op.drop_table('delivery_user')
  op.drop_table('customer_user')

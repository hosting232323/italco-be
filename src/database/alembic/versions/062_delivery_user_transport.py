"""Move delivery users onto vehicles and remove direct schedule assignment.

Revision ID: 062
Revises: 061

Delivery users belong to a vehicle through delivery_user_info.transport_id.
Schedules inherit their users from that vehicle, so delivery_group is removed.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '062'
down_revision: Union[str, None] = '061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('delivery_user_info', sa.Column('transport_id', sa.Integer(), nullable=True))
  op.create_foreign_key(
    'fk_delivery_user_info_transport_id', 'delivery_user_info', 'transport', ['transport_id'], ['id']
  )
  op.drop_table('delivery_group')


def downgrade() -> None:
  op.create_table(
    'delivery_group',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('schedule_id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id']),
    sa.ForeignKeyConstraint(['schedule_id'], ['schedule.id']),
    sa.ForeignKeyConstraint(['company_id'], ['company.id']),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('schedule_id', 'user_id', name='uq_delivery_group_schedule_user'),
  )
  op.drop_constraint('fk_delivery_user_info_transport_id', 'delivery_user_info', type_='foreignkey')
  op.drop_column('delivery_user_info', 'transport_id')

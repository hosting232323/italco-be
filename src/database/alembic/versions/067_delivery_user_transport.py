"""Move delivery users onto vehicles and remove direct schedule assignment.

Revision ID: 067
Revises: 066

Delivery users belong to a vehicle through delivery_user_info.transport_id.
Schedules inherit their users from that vehicle, so delivery_group is removed.
Before the drop each courier is attached to the vehicle of the latest schedule
they were assigned to, so production keeps the courier -> vehicle assignments.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '067'
down_revision: Union[str, None] = '066'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('delivery_user_info', sa.Column('transport_id', sa.Integer(), nullable=True))
  op.create_foreign_key(
    'fk_delivery_user_info_transport_id', 'delivery_user_info', 'transport', ['transport_id'], ['id']
  )
  # A courier who drove different vehicles takes the most recent one: if that is
  # wrong, the admin changes it.
  op.execute(
    """
    UPDATE delivery_user_info AS info
    SET transport_id = latest.transport_id
    FROM (
      SELECT DISTINCT ON (dg.user_id) dg.user_id, s.transport_id
      FROM delivery_group dg
      JOIN schedule s ON s.id = dg.schedule_id
      WHERE s.transport_id IS NOT NULL
      ORDER BY dg.user_id, s.date DESC, s.id DESC
    ) AS latest
    WHERE info.user_id = latest.user_id AND info.transport_id IS NULL
    """
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

"""via la relazione utenti delivery - borderò, orario di attività company, indirizzo sul veicolo

Revision ID: 064
Revises: 063
Create Date: 2026-09-23 12:00:00.000000

- Il borderò eredita i corrieri dal veicolo (delivery_user_info.transport_id):
  la tabella delivery_group non serve più.
- Company: aggiunte colonne activity_start_time e activity_end_time.
- Veicolo: aggiunta colonna address su transport; rimossa colonna cap da delivery_user_info.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '064'
down_revision: Union[str, None] = '063'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.drop_table('delivery_group')
  op.add_column('company', sa.Column('activity_start_time', sa.Time(), nullable=True))
  op.add_column('company', sa.Column('activity_end_time', sa.Time(), nullable=True))
  op.add_column('transport', sa.Column('address', sa.String(), nullable=True))
  op.drop_column('delivery_user_info', 'cap')


def downgrade() -> None:
  op.add_column('delivery_user_info', sa.Column('cap', sa.String(), nullable=True))
  op.drop_column('transport', 'address')
  op.drop_column('company', 'activity_end_time')
  op.drop_column('company', 'activity_start_time')
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

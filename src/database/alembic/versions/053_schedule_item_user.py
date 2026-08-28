"""schedule item user

Revision ID: 053
Revises: 052
Create Date: 2026-08-22 10:00:00.000000

Tabella nuova, creata dopo l'introduzione del tenant (050): company_id va
NOT NULL fin dalla create_table, senza il percorso nullable->backfill->vincolo
che serve solo alle tabelle preesistenti con dati.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '053'
down_revision: Union[str, None] = '052'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'schedule_item_user',
    sa.Column('type', sa.Enum('OPENING', 'CHANGE', 'CLOSING', name='scheduleitemusertype'), nullable=False),
    sa.Column('schedule_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(
      ['schedule_id'],
      ['schedule.id'],
    ),
    sa.ForeignKeyConstraint(
      ['user_id'],
      ['user.id'],
    ),
    sa.ForeignKeyConstraint(
      ['company_id'],
      ['company.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
  )


def downgrade() -> None:
  op.drop_table('schedule_item_user')

"""schedule item activity

Revision ID: 067
Revises: 066
Create Date: 2026-10-01 12:00:00.000000

Su questo branch (demo) la migration è la 067, non la 060 che ha su main: le
revisioni 060-066 sono già della demo e il database demo le ha applicate.

Nuovo tipo di tappa del borderò: l'attività libera (pausa, rifornimento,
contrattempo). Non punta a un ordine né a un punto di ritiro, quindi i suoi
dati stanno in una tabella propria agganciata a schedule_item.

Il valore di enum va nominato come il membro python (ACTIVITY), non come il
valore serializzato ('Activity'): vedi la trappola già incontrata su wooffy.
Un valore di enum appena aggiunto non è usabile nella stessa transazione che lo
aggiunge: qui non serve, ma ALTER TYPE ... ADD VALUE va comunque fuori
transazione, da cui l'autocommit_block.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '067'
down_revision: Union[str, None] = '066'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  with op.get_context().autocommit_block():
    op.execute("ALTER TYPE scheduletype ADD VALUE IF NOT EXISTS 'ACTIVITY'")

  op.create_table(
    'schedule_item_activity',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('note', sa.String(), nullable=True),
    sa.Column('address', sa.String(), nullable=True),
    sa.Column('cap', sa.String(), nullable=True),
    sa.Column('duration_minutes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('schedule_item_id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('duration_minutes >= 0', name='ck_schedule_item_activity_duration'),
    sa.ForeignKeyConstraint(['company_id'], ['company.id'], name='fk_schedule_item_activity_company_id'),
    sa.ForeignKeyConstraint(['schedule_item_id'], ['schedule_item.id']),
    sa.PrimaryKeyConstraint('id'),
  )
  op.create_index(
    op.f('ix_schedule_item_activity_schedule_item_id'), 'schedule_item_activity', ['schedule_item_id'], unique=False
  )


def downgrade() -> None:
  op.drop_index(op.f('ix_schedule_item_activity_schedule_item_id'), table_name='schedule_item_activity')
  op.drop_table('schedule_item_activity')
  # Il valore ACTIVITY resta nell'enum: Postgres non sa rimuovere un valore da un tipo.

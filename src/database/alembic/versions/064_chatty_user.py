"""chatty user

Revision ID: 064
Revises: 063
Create Date: 2026-10-16 12:00:00.000000

I thread di Chatty non avevano proprietario e GET /chatty/thread/<id> non
chiedeva il login: chiunque avesse l'id leggeva la conversazione, ordini
compresi. Da qui in avanti ogni thread appartiene all'utente che lo apre.

La colonna resta nullable: i thread gia' salvati non hanno un proprietario
ricostruibile e restano senza, quindi non piu' accessibili da nessuno.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '064'
down_revision: Union[str, None] = '063'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('chatty', sa.Column('user_id', sa.Integer(), nullable=True))
  op.create_foreign_key('chatty_user_id_fkey', 'chatty', 'user', ['user_id'], ['id'], ondelete='CASCADE')
  op.create_index('ix_chatty_user_id', 'chatty', ['user_id'])


def downgrade() -> None:
  op.drop_index('ix_chatty_user_id', table_name='chatty')
  op.drop_constraint('chatty_user_id_fkey', 'chatty', type_='foreignkey')
  op.drop_column('chatty', 'user_id')

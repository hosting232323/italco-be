"""indexes for the schedule list query

Revision ID: 055
Revises: 054
Create Date: 2026-09-01 14:00:00.000000

Indici sul percorso della pagina dei borderò, che dopo la riscrittura di
query_schedules gira in due passi: prima gli id, poi il dettaglio.

I due che portano il grosso:

- schedule (company_id, created_at DESC) è esattamente la chiave con cui
  query_schedule_ids sceglie gli ultimi N borderò dell'attività: Postgres
  percorre l'indice e si ferma dopo N invece di scansionare tutto l'archivio.
- schedule_item (schedule_id) serve all'EXISTS che scarta i borderò senza item.
  Senza, Postgres non ha modo di sondare la tabella e la aggrega tutta: su
  200.000 item misurati 12 secondi contro 3 millisecondi.

Gli altri tre sono gli indici sulle foreign key che la query di dettaglio
attraversa. Nessuna di queste colonne era indicizzata: PostgreSQL non crea
indici sulle foreign key da solo, e la migration 050 che le ha aggiunte tutte
non li ha messi.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '055'
down_revision: Union[str, None] = '054'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FOREIGN_KEY_INDEXES = (
  ('schedule_item', 'schedule_id'),
  ('schedule_item_order', 'schedule_item_id'),
  ('schedule_item_collection_point', 'schedule_item_id'),
  ('product', 'order_id'),
)

SCHEDULE_INDEX = 'ix_schedule_company_id_created_at'


def upgrade() -> None:
  op.create_index(SCHEDULE_INDEX, 'schedule', ['company_id', sa.text('created_at DESC')])
  for table, column in FOREIGN_KEY_INDEXES:
    op.create_index(op.f(f'ix_{table}_{column}'), table, [column])


def downgrade() -> None:
  for table, column in reversed(FOREIGN_KEY_INDEXES):
    op.drop_index(op.f(f'ix_{table}_{column}'), table_name=table)
  op.drop_index(SCHEDULE_INDEX, table_name='schedule')

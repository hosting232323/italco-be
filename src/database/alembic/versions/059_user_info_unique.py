"""user info unique per user

Revision ID: 059
Revises: 058
Create Date: 2026-09-15 12:00:00.000000

customer_user_info e delivery_user_info devono avere una sola riga per utente,
ma nessun vincolo lo imponeva. Le righe doppie sono nate in due modi:
- la migrazione 023 ha inserito una riga con la sola email per ogni utente,
  anche per chi una scheda l'aveva già;
- save_user_info leggeva e poi creava: due posizioni GPS simultanee dello
  stesso corriere trovavano entrambe "nessuna scheda" e ne creavano due.

Chi legge prende la prima riga senza ordinamento, quindi con i doppioni la
pagina Punti Vendita, il DDT RAEE e le email potevano usare la scheda vuota.

La migrazione non sceglie da sola quale riga tenere: due schede dello stesso
utente possono avere dati diversi, e decidere è un lavoro da fare a mano. Se
trova doppioni si ferma elencandoli; una volta ripuliti aggiunge il vincolo.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '059'
down_revision: Union[str, None] = '058'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = ('customer_user_info', 'delivery_user_info')


def upgrade() -> None:
  bind = op.get_bind()

  duplicates = {}
  for table in TABLES:
    rows = bind.execute(
      sa.text(f'SELECT user_id, array_agg(id ORDER BY id) FROM {table} GROUP BY user_id HAVING count(*) > 1')
    ).all()
    if rows:
      duplicates[table] = {user_id: ids for user_id, ids in rows}

  if duplicates:
    details = '; '.join(
      f'{table}: ' + ', '.join(f'user_id {user_id} -> id {ids}' for user_id, ids in rows.items())
      for table, rows in duplicates.items()
    )
    raise RuntimeError(f'Schede utente doppie da ripulire a mano prima del vincolo di unicità: {details}')

  for table in TABLES:
    op.create_unique_constraint(f'uq_{table}_user_id', table, ['user_id'])


def downgrade() -> None:
  for table in reversed(TABLES):
    op.drop_constraint(f'uq_{table}_user_id', table, type_='unique')

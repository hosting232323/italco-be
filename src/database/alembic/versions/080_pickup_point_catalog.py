"""catalogo unificato dei punti di ritiro

079
Create Date: 2026-11-18 10:00:00.000000

pickup_point: indirizzi di ritiro condivisi fra i clienti. Ogni collection_point
punta a una voce (pickup_point_id). Il backfill unifica i punti esistenti con lo
stesso indirizzo e CAP nella stessa company.
"""

import re
from collections import Counter
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '080'
down_revision: Union[str, None] = '079'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _key(address: str, cap: str) -> tuple:
  # Parole ordinate: "99 via X" e "via X 99" sono lo stesso indirizzo.
  words = sorted(re.sub(r'[\W_]+', ' ', (address or '').lower()).split())
  return (' '.join(words), (cap or '').strip())


def upgrade() -> None:
  op.create_table(
    'pickup_point',
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('address', sa.String(), nullable=False),
    sa.Column('cap', sa.String(), nullable=False),
    sa.Column('lat', sa.Float(), nullable=True),
    sa.Column('lon', sa.Float(), nullable=True),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['company.id']),
    sa.PrimaryKeyConstraint('id'),
  )
  op.add_column('collection_point', sa.Column('pickup_point_id', sa.Integer(), nullable=True))
  op.create_index(op.f('ix_collection_point_pickup_point_id'), 'collection_point', ['pickup_point_id'], unique=False)
  op.create_foreign_key(
    'fk_collection_point_pickup_point', 'collection_point', 'pickup_point', ['pickup_point_id'], ['id']
  )

  connection = op.get_bind()
  rows = connection.execute(
    sa.text('SELECT id, company_id, name, address, cap, lat, lon FROM collection_point ORDER BY id')
  ).fetchall()
  groups: dict[tuple, list] = {}
  for row in rows:
    groups.setdefault((row.company_id, *_key(row.address, row.cap)), []).append(row)

  for (company_id, _, _), points in groups.items():
    name = Counter((point.name or '').strip() for point in points).most_common(1)[0][0]
    first = points[0]
    located = next((point for point in points if point.lat is not None and point.lon is not None), None)
    pickup_point_id = connection.execute(
      sa.text(
        'INSERT INTO pickup_point (name, address, cap, lat, lon, company_id, created_at, updated_at) '
        'VALUES (:name, :address, :cap, :lat, :lon, :company_id, now(), now()) RETURNING id'
      ),
      {
        'name': name,
        'address': first.address,
        'cap': first.cap,
        'lat': located.lat if located else None,
        'lon': located.lon if located else None,
        'company_id': company_id,
      },
    ).scalar()
    connection.execute(
      sa.text('UPDATE collection_point SET pickup_point_id = :pp WHERE id = ANY(:ids)'),
      {'pp': pickup_point_id, 'ids': [point.id for point in points]},
    )


def downgrade() -> None:
  op.drop_constraint('fk_collection_point_pickup_point', 'collection_point', type_='foreignkey')
  op.drop_index(op.f('ix_collection_point_pickup_point_id'), table_name='collection_point')
  op.drop_column('collection_point', 'pickup_point_id')
  op.drop_table('pickup_point')

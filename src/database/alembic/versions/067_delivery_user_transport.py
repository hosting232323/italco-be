"""Move delivery users onto vehicles and remove direct schedule assignment.

Revision ID: 067
Revises: 066

Delivery users belong to a vehicle through delivery_user_info.transport_id.
Schedules inherit their users from that vehicle, so delivery_group is removed.
Before the drop each courier is attached to the vehicle of the latest schedule
they were assigned to, so production keeps the courier -> vehicle assignments.

On the production database the pairing agreed on test is then applied on top:
vehicle 13 becomes VEICOLO 1, VEICOLO 2 and 3 are created and every courier gets
the vehicle it has on test. Production is recognised by vehicle 13 still having
the plate FJ-337-GV: any other database keeps only the backfill above.

Last, past schedules that share a vehicle on the same day are separated: a vehicle
can have a single schedule per day now, so the extra ones move, at random, to a
vehicle that has no schedule that day. Past couriers are not preserved, a schedule
shows the current ones of its vehicle.
"""

import random
from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '067'
down_revision: Union[str, None] = '066'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRODUCTION_PLATE = 'FJ-337-GV'

# (id, name, plate, cap, company_id): vehicle 13 is renamed, 14 and 15 are new.
TRANSPORTS = [
  (13, 'VEICOLO 1', 'VEICOLO 1', '70026', 2),
  (14, 'VEICOLO 2', 'VEICOLO 2', '70026', 2),
  (15, 'VEICOLO 3', 'VEICOLO 3', '70026', 2),
]

# (user_id, transport_id, company_id): None = courier without a vehicle.
COURIER_TRANSPORTS = [
  (3, None, 1),
  (5, 4, 1),
  (6, 4, 1),
  (7, None, 1),
  (17, 5, 1),
  (19, 5, 1),
  (25, None, 1),
  (26, 6, 1),
  (27, 6, 1),
  (29, None, 1),
  (31, None, 1),
  (33, 7, 1),
  (35, 7, 1),
  (36, 8, 1),
  (38, 8, 1),
  (40, None, 1),
  (41, None, 1),
  (47, 3, 1),
  (48, 3, 1),
  (49, 11, 1),
  (50, None, 1),
  (51, None, 1),
  (52, 9, 1),
  (54, 11, 1),
  (57, 10, 1),
  (58, 10, 1),
  (59, 9, 1),
  (60, None, 1),
  (62, 12, 1),
  (63, 12, 1),
  (76, 15, 2),
  (77, 13, 2),
  (78, None, 2),
  (79, 14, 2),
  (80, None, 2),
  (81, 14, 2),
]


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
  apply_production_pairing()
  separate_overlapping_schedules()
  op.drop_table('delivery_group')


def apply_production_pairing() -> None:
  bind = op.get_bind()
  is_production = bind.execute(
    sa.text('SELECT 1 FROM transport WHERE id = 13 AND plate = :plate'), {'plate': PRODUCTION_PLATE}
  ).first()
  if not is_production:
    return

  for transport_id, name, plate, cap, company_id in TRANSPORTS:
    params = {'id': transport_id, 'name': name, 'plate': plate, 'cap': cap, 'company_id': company_id}
    bind.execute(sa.text('UPDATE transport SET name = :name, plate = :plate, cap = :cap WHERE id = :id'), params)
    bind.execute(
      sa.text(
        """
        INSERT INTO transport (id, name, plate, cap, company_id, created_at, updated_at)
        SELECT :id, :name, :plate, :cap, :company_id, now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM transport WHERE id = :id)
        """
      ),
      params,
    )
  bind.execute(sa.text("SELECT setval('transport_id_seq', (SELECT max(id) FROM transport))"))

  for user_id, transport_id, company_id in COURIER_TRANSPORTS:
    params = {'user_id': user_id, 'transport_id': transport_id, 'company_id': company_id}
    bind.execute(sa.text('UPDATE delivery_user_info SET transport_id = :transport_id WHERE user_id = :user_id'), params)
    # A courier without an info row would lose the vehicle, so the row is created.
    if transport_id is not None:
      bind.execute(
        sa.text(
          """
          INSERT INTO delivery_user_info (user_id, company_id, transport_id, created_at, updated_at)
          SELECT :user_id, :company_id, :transport_id, now(), now()
          WHERE EXISTS (SELECT 1 FROM "user" WHERE id = :user_id)
            AND NOT EXISTS (SELECT 1 FROM delivery_user_info WHERE user_id = :user_id)
          """
        ),
        params,
      )


def separate_overlapping_schedules() -> None:
  bind = op.get_bind()
  rng = random.Random(0)
  transport_ids = [row[0] for row in bind.execute(sa.text('SELECT id FROM transport ORDER BY id'))]
  by_date = defaultdict(list)
  for schedule_id, schedule_date, transport_id in bind.execute(
    sa.text('SELECT id, date, transport_id FROM schedule ORDER BY date, id')
  ):
    by_date[schedule_date].append((schedule_id, transport_id))

  for schedules in by_date.values():
    used = set()
    to_move = []
    for schedule_id, transport_id in schedules:
      if transport_id in used:
        to_move.append(schedule_id)
      else:
        used.add(transport_id)

    for schedule_id in to_move:
      free = [transport_id for transport_id in transport_ids if transport_id not in used]
      # No free vehicle: the schedule stays where it is rather than failing the deploy.
      if not free:
        continue
      chosen = rng.choice(free)
      used.add(chosen)
      bind.execute(
        sa.text('UPDATE schedule SET transport_id = :transport_id WHERE id = :id'),
        {'transport_id': chosen, 'id': schedule_id},
      )


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
  # Only the vehicle 13 name goes back: the pairing is data, not schema.
  op.execute(
    """
    UPDATE transport SET name = 'FJ-337-GV', plate = 'FJ-337-GV'
    WHERE id = 13 AND plate = 'VEICOLO 1' AND company_id = 2
    """
  )

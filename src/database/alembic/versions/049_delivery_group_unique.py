"""delivery group unique constraint

Revision ID: 049
Revises: 048
Create Date: 2026-07-18 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = '049'
down_revision: Union[str, None] = '048'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  # Rimuove eventuali duplicati preesistenti tenendo la riga più vecchia,
  # altrimenti la creazione del vincolo fallirebbe.
  op.execute(
    'DELETE FROM delivery_group a USING delivery_group b '
    'WHERE a.id > b.id AND a.schedule_id = b.schedule_id AND a.user_id = b.user_id'
  )
  op.create_unique_constraint('uq_delivery_group_schedule_user', 'delivery_group', ['schedule_id', 'user_id'])


def downgrade() -> None:
  op.drop_constraint('uq_delivery_group_schedule_user', 'delivery_group', type_='unique')

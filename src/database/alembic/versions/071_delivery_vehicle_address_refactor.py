"""orario di attività company, indirizzo sul veicolo

Revision ID: 071
Revises: 070
Create Date: 2026-09-23 12:00:00.000000

- Company: aggiunte colonne activity_start_time e activity_end_time.
- Veicolo: aggiunta colonna address su transport; rimossa colonna cap da delivery_user_info.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '071'
down_revision: Union[str, None] = '070'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('company', sa.Column('activity_start_time', sa.Time(), nullable=True))
  op.add_column('company', sa.Column('activity_end_time', sa.Time(), nullable=True))
  op.add_column('transport', sa.Column('address', sa.String(), nullable=True))
  op.drop_column('delivery_user_info', 'cap')


def downgrade() -> None:
  op.add_column('delivery_user_info', sa.Column('cap', sa.String(), nullable=True))
  op.drop_column('transport', 'address')
  op.drop_column('company', 'activity_end_time')
  op.drop_column('company', 'activity_start_time')

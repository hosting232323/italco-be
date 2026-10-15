"""user.email e customer_user_info.name migrato dal nickname

Revision ID: 065
Revises: 064
Create Date: 2026-10-15 10:00:00.000000

Il nickname resta l'identificativo di login, l'email è facoltativa e unica.
Per i punti vendita il nickname faceva anche da nome in filtri e select: il
nome diventa un campo della scheda punto vendita, inizializzato col nickname
corrente; i punti vendita senza scheda ne ricevono una.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '065'
down_revision: Union[str, None] = '064'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column('user', sa.Column('email', sa.String(), nullable=True))
  op.create_unique_constraint('user_email_key', 'user', ['email'])

  op.add_column('customer_user_info', sa.Column('name', sa.String(), nullable=True))
  op.execute(
    """
    UPDATE customer_user_info
    SET name = "user".nickname
    FROM "user"
    WHERE "user".id = customer_user_info.user_id
    """
  )
  op.execute(
    """
    INSERT INTO customer_user_info (user_id, company_id, name, created_at, updated_at)
    SELECT id, company_id, nickname, now(), now()
    FROM "user"
    WHERE role = 'CUSTOMER'
      AND company_id IS NOT NULL
      AND id NOT IN (SELECT user_id FROM customer_user_info)
    """
  )


def downgrade() -> None:
  op.drop_column('customer_user_info', 'name')
  op.drop_constraint('user_email_key', 'user', type_='unique')
  op.drop_column('user', 'email')

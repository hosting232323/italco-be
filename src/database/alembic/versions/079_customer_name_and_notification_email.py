"""customer_user_info.name migrato dal nickname e notification_email

Revision ID: 079
Revises: 078
Create Date: 2026-11-13 10:00:00.000000

Per i punti vendita il nickname faceva anche da nome in filtri e select: il
nome diventa un campo della scheda punto vendita, inizializzato col nickname
corrente; i punti vendita senza scheda ne ricevono una.
Accanto alla mail del punto vendita si aggiunge una mail dedicata alle
notifiche degli ordini, facoltativa.

"""

from typing import Sequence, Union

from alembic import op


revision: str = '079'
down_revision: Union[str, None] = '078'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  # Idempotente: gli ambienti che hanno girato feat/user-nickname-to-email
  # hanno già customer_user_info.name con la stessa revision.
  op.execute('ALTER TABLE customer_user_info ADD COLUMN IF NOT EXISTS name VARCHAR')
  op.execute('ALTER TABLE customer_user_info ADD COLUMN IF NOT EXISTS notification_email VARCHAR')
  op.execute(
    """
    UPDATE customer_user_info
    SET name = "user".nickname
    FROM "user"
    WHERE "user".id = customer_user_info.user_id
      AND customer_user_info.name IS NULL
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
  op.drop_column('customer_user_info', 'notification_email')
  op.drop_column('customer_user_info', 'name')

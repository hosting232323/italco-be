"""user.email e customer_user_info.name migrato dal nickname

Revision ID: 066
Revises: 065
Create Date: 2026-10-15 10:00:00.000000

Il nickname resta l'identificativo di login, l'email è facoltativa e unica.
Per i punti vendita il nickname faceva anche da nome in filtri e select: il
nome diventa un campo della scheda punto vendita, inizializzato col nickname
corrente; i punti vendita senza scheda ne ricevono una.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '066'
down_revision: Union[str, None] = '065'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  # Idempotente: alcuni ambienti hanno gia' queste colonne, applicate quando la
  # migration si chiamava 065 (poi ceduta a schedule_version).
  op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS email VARCHAR')
  op.execute(
    """
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_email_key') THEN
        ALTER TABLE "user" ADD CONSTRAINT user_email_key UNIQUE (email);
      END IF;
    END $$
    """
  )

  op.execute('ALTER TABLE customer_user_info ADD COLUMN IF NOT EXISTS name VARCHAR')
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
  op.drop_column('customer_user_info', 'name')
  op.drop_constraint('user_email_key', 'user', type_='unique')
  op.drop_column('user', 'email')

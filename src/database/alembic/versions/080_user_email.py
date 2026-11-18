"""user.email facoltativa e unica

Revision ID: 080
Revises: 079
Create Date: 2026-10-15 10:00:00.000000

Il nickname resta l'identificativo di login, l'email è facoltativa e unica.
Il nome del punto vendita migrato dal nickname è nella 079 di main.

"""

from typing import Sequence, Union

from alembic import op


revision: str = '080'
down_revision: Union[str, None] = '079'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  # Idempotente: alcuni ambienti hanno gia' la colonna, applicata quando la
  # migration era la 065 o la 079 di questo branch.
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


def downgrade() -> None:
  op.drop_constraint('user_email_key', 'user', type_='unique')
  op.drop_column('user', 'email')

"""user.email, customer_user_info.name migrato dal nickname e company_mail

Revision ID: 068
Revises: 067
Create Date: 2026-10-15 10:00:00.000000

Il nickname resta l'identificativo di login, l'email è facoltativa e unica.
Per i punti vendita il nickname faceva anche da nome in filtri e select: il
nome diventa un campo della scheda punto vendita, inizializzato col nickname
corrente; i punti vendita senza scheda ne ricevono una.

company_mail: le email di anomalia andavano a indirizzi scritti nel codice, ora
ogni attivita' ha la sua lista, configurata dal suo admin. Alla creazione della
tabella ogni attivita' esistente riceve come lista iniziale l'indirizzo che
prima era fisso, per non interrompere le notifiche in produzione.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '068'
down_revision: Union[str, None] = '067'
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

  bind = op.get_bind()
  if not sa.inspect(bind).has_table('company_mail'):
    op.create_table(
      'company_mail',
      sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
      sa.Column('company_id', sa.Integer(), nullable=False),
      sa.Column('email', sa.String(), nullable=False),
      sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
      sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
      sa.ForeignKeyConstraint(['company_id'], ['company.id'], name='fk_company_mail_company_id'),
      sa.PrimaryKeyConstraint('id'),
      sa.UniqueConstraint('company_id', 'email', name='company_mail_company_id_email_key'),
    )
    op.execute(
      """
      INSERT INTO company_mail (company_id, email, created_at, updated_at)
      SELECT id, 'coppolagabriele973@gmail.com', now(), now() FROM company
      """
    )


def downgrade() -> None:
  op.drop_table('company_mail')
  op.drop_column('customer_user_info', 'name')
  op.drop_constraint('user_email_key', 'user', type_='unique')
  op.drop_column('user', 'email')

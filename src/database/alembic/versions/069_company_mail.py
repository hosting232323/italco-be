"""company_mail: destinatari delle email di anomalia per attività

Revision ID: 069
Revises: 068
Create Date: 2026-10-30 10:00:00.000000

Gli indirizzi che ricevevano le email di anomalia erano scritti nel codice e
valevano per tutte le attività. Ora ogni attività ha la sua lista, configurata
dal suo admin. Per non interrompere le notifiche in produzione, ogni attività
esistente riceve come lista iniziale l'indirizzo che prima era fisso.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '069'
down_revision: Union[str, None] = '068'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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

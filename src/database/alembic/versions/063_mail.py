"""mail

Revision ID: 063
Revises: 062
Create Date: 2026-10-06 12:00:00.000000

Archivio delle email generate da richieste pubbliche (per ora le richieste di
demo della landing): la richiesta viene salvata prima dell'invio, cosi' un
contatto non va perso se l'SMTP e' giu'. Stessa tabella di generic-be.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '063'
down_revision: Union[str, None] = '062'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'mail',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('origin', sa.String(), nullable=True),
    sa.Column('recipient', sa.String(), nullable=False),
    sa.Column('subject', sa.String(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
  )


def downgrade() -> None:
  op.drop_table('mail')

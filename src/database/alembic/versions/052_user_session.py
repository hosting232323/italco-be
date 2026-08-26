"""user session table for refresh token rotation

Revision ID: 052
Revises: 051
Create Date: 2026-07-26 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '052'
down_revision: Union[str, None] = '051'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'user_session',
    sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
    sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
    sa.Column('token_hash', sa.String(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked', sa.Boolean(), nullable=False, server_default=sa.false()),
    # Valorizzata solo dalla rotazione: la finestra di grazia sul refresh non si
    # applica ai token revocati da logout o reset password.
    sa.Column('rotated_at', sa.DateTime(timezone=True), nullable=True),
    # Tutte le rotazioni discendenti da uno stesso login condividono la famiglia:
    # e' cio' che lega un token alla propria catena.
    sa.Column('family_id', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
  )
  op.create_index('ix_user_session_token_hash', 'user_session', ['token_hash'], unique=True)
  op.create_index('ix_user_session_user_id', 'user_session', ['user_id'])
  op.create_index('ix_user_session_family_id', 'user_session', ['family_id'])


def downgrade() -> None:
  op.drop_index('ix_user_session_family_id', table_name='user_session')
  op.drop_index('ix_user_session_user_id', table_name='user_session')
  op.drop_index('ix_user_session_token_hash', table_name='user_session')
  op.drop_table('user_session')

"""Motivation

Revision ID: 981eba745ab5
Revises: 9b11ccdaf5ad
Create Date: 2025-09-29 16:34:36.149158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '981eba745ab5'
down_revision: Union[str, None] = '9b11ccdaf5ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table('motivation',
    sa.Column('id_order', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'IN_PROGRESS', 'ON_BOARD', 'COMPLETED', 'CANCELLED', 'AT_WAREHOUSE', name='orderstatus'), nullable=False),
    sa.Column('delay', sa.Boolean(), nullable=True),
    sa.Column('anomaly', sa.Boolean(), nullable=True),
    sa.Column('text', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['id_order'], ['order.id'], ),
    sa.PrimaryKeyConstraint('id')
  )
  connection = op.get_bind()
  orders = connection.execute(sa.text("SELECT id, motivation, status, delay, anomaly FROM 'order' WHERE motivation IS NOT NULL")).fetchall()
  for order in orders:
    connection.execute(
      sa.text(
        "INSERT INTO motivation (id_order, text, status, delay, anomaly, created_at, updated_at) "
        "VALUES (:id_order, :text, :status, :delay, :anomaly, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
      ),
      {"id_order": order.id, "text": order.motivation, "status": order.status, "delay": order.delay, "anomaly": order.anomaly}
    )
  op.drop_column('order', 'motivation')


def downgrade() -> None:
  op.add_column('order', sa.Column('motivation', sa.VARCHAR(), autoincrement=False, nullable=True))
  connection = op.get_bind()
  motivations = connection.execute(sa.text("SELECT id_order, text FROM motivation")).fetchall()
  for m in motivations:
    connection.execute(
      sa.text("UPDATE 'order' SET motivation=:text WHERE id=:id_order"),
      {"text": m.text, "id_order": m.id_order}
    )
  op.drop_table('motivation')

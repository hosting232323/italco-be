"""update rae

Revision ID: 042
Revises: 041
Create Date: 2026-06-09 13:07:38.803297

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '042'
down_revision: Union[str, None] = '041'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'carrier',
    sa.Column('company_name', sa.String(), nullable=True),
    sa.Column('address', sa.String(), nullable=True),
    sa.Column('fiscal_code', sa.String(), nullable=True),
    sa.Column('vat_number', sa.String(), nullable=True),
    sa.Column('authorization_code', sa.String(), nullable=True),
    sa.Column('authorization_date', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
  )
  op.create_table(
    'collection_center',
    sa.Column('company_name', sa.String(), nullable=True),
    sa.Column('address', sa.String(), nullable=True),
    sa.Column('fiscal_code', sa.String(), nullable=True),
    sa.Column('vat_number', sa.String(), nullable=True),
    sa.Column('authorization_code', sa.String(), nullable=True),
    sa.Column('authorization_date', sa.String(), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
  )
  op.create_table(
    'disposal',
    sa.Column('date', sa.DateTime(), nullable=True),
    sa.Column('code', sa.String(), nullable=True),
    sa.Column('document_ldr', sa.String(), nullable=True),
    sa.Column('carrier_id', sa.Integer(), nullable=False),
    sa.Column('collection_center_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(
      ['carrier_id'],
      ['carrier.id'],
    ),
    sa.ForeignKeyConstraint(
      ['collection_center_id'],
      ['collection_center.id'],
    ),
    sa.PrimaryKeyConstraint('id'),
  )
  op.add_column('rae_product', sa.Column('disposal_id', sa.Integer(), nullable=True))
  op.create_foreign_key(None, 'rae_product', 'disposal', ['disposal_id'], ['id'])


def downgrade() -> None:
  op.drop_constraint(None, 'rae_product', type_='foreignkey')
  op.drop_column('rae_product', 'disposal_id')
  op.drop_table('disposal')
  op.drop_table('collection_center')
  op.drop_table('carrier')

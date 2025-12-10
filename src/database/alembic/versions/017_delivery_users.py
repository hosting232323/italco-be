"""Delivery users

Revision ID: 017
Revises: 016
Create Date: 2025-12-10 20:12:46.125304

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '017'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    'delivery_user',
    sa.Column('lat', sa.Numeric(precision=11, scale=8), nullable=True),
    sa.Column('lon', sa.Numeric(precision=11, scale=8), nullable=True),
    sa.Column('location', sa.String(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id']),
    sa.PrimaryKeyConstraint('id'),
  )

  conn = op.get_bind()
  delivery_users = conn.execute(
    sa.text("""
    SELECT id, lat, lon
    FROM "user"
    WHERE role = 'DELIVERY'
  """)
  ).fetchall()
  for u in delivery_users:
    conn.execute(
      sa.text("""
      INSERT INTO delivery_user (lat, lon, location, user_id, created_at, updated_at)
      VALUES (:lat, :lon, :location, :user_id, NOW(), NOW())
    """),
      {'lat': u.lat, 'lon': u.lon, 'location': '', 'user_id': u.id},
    )

  op.add_column('delivery_group', sa.Column('delivery_user_id', sa.Integer(), nullable=True))
  for u in delivery_users:
    conn.execute(
      sa.text("""
      UPDATE delivery_group
      SET delivery_user_id = (
        SELECT id FROM delivery_user WHERE user_id = :uid
      )
      WHERE user_id = :uid
    """),
      {'uid': u.id},
    )

  op.alter_column('delivery_group', 'delivery_user_id', nullable=False)
  op.drop_constraint(op.f('fk_delivery_group_user'), 'delivery_group', type_='foreignkey')
  op.create_foreign_key(None, 'delivery_group', 'delivery_user', ['delivery_user_id'], ['id'])
  op.drop_column('delivery_group', 'user_id')
  op.drop_column('user', 'lon')
  op.drop_column('user', 'lat')


def downgrade() -> None:
  op.add_column('user', sa.Column('lat', sa.NUMERIC(precision=11, scale=8), autoincrement=False, nullable=True))
  op.add_column('user', sa.Column('lon', sa.NUMERIC(precision=11, scale=8), autoincrement=False, nullable=True))
  op.add_column('delivery_group', sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False))
  op.drop_constraint(None, 'delivery_group', type_='foreignkey')
  op.create_foreign_key(op.f('fk_delivery_group_user'), 'delivery_group', 'user', ['user_id'], ['id'])
  op.drop_column('delivery_group', 'delivery_user_id')
  op.drop_table('delivery_user')

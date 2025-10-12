"""update delivery group

Revision ID: 6e5bf22fe99a
Revises: 981eba745ab5
Create Date: 2025-10-09 16:04:31.031537

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6e5bf22fe99a'
down_revision: Union[str, None] = '981eba745ab5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Aggiungi nuove colonne
    op.add_column('delivery_group', sa.Column('schedule_id', sa.Integer(), nullable=True))
    op.add_column('delivery_group', sa.Column('italco_user_id', sa.Integer(), nullable=True))

    # 2. Crea FK
    op.create_foreign_key('fk_delivery_group_schedule', 'delivery_group', 'schedule', ['schedule_id'], ['id'])
    op.create_foreign_key('fk_delivery_group_italco_user', 'delivery_group', 'italco_user', ['italco_user_id'], ['id'])

    # 3. Aggiungi lat/lon all'italco_user
    op.add_column('italco_user', sa.Column('lat', sa.Numeric(precision=11, scale=8), nullable=True))
    op.add_column('italco_user', sa.Column('lon', sa.Numeric(precision=11, scale=8), nullable=True))

    # 4. Sposta i dati di lat/lon da delivery_group a italco_user
    op.execute("""
        UPDATE italco_user
        SET lat = dg.lat, lon = dg.lon
        FROM delivery_group dg
        WHERE italco_user.delivery_group_id = dg.id
    """)

    # 5. Imposta valori temporanei per schedule_id e italco_user_id
    op.execute("""
        UPDATE delivery_group
        SET italco_user_id = iu.id
        FROM italco_user iu
        WHERE iu.delivery_group_id = delivery_group.id
    """)
    op.execute("""
        UPDATE delivery_group
        SET schedule_id = (SELECT id FROM schedule LIMIT 1)
        WHERE schedule_id IS NULL
    """)

    # 6. Elimina le colonne vecchie (solo dopo aver copiato i dati)
    op.drop_column('delivery_group', 'lat')
    op.drop_column('delivery_group', 'lon')
    op.drop_column('delivery_group', 'name')

    # 7. Rimuovi i vecchi collegamenti FK
    op.drop_constraint('italco_user_delivery_group_id_fkey', 'italco_user', type_='foreignkey')
    op.drop_column('italco_user', 'delivery_group_id')
    op.drop_constraint('schedule_delivery_group_id_fkey', 'schedule', type_='foreignkey')
    op.drop_column('schedule', 'delivery_group_id')

    # 8. Imposta le nuove colonne come NOT NULL (solo alla fine)
    op.alter_column('delivery_group', 'schedule_id', nullable=False)
    op.alter_column('delivery_group', 'italco_user_id', nullable=False)


def downgrade() -> None:
    # 1. Riaggiungi le colonne rimosse da delivery_group
    op.add_column('delivery_group', sa.Column('name', sa.VARCHAR(), nullable=True))
    op.add_column('delivery_group', sa.Column('lon', sa.Numeric(precision=11, scale=8), nullable=True))
    op.add_column('delivery_group', sa.Column('lat', sa.Numeric(precision=11, scale=8), nullable=True))

    # 2. Riaggiungi delivery_group_id su italco_user e schedule
    op.add_column('italco_user', sa.Column('delivery_group_id', sa.Integer(), nullable=True))
    op.add_column('schedule', sa.Column('delivery_group_id', sa.Integer(), nullable=True))

    # 3. Ricrea le FK precedenti
    op.create_foreign_key('italco_user_delivery_group_id_fkey', 'italco_user', 'delivery_group', ['delivery_group_id'], ['id'])
    op.create_foreign_key('schedule_delivery_group_id_fkey', 'schedule', 'delivery_group', ['delivery_group_id'], ['id'])

    # 4. Copia indietro i dati di lat/lon da italco_user a delivery_group
    op.execute("""
        UPDATE delivery_group
        SET lat = iu.lat, lon = iu.lon
        FROM italco_user iu
        WHERE iu.delivery_group_id = delivery_group.id
    """)

    # 5. Imposta un nome di fallback per evitare errori NOT NULL
    op.execute("UPDATE delivery_group SET name = 'Recovered Group' WHERE name IS NULL")

    # 6. Rimuovi le FK create in upgrade
    op.drop_constraint('fk_delivery_group_schedule', 'delivery_group', type_='foreignkey')
    op.drop_constraint('fk_delivery_group_italco_user', 'delivery_group', type_='foreignkey')

    # 7. Rimuovi le colonne aggiunte in upgrade
    op.drop_column('delivery_group', 'italco_user_id')
    op.drop_column('delivery_group', 'schedule_id')

    # 8. Rimuovi lat/lon da italco_user
    op.drop_column('italco_user', 'lon')
    op.drop_column('italco_user', 'lat')

    # 9. Rendi name NOT NULL di nuovo
    op.alter_column('delivery_group', 'name', nullable=False)

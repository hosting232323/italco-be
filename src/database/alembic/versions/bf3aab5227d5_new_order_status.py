"""new_order_status

Revision ID: bf3aab5227d5
Revises: 9b11ccdaf5ad
Create Date: 2025-10-02 15:10:57.276890

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf3aab5227d5'
down_revision: Union[str, None] = '9b11ccdaf5ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.execute("ALTER TYPE orderstatus ADD VALUE 'Da Riprogrammare';")


def downgrade() -> None:
  pass

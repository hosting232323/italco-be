"""rename document tables

Revision ID: 049
Revises: 048
Create Date: 2026-07-13

"""

from typing import Sequence, Union

from alembic import op


revision: str = '049'
down_revision: Union[str, None] = '048'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.rename_table('rae_document', 'dtr_document')
  op.rename_table('disposal_first_copy_document', 'fir_first_document')
  op.rename_table('disposal_fourth_copy_document', 'fir_fourth_document')


def downgrade() -> None:
  op.rename_table('fir_fourth_document', 'disposal_fourth_copy_document')
  op.rename_table('fir_first_document', 'disposal_first_copy_document')
  op.rename_table('dtr_document', 'rae_document')

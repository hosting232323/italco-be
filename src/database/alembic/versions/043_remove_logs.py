"""remove logs

Revision ID: 043
Revises: 042
Create Date: 2026-06-06 15:03:14.727239

"""

import json
import pytz
import decimal
from pathlib import Path
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '043'
down_revision: Union[str, None] = '042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _serialize_default(o):
  return float(o) if isinstance(o, decimal.Decimal) else str(o)


def migrate_logs_to_files() -> None:
  """Travasa i log dalla tabella `log` ai file JSONL giornalieri, nello stesso
  formato usato a runtime da save_log, prima che la tabella venga droppata."""
  from src import STATIC_FOLDER, IS_DEV

  log_dir = Path(STATIC_FOLDER) / ('test' if IS_DEV else 'prod') / 'logs'
  log_dir.mkdir(parents=True, exist_ok=True)
  rome_tz = pytz.timezone('Europe/Rome')

  connection = op.get_bind()
  rows = connection.execute(
    sa.text(
      'SELECT l.content, l.user_id, u.nickname, l.created_at '
      'FROM log l JOIN "user" u ON u.id = l.user_id '
      'ORDER BY l.created_at'
    )
  )

  for content, user_id, nickname, created_at in rows:
    try:
      payload = json.loads(content) if content else {}
    except (json.JSONDecodeError, TypeError):
      payload = {}

    ts = (created_at or datetime.now(rome_tz)).astimezone(rome_tz)
    entry = {
      'ts': ts.isoformat(),
      'user_id': user_id,
      'nickname': nickname,
      'request': payload.get('request'),
      'response': payload.get('response'),
    }

    month_dir = log_dir / ts.strftime('%Y-%m')
    month_dir.mkdir(parents=True, exist_ok=True)
    log_file = month_dir / f'{ts.strftime("%Y-%m-%d")}.jsonl'
    with open(log_file, 'a', encoding='utf-8') as f:
      f.write(json.dumps(entry, ensure_ascii=False, default=_serialize_default) + '\n')


def upgrade() -> None:
  migrate_logs_to_files()
  op.drop_table('log')


def downgrade() -> None:
  op.create_table(
    'log',
    sa.Column('content', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('log_user_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('log_pkey')),
  )

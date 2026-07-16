import os
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

# Lo storage locale deve essere isolato PRIMA dell'import di src:
# STATIC_FOLDER viene letto a livello di modulo in src/__init__.py.
os.environ.setdefault('STATIC_FOLDER', tempfile.mkdtemp(prefix='italco-test-static-'))


def _assert_test_database_url(url: str) -> str:
  parsed = make_url(url)
  db_name = (parsed.database or '').split('/')[-1]
  if not db_name.startswith('test'):
    raise RuntimeError(f'DATABASE_URL must target a test DB. Got database "{db_name}".')
  return url


def _prepare_test_database(url: str):
  """Crea il database di test se manca e riparte da uno schema vuoto.

  Lo schema viene poi ricostruito dalle migrazioni alembic quando
  src.__main__ chiama set_database (alembic_migration_check).
  """
  parsed = make_url(url)
  admin_engine = create_engine(parsed.set(database='postgres'), isolation_level='AUTOCOMMIT', pool_pre_ping=True)
  with admin_engine.connect() as conn:
    exists = conn.execute(
      text('SELECT 1 FROM pg_database WHERE datname = :db_name'), {'db_name': parsed.database}
    ).scalar()
    if not exists:
      conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
  admin_engine.dispose()

  engine = create_engine(url, isolation_level='AUTOCOMMIT', pool_pre_ping=True)
  with engine.connect() as conn:
    conn.execute(text('DROP SCHEMA public CASCADE'))
    conn.execute(text('CREATE SCHEMA public'))
  engine.dispose()


DATABASE_URL = _assert_test_database_url(os.environ['DATABASE_URL'])
_prepare_test_database(DATABASE_URL)

# L'import registra tutti i blueprint sull'app reale ed esegue set_database,
# che applica le migrazioni alembic sul database di test appena ripulito.
import database_api  # noqa: E402
import src.__main__  # noqa: E402,F401
from src import app as flask_app  # noqa: E402
from src.database.seed import seed_data  # noqa: E402


_TABLES = ', '.join(f'"{table.name}"' for table in database_api.Base.metadata.sorted_tables)


def _truncate_all_tables():
  with database_api.engine.begin() as conn:
    conn.execute(text(f'TRUNCATE TABLE {_TABLES} RESTART IDENTITY CASCADE'))


@pytest.fixture(autouse=True)
def db():
  """Ogni test parte da un database vuoto (schema creato dalle migrazioni)."""
  _truncate_all_tables()
  yield


@pytest.fixture
def seeded_db(db):
  seed_data()
  yield


@pytest.fixture(scope='session')
def app():
  flask_app.config.update(TESTING=True)
  return flask_app


@pytest.fixture
def client(app, db):
  return app.test_client()

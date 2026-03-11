import os

import pytest
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

os.environ['DECODE_JWT_TOKEN'] = 'test-secret-key-at-least-32-bytes'
os.environ.setdefault('SESSION_HOURS', '5')

import database_api
import src.database.schema  # noqa: F401
from src.database.seed import seed_data

from src.end_points.users import user_bp


def _assert_test_database_url(url: str) -> str:
  parsed = make_url(url)
  db_name = (parsed.database or '').split('/')[-1]
  if not db_name.startswith('test'):
    raise RuntimeError(f'DATABASE_URL must target a test DB. Got database "{db_name}".')
  return url


@pytest.fixture(scope='session')
def database_engine():
  database_url = os.environ.get('DATABASE_URL')
  if not database_url:
    raise RuntimeError('DATABASE_URL is required for tests.')

  safe_url = _assert_test_database_url(database_url)
  engine = create_engine(safe_url, pool_pre_ping=True)
  try:
    with engine.connect():
      pass
  except OperationalError as exc:
    parsed = make_url(safe_url)
    if parsed.drivername.startswith('postgresql') and 'does not exist' in str(exc):
      admin_url = parsed.set(database='postgres')
      admin_engine = create_engine(admin_url, isolation_level='AUTOCOMMIT', pool_pre_ping=True)
      with admin_engine.connect() as conn:
        exists = conn.execute(
          text('SELECT 1 FROM pg_database WHERE datname = :db_name'),
          {'db_name': parsed.database},
        ).scalar()
        if not exists:
          conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
      admin_engine.dispose()
      with engine.connect():
        pass
    else:
      raise
  database_api.engine = engine
  yield engine
  engine.dispose()


@pytest.fixture
def seeded_db(database_engine):
  database_api.Base.metadata.drop_all(bind=database_engine)
  database_api.Base.metadata.create_all(bind=database_engine)
  seed_data()
  yield


@pytest.fixture
def app(seeded_db):
  app = Flask(__name__)
  app.register_blueprint(user_bp, url_prefix='/users/')
  return app


@pytest.fixture
def client(app):
  return app.test_client()

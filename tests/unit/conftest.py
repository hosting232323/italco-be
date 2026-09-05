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
from src.database.schema import Company, RaeDisposalPlace  # noqa: E402
from src.database.seed import seed_data  # noqa: E402
from database_api.operations import create  # noqa: E402


_TABLES = ', '.join(f'"{table.name}"' for table in database_api.Base.metadata.sorted_tables)


def _truncate_all_tables():
  with database_api.engine.begin() as conn:
    conn.execute(text(f'TRUNCATE TABLE {_TABLES} RESTART IDENTITY CASCADE'))


TEST_COMPANY_NAME = 'Test Company'

# Dati legali dell'attività: la fixture li popola così i PDF che li stampano
# hanno qualcosa di reale da rendere, come in produzione. I dati RAE specifici
# (iscrizione Albo, luogo di raggruppamento) non sono più qui: vivono su
# RaeDisposalPlace, popolato subito sotto per la stessa ragione.
TEST_COMPANY_LEGAL = {
  'legal_name': 'Test Company SRL',
  'vat_number': '09876543210',
  'tax_code': '01234567890',
  'address': 'Via delle Prove 1',
  'city': 'Bari (BA)',
}

TEST_DISPOSAL_PLACE = {
  'name': 'Sede principale',
  'rae_registration': 'RD999S00099999 del 01/01/26',
  'rae_grouping_place': 'Via Deposito 9, Bari (BA)',
}


@pytest.fixture(autouse=True)
def db():
  """Database vuoto (schema creato dalle migrazioni) e una company attiva.

  Il tenant nello scope non è comodità da test: senza, il timbro in scrittura
  rifiuta le insert esattamente come farebbe in produzione fuori da una
  richiesta autenticata. La fixture restituisce la company così i test di
  isolamento possono confrontarla con una seconda.

  rae=True perché la company di default è quella su cui gira tutto il resto
  della suite, RAEE compreso. Lo spegnimento è la condizione da provare, non
  quella da subire: i test del modulo disattivo se lo mettono a False da soli.
  Stesso discorso per automatic_planning, che i suoi endpoint (le proposte di
  schedulazione) richiedono acceso.

  Le porta dietro anche un luogo di smaltimento, altrimenti il vincolo "almeno
  uno con rae=true" sarebbe già violato dalla fixture stessa.
  """
  _truncate_all_tables()
  company = create(Company, {'name': TEST_COMPANY_NAME, 'rae': True, 'automatic_planning': True, **TEST_COMPANY_LEGAL})
  with database_api.scope(company_id=company.id):
    create(RaeDisposalPlace, TEST_DISPOSAL_PLACE)
    yield company


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

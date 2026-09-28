import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

# L'isolamento di STATIC_FOLDER vive in tests/conftest.py: deve avvenire
# PRIMA di qualunque `import src` in qualunque conftest, e tests/e2e/conftest.py
# importa src.database.schema senza passare da qui.


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
# (il DDT RAEE) hanno qualcosa di reale da rendere, come in produzione.
# rae_registration (iscrizione Albo) è dell'attività, una sola; il luogo di
# raggruppamento vive su RaeDisposalPlace, popolato subito sotto per la stessa
# ragione.
TEST_COMPANY_LEGAL = {
  'legal_name': 'Test Company SRL',
  'vat_number': '09876543210',
  'tax_code': '01234567890',
  'address': 'Via delle Prove 1',
  'city': 'Bari (BA)',
  'rae_registration': 'RD999S00099999 del 01/01/26',
}

TEST_DISPOSAL_PLACE = {
  'name': 'Sede principale',
  'rae_grouping_place': 'Via Deposito 9, Bari (BA)',
}


@pytest.fixture(autouse=True)
def _clear_caps_cache():
  """Isola i test dalla cache di src.utils.caps.

  Le funzioni di geocodifica sono cachate per evitare di richiamare
  Nominatim ad ogni lookup (vedi src/utils/caps.py); senza reset, un test
  che chiama la funzione reale (rete vera o mockata) inquina la cache per
  tutti i test successivi che si aspettano di controllare la chiamata.
  """
  from src.end_points.service import travel as travel_module
  from src.utils import caps as caps_module

  caps_module.get_province_by_cap.cache_clear()
  caps_module.get_cap_by_name.cache_clear()
  caps_module.get_lat_lon_by_cap.cache_clear()
  caps_module.get_lat_lon_by_address.cache_clear()
  travel_module.travel_time_matrix_osrm.cache_clear()
  yield


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


class OfflineGeo:
  """Geocoding e OSRM finti, con i percorsi che il codice ha chiesto.

  I test della capienza delle fasce passano dal geocoder (veicolo, ritiri,
  ordini) e da OSRM (minuti di strada): senza questa fixture chiamerebbero il
  vero Nominatim e passerebbero solo con la rete su. Qui i luoghi si dichiarano
  (``places``: sottostringa dell'indirizzo -> coordinata, ``caps``: CAP ->
  coordinata), i minuti di ogni percorso li decide il test (``minutes``, un
  numero o una funzione del percorso) e ``paths`` registra i percorsi chiesti,
  per verificare l'ordine in cui il veicolo tocca le tappe.
  """

  def __init__(self):
    self.places: dict[str, tuple] = {}
    self.caps: dict[str, tuple] = {}
    self.minutes = 0
    self.paths: list[list[tuple]] = []
    self.unreachable = False

  def by_address(self, address):
    if self.unreachable:
      raise requests.ConnectionError('geocoder non raggiungibile')
    for fragment, coord in self.places.items():
      if fragment in (address or ''):
        return coord
    return None, None

  def by_cap(self, cap):
    if self.unreachable:
      raise requests.ConnectionError('geocoder non raggiungibile')
    return self.caps.get(cap, (None, None))

  def sequential(self, coords):
    self.paths.append(list(coords))
    return self.minutes(coords) if callable(self.minutes) else self.minutes


@pytest.fixture
def offline_geo():
  geo = OfflineGeo()
  targets = {
    'src.end_points.service.travel.get_lat_lon_by_address': geo.by_address,
    'src.end_points.service.travel.get_lat_lon_by_cap': geo.by_cap,
    'src.end_points.service.duration.get_lat_lon_by_address': geo.by_address,
    'src.end_points.service.duration.get_lat_lon_by_cap': geo.by_cap,
    'src.end_points.service.travel.sequential_travel_minutes': geo.sequential,
  }
  patches = [patch(target, replacement) for target, replacement in targets.items()]
  for active in patches:
    active.start()
  yield geo
  for active in patches:
    active.stop()

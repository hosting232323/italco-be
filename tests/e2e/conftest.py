import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

# Ensure the project root is in sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

import database_api

import src.database.schema  # noqa: F401
from src.database.enum import UserRole
from tests.utils import create_user_for_login


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


def _wait_backend_ready(backend_url: str, timeout_seconds: int):
  deadline = time.time() + timeout_seconds
  health_url = f'{backend_url}/'
  while time.time() < deadline:
    try:
      with urlopen(health_url, timeout=2):
        return
    except URLError:
      time.sleep(0.5)
  raise RuntimeError(f'Backend did not become ready at {health_url} within {timeout_seconds} seconds.')


def _encrypt_password(password: str, secret_key: str, iv_string: str) -> str:
  """Encrypts the password using AES-CBC with PKCS7 padding, then encodes as base64."""
  key_bytes = secret_key.encode('utf-8')
  iv_bytes = iv_string.encode('utf-8')
  if len(key_bytes) not in {16, 24, 32}:
    raise ValueError('E2E secret key must be 16, 24, or 32 bytes for AES.')
  if len(iv_bytes) != 16:
    raise ValueError('E2E IV must be exactly 16 bytes for AES-CBC.')

  padder = padding.PKCS7(128).padder()
  padded = padder.update(password.encode('utf-8')) + padder.finalize()

  cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes))
  encryptor = cipher.encryptor()
  ciphertext = encryptor.update(padded) + encryptor.finalize()
  return base64.b64encode(iv_bytes + ciphertext).decode('utf-8')


@pytest.fixture(scope='session')
def e2e_secret_key() -> str:
  return os.environ.get('E2E_SECRET_KEY', '0123456789abcdef0123456789abcdef')


@pytest.fixture(scope='session')
def e2e_iv() -> str:
  return os.environ.get('E2E_IV', '0123456789abcdef')


def _wait_url_ready(url: str, timeout_seconds: int):
  deadline = time.time() + timeout_seconds
  while time.time() < deadline:
    try:
      with urlopen(url, timeout=2):
        return
    except URLError:
      time.sleep(0.5)
  raise RuntimeError(f'Service did not become ready at {url} within {timeout_seconds} seconds.')


@pytest.fixture(scope='session')
def frontend_server(backend_server: str, e2e_secret_key: str, e2e_iv: str):
  if os.environ.get('E2E_MANAGE_FRONTEND', '1') != '1':
    yield None
    return

  frontend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'italco-fe'))
  if not os.path.isdir(frontend_root):
    pytest.fail(f'Cannot find frontend project at {frontend_root}')

  frontend_port = int(os.environ.get('E2E_FRONTEND_PORT', '4173'))
  managed_frontend_url = f'http://127.0.0.1:{frontend_port}/'
  env = os.environ.copy()
  env['VITE_HOSTNAME'] = f'{backend_server}/'
  env['VITE_SECRET_KEY'] = e2e_secret_key
  env['VITE_IV'] = e2e_iv

  command = ['bun', 'run', 'dev', '--host', '127.0.0.1', '--port', str(frontend_port)]
  process = subprocess.Popen(
    command, cwd=frontend_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
  )

  startup_timeout = int(os.environ.get('E2E_FRONTEND_STARTUP_TIMEOUT', '40'))
  try:
    _wait_url_ready(managed_frontend_url, startup_timeout)
  except Exception as exc:
    process.terminate()
    process.wait(timeout=5)
    stderr = process.stderr.read() if process.stderr else ''
    stdout = process.stdout.read() if process.stdout else ''
    pytest.fail(f'Failed to start frontend at {managed_frontend_url}: {exc}\nstdout:\n{stdout}\nstderr:\n{stderr}')

  yield managed_frontend_url

  process.terminate()
  try:
    process.wait(timeout=5)
  except subprocess.TimeoutExpired:
    process.kill()
    process.wait(timeout=5)


@pytest.fixture(scope='session')
def frontend_url(frontend_server: str | None) -> str:
  if frontend_server:
    return frontend_server
  return os.environ.get('E2E_FRONTEND_URL', 'http://localhost:3000/').rstrip('/') + '/'


@pytest.fixture(scope='session')
def backend_url() -> str:
  return os.environ.get('E2E_BACKEND_URL', 'http://localhost:8080/').rstrip('/')


@pytest.fixture(scope='session')
def backend_server(backend_url: str, database_engine):
  parsed = urlparse(backend_url)
  if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
    pytest.fail(f'Invalid E2E_BACKEND_URL: {backend_url}')
  if parsed.scheme != 'http':
    pytest.fail(f'E2E_BACKEND_URL must be http for local test server startup. Got: {backend_url}')
  if parsed.path not in {'', '/'}:
    pytest.fail(f'E2E_BACKEND_URL must not include a path. Got: {backend_url}')

  port = parsed.port or 8080
  project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
  env = os.environ.copy()
  existing_pythonpath = env.get('PYTHONPATH')
  env['PYTHONPATH'] = f'{project_root}{os.pathsep}{existing_pythonpath}' if existing_pythonpath else project_root
  env['PORT'] = str(port)
  env.setdefault('IS_DEV', '1')

  command = [
    sys.executable,
    '-c',
    'from src.__main__ import app; app.run(host="127.0.0.1", port=int(__import__("os").environ["PORT"]), debug=False, use_reloader=False)',
  ]
  process = subprocess.Popen(
    command, cwd=project_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
  )

  startup_timeout = int(os.environ.get('E2E_BACKEND_STARTUP_TIMEOUT', '20'))
  try:
    _wait_backend_ready(backend_url, startup_timeout)
  except Exception as exc:
    process.terminate()
    process.wait(timeout=5)
    stderr = process.stderr.read() if process.stderr else ''
    stdout = process.stdout.read() if process.stdout else ''
    pytest.fail(f'Failed to start backend at {backend_url}: {exc}\nstdout:\n{stdout}\nstderr:\n{stderr}')

  yield backend_url

  process.terminate()
  try:
    process.wait(timeout=5)
  except subprocess.TimeoutExpired:
    process.kill()
    process.wait(timeout=5)


@pytest.fixture(scope='session')
def selenium_remote_url() -> str | None:
  return os.environ.get('SELENIUM_REMOTE_URL')


@pytest.fixture(scope='session')
def driver(selenium_remote_url: str | None):
  options = Options()
  options.add_argument('--headless=new')
  options.add_argument('--no-sandbox')
  options.add_argument('--disable-dev-shm-usage')
  options.add_argument('--window-size=1440,1000')

  if selenium_remote_url:
    browser = webdriver.Remote(command_executor=selenium_remote_url, options=options)
  else:
    browser = webdriver.Chrome(options=options)

  yield browser
  browser.quit()


@pytest.fixture
def wait(driver):
  return WebDriverWait(driver, timeout=15)


@pytest.fixture
def frontend_reachable(frontend_url: str):
  try:
    with urlopen(frontend_url, timeout=5):
      return frontend_url
  except URLError as exc:
    pytest.fail(f'Frontend is not reachable at {frontend_url}. Set E2E_FRONTEND_URL correctly. ({exc})')


@pytest.fixture
def e2e_user(request, backend_server: str, e2e_secret_key: str, e2e_iv: str):
  if not os.environ.get('DATABASE_URL'):
    pytest.fail('DATABASE_URL is required to provision E2E login test user.')
  request.getfixturevalue('database_engine')
  nickname = f'e2e.login.{uuid4().hex[:10]}@example.com'
  plain_password = 'e2e-password'
  encrypted_password = _encrypt_password(plain_password, e2e_secret_key, e2e_iv)
  create_user_for_login(nickname, encrypted_password, UserRole.DELIVERY)
  payload = json.dumps({'email': nickname, 'password': encrypted_password}).encode('utf-8')
  req = Request(
    f'{backend_server}/user/login',
    data=payload,
    headers={'Content-Type': 'application/json'},
    method='POST',
  )
  try:
    with urlopen(req, timeout=5) as response:
      body = json.loads(response.read().decode('utf-8'))
    if body.get('status') != 'ok':
      pytest.fail(
        'Backend login did not accept provisioned E2E user. '
        f'endpoint={backend_server}/user/login response={body}. '
        'Ensure backend uses the same DATABASE_URL as tests.'
      )
  except HTTPError as exc:
    response_body = exc.read().decode('utf-8', errors='replace') if hasattr(exc, 'read') else ''
    pytest.fail(
      f'Backend login endpoint returned HTTP {exc.code} at {backend_server}/user/login. Body: {response_body}'
    )
  except URLError as exc:
    pytest.fail(f'Backend is not reachable at {backend_server}. ({exc})')
  return {'email': nickname, 'password': plain_password}

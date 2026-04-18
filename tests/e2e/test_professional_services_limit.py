"""
E2E test: Pianificazione Automatica respects MAX_PROFESSIONAL_ORDERS=2.

Uses Selenium (Chrome) to match the CI test infrastructure.  The test logs
in via the browser (to establish a realistic session and confirm the frontend
is reachable), extracts the JWT token from the Pinia user store, then calls
the /schedule/suggestions API directly to assert that every returned proposal
group contains at most 2 professional orders (orders that have at least one
product with a professional service).
"""

import datetime
import json
import urllib.request
from urllib.error import HTTPError

import pytest

from tests.e2e.order_lifecycle_flow import _login as _do_login

pytestmark = pytest.mark.e2e

MAX_PROFESSIONAL_ORDERS = 2


def _count_professional_orders_in_group(schedule_items: list) -> int:
  """Return the number of Order items in a proposal group that have at least
  one product with a professional service."""
  count = 0
  for item in schedule_items:
    if item.get('operation_type') != 'Order':
      continue
    for product in item.get('products', {}).values():
      if any(isinstance(svc, dict) and svc.get('professional') for svc in product.get('services', [])):
        count += 1
        break
  return count


def _extract_token(driver) -> str:
  """Extract the JWT token from the Pinia user store after login."""
  token = driver.execute_script("""
    const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
    const userStore = pinia?._s?.get('user');
    return userStore?.token ?? null;
  """)
  assert token, 'JWT token not found in Pinia user store after login'
  return token


def test_schedule_proposals_professional_services_limit(driver, wait, frontend_reachable, e2e_user, backend_server):
  """
  Flow:
  1. Login as admin via the browser (verifies the frontend login works).
  2. Extract the JWT token from the Pinia user store.
  3. Call /schedule/suggestions with today's date and min_size_group=1 so all
     20 seed orders are eligible for grouping.
  4. Assert every group has ≤ MAX_PROFESSIONAL_ORDERS=2 professional orders
     (orders that have at least one product with a professional service).
  """
  today = datetime.date.today().isoformat()

  # 1. Login via browser
  _do_login(driver, wait, frontend_reachable, e2e_user['email'], e2e_user['password'])

  # 2. Extract JWT token from Pinia store
  token = _extract_token(driver)

  # 3. Call schedule/suggestions API directly
  url = f'{backend_server}/schedule/suggestions?work_date={today}&min_size_group=1&max_size_group=12&max_distance_km=50'
  req = urllib.request.Request(url, headers={'Authorization': token}, method='GET')
  try:
    with urllib.request.urlopen(req, timeout=30) as resp:
      body = json.loads(resp.read())
  except HTTPError as exc:
    raw = exc.read()
    try:
      body = json.loads(raw)
    except Exception:
      body = {'status': 'ko', 'raw': raw.decode('utf-8', errors='replace'), 'http_status': exc.code}

  # 4. Assert professional order limit
  assert body.get('status') == 'ok', f'schedule/suggestions returned non-ok status: {body}'

  groups = body['groups']
  assert len(groups) > 0, 'Expected at least one proposal group from the seed data'

  for i, group in enumerate(groups):
    pro_count = _count_professional_orders_in_group(group['schedule_items'])
    assert pro_count <= MAX_PROFESSIONAL_ORDERS, (
      f'Group {i} contains {pro_count} professional orders (limit is {MAX_PROFESSIONAL_ORDERS})'
    )

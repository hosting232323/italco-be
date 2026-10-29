"""
E2E (Playwright): la Pianificazione Automatica rispetta MAX_PROFESSIONAL_ORDERS=2.

Flusso completamente browser-based:
1. Login come admin (fixture pw_page).
2. Va sulla pagina Ordini e apre "Pianificazione Automatica".
3. Imposta la data odierna e min_size_group = 1.
4. Invia e attende le proposte di borderò.
5. Legge le proposte dalla risposta API e verifica il limite di ordini
   professionali per ciascuna proposta.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

MAX_PROFESSIONAL_ORDERS = 2


def _extract_suggestions(payload):
  """Estrae ricorsivamente i gruppi/proposte dal payload JSON."""
  if isinstance(payload, list):
    if payload and all(isinstance(item, dict) for item in payload):
      if any('orders' in item for item in payload):
        return payload
    for item in payload:
      found = _extract_suggestions(item)
      if found:
        return found
    return None

  if isinstance(payload, dict):
    groups = payload.get('groups')
    if isinstance(groups, list):
      return groups

    direct = payload.get('suggestions')
    if isinstance(direct, list):
      return direct

    for value in payload.values():
      found = _extract_suggestions(value)
      if found:
        return found

  return None


def _count_professional_orders(orders: list) -> int:
  count = 0
  for order in orders:
    if order.get('operation_type') != 'Order':
      continue
    for product in (order.get('products') or {}).values():
      if any(service.get('professional') for service in (product.get('services') or [])):
        count += 1
        break
  return count


def test_schedule_proposals_professional_services_limit(pw_page: Page, pw_base_url: str):
  page = pw_page
  browser_errors = []
  page.on('pageerror', lambda error: browser_errors.append(str(error)))
  page.on('console', lambda message: browser_errors.append(message.text) if message.type == 'error' else None)

  # Il bottone "Pianificazione Automatica" sta in OrderTable, quindi nella
  # pagina Ordini: dopo il login si atterra sulla dashboard, che non lo ha.
  page.goto(f'{pw_base_url}/orders')
  schedule_button = page.get_by_role('button', name='Pianificazione Automatica')
  expect(schedule_button).to_be_visible(timeout=15_000)

  schedule_button.click()
  expect(page.locator('.v-dialog')).to_be_visible(timeout=10_000)

  date_field = page.locator('.v-dialog .v-text-field').filter(has_text='Data Work')
  date_field.click()
  page.wait_for_selector('.v-date-picker-month', timeout=5_000)
  page.locator('.v-date-picker-month__day-btn[aria-current="date"]').click()
  page.keyboard.press('Escape')

  min_input = page.locator('.v-dialog input[type="number"]').first
  min_input.click()
  min_input.fill('1')

  with page.expect_response(lambda response: '/schedule/suggestions' in response.url, timeout=30_000) as api_response:
    page.locator('.v-dialog').get_by_role('button', name='INVIA').click()

  response = api_response.value
  try:
    payload = response.json()
  except Exception as exc:
    pytest.fail(f'La API delle proposte non ha restituito JSON (HTTP {response.status}): {exc}')

  assert response.ok, f'API pianificazione HTTP {response.status}: {payload}'
  assert payload.get('status') == 'ok', f'API pianificazione ha risposto con errore: {payload}'
  suggestions = _extract_suggestions(payload)
  assert suggestions, f'Nessuna proposta ricevuta dal backend: {payload}'

  try:
    expect(page.get_by_text('Proposta Borderò 1')).to_be_visible(timeout=10_000)
  except AssertionError as exc:
    first_group = suggestions[0]
    group_summary = {
      'group_keys': list(first_group),
      'schedule_item_count': len(first_group.get('schedule_items') or []),
      'operation_types': sorted({item.get('operation_type') for item in first_group.get('schedule_items') or []}),
      'transport_count': len(first_group.get('transports') or []),
    }
    pytest.fail(
      f'La API ha restituito {len(suggestions)} gruppi ({group_summary}), '
      f'ma la proposta non è stata renderizzata. Errori browser: {browser_errors}; errore: {exc}'
    )

  for index, suggestion in enumerate(suggestions):
    orders = suggestion.get('orders') or suggestion.get('schedule_items') or []
    pro_count = _count_professional_orders(orders)
    assert pro_count <= MAX_PROFESSIONAL_ORDERS, (
      f'Proposta Borderò {index + 1} ha {pro_count} ordini professionali (limite: {MAX_PROFESSIONAL_ORDERS})'
    )

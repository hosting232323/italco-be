"""
E2E (Playwright): la Pianificazione Automatica rispetta MAX_PROFESSIONAL_ORDERS=2.

Flusso completamente browser-based:
1. Login come admin (fixture pw_page).
2. Apre "Pianificazione Automatica".
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


def test_schedule_proposals_professional_services_limit(pw_page: Page):
  page = pw_page
  captured_suggestions = []

  def _capture_suggestions(response):
    try:
      if 'application/json' not in response.headers.get('content-type', '').lower():
        return
      suggestions = _extract_suggestions(response.json())
      if suggestions:
        captured_suggestions.append(suggestions)
    except Exception:
      return

  page.on('response', _capture_suggestions)

  page.get_by_role('button', name='Pianificazione Automatica').click()
  expect(page.locator('.v-dialog')).to_be_visible(timeout=10_000)

  date_field = page.locator('.v-dialog .v-text-field').filter(has_text='Data Work')
  date_field.click()
  page.wait_for_selector('.v-date-picker-month', timeout=5_000)
  page.locator('.v-date-picker-month__day-btn[aria-current="date"]').click()
  page.keyboard.press('Escape')

  min_input = page.locator('.v-dialog input[type="number"]').first
  min_input.click()
  min_input.fill('1')

  page.locator('.v-dialog').get_by_role('button', name='INVIA').click()

  expect(page.get_by_text('Proposta Borderò 1')).to_be_visible(timeout=30_000)

  for _ in range(20):
    if captured_suggestions:
      break
    page.wait_for_timeout(500)

  page.remove_listener('response', _capture_suggestions)

  suggestions = captured_suggestions[-1] if captured_suggestions else None
  assert suggestions, 'Impossibile leggere le proposte dalla risposta API'
  assert len(suggestions) > 0, 'Nessuna proposta ricevuta dal backend'

  for index, suggestion in enumerate(suggestions):
    orders = suggestion.get('orders') or suggestion.get('schedule_items') or []
    pro_count = _count_professional_orders(orders)
    assert pro_count <= MAX_PROFESSIONAL_ORDERS, (
      f'Proposta Borderò {index + 1} ha {pro_count} ordini professionali (limite: {MAX_PROFESSIONAL_ORDERS})'
    )

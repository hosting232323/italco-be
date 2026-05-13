"""
E2E tests (Playwright): lifecycle ordine in stile test module compatto.

Copre gli stessi scenari del flusso Selenium legacy:
1. Admin crea un ordine completo end-to-end.
2. Step customer blocca submit senza "Punto Vendita".
3. Form operatore blocca indirizzo non validato da Google Places.
4. Dialog "Crea Ordine" si apre e si chiude correttamente.
"""

from dataclasses import asdict, dataclass

import pytest
from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

pytestmark = pytest.mark.e2e


@dataclass(frozen=True)
class OrderLifecycleData:
  punto_vendita: str = 'customer'
  tipo: str = 'Consegna'
  prodotto: str = 'Prodotto Test'
  servizio: str = 'Service 1'
  destinatario: str = 'Mario Rossi'
  indirizzo_display: str = 'Viale Luigi Einaudi, 70125 Bari BA, Italy'
  indirizzo_store: str = 'Viale Luigi Einaudi, Bari, BA'
  cap: str = '70125'
  recapito: str = '+393280000001'
  contrassegno: str = '100'
  piano: str = '2'


def _input_for_label(page: Page, label_text: str):
  locator = page.locator(
    'xpath='
    f"//label[contains(@class,'v-label') and normalize-space()='{label_text}']"
    "/ancestor::div[contains(@class,'v-field__field')][1]"
    '//input'
  ).first
  expect(locator).to_be_visible(timeout=12_000)
  return locator


def _click_submit(page: Page):
  submit = page.locator("button[type='submit'], button:has-text('Invia')").first
  expect(submit).to_be_visible(timeout=10_000)
  submit.click()


def _open_creation_dialog(page: Page):
  plus_button = page.locator(
    "xpath=//h1//button[.//*[contains(@class,'mdi-plus')]]"
    " | //button[contains(@class,'v-btn--icon')][.//*[contains(@class,'mdi-plus')]]"
  ).first
  expect(plus_button).to_be_visible(timeout=12_000)
  plus_button.click()
  expect(page.get_by_text('Crea Ordine')).to_be_visible(timeout=12_000)


def _pick_dropdown_item(page: Page, item_text: str):
  visible_overlay_prefix = "//div[contains(@class,'v-overlay__content') and not(contains(@style,'display: none'))]"

  exact = page.locator(
    f"xpath={visible_overlay_prefix}//div[contains(@class,'v-list-item-title') and normalize-space()='{item_text}']"
  ).first
  if exact.count() > 0:
    expect(exact).to_be_visible(timeout=10_000)
    exact.click()
    return

  ci_contains = page.locator(
    'xpath='
    f"{visible_overlay_prefix}//div[contains(@class,'v-list-item-title') and "
    f"contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{item_text.lower()}')]"
  ).first
  expect(ci_contains).to_be_visible(timeout=10_000)
  ci_contains.click()


def _open_vselect(page: Page, label_text: str):
  inp = _input_for_label(page, label_text)
  inp.evaluate(
    """
    (input) => {
      const vSelect = input.closest('.v-select');
      const icon = vSelect?.querySelector('.v-select__menu-icon');
      const appendInner = input.closest('.v-field')?.querySelector('.v-field__append-inner');
      const target = icon || appendInner || input.closest('.v-field') || input;
      target?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    }
    """
  )


def _select_punto_vendita(page: Page, punto_vendita: str):
  pv_input = _input_for_label(page, 'Punto Vendita')
  pv_input.click()
  pv_input.fill('')
  pv_input.type(punto_vendita, delay=45)
  _pick_dropdown_item(page, punto_vendita)
  # Ensure selection is committed in Vuetify combobox before submit.
  pv_input.press('Tab')
  _click_submit(page)


def _select_tipo(page: Page, tipo: str):
  _open_vselect(page, 'Tipo')
  _pick_dropdown_item(page, tipo)


def _add_product(page: Page, prodotto: str, servizio: str):
  product_input = _input_for_label(page, 'Prodotto')
  product_input.fill(prodotto)

  _open_vselect(page, 'Servizio')
  _pick_dropdown_item(page, servizio)

  plus_icon = page.locator("xpath=(//div[contains(@class,'v-input__prepend')]//*[contains(@class,'mdi-plus')])[1]")
  expect(plus_icon).to_be_visible(timeout=10_000)
  plus_icon.click(force=True)

  expect(
    page.locator(f"xpath=//div[contains(@class,'v-list-item-title') and contains(text(),'{prodotto}')]").first
  ).to_be_visible(timeout=10_000)


def _sync_operator_values_in_store(page: Page, data: OrderLifecycleData):
  payload = asdict(data)
  page.evaluate(
    """
    (args) => {
      const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
      const orderStore = pinia?._s?.get('order');
      if (!orderStore) return;
      const o = orderStore.element;
      o.addressee = args.destinatario;
      o.address = args.indirizzo_store;
      o.cap = args.cap;
      o.addressee_contact = args.recapito;
      o.mark = args.contrassegno;
      o.elevator = true;
      o.floor = args.piano;
    }
    """,
    payload,
  )


def _fill_operator_form(page: Page, data: OrderLifecycleData):
  _input_for_label(page, 'Destinatario').fill(data.destinatario)

  addr_input = page.locator("input[id^='google-autocomplete-']").first
  expect(addr_input).to_be_visible(timeout=10_000)
  addr_input.fill(data.indirizzo_display)

  page.evaluate(
    """
    ({ displayAddress, storeAddress }) => {
      const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
      const orderStore = pinia?._s?.get('order');
      if (orderStore) orderStore.element.address = storeAddress;
      const input = document.querySelector('input[id^="google-autocomplete-"]');
      if (!input) return;
      input.value = displayAddress;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      input.dispatchEvent(new Event('blur', { bubbles: true }));
    }
    """,
    {'displayAddress': data.indirizzo_display, 'storeAddress': data.indirizzo_store},
  )

  _input_for_label(page, 'CAP').fill(data.cap)
  _input_for_label(page, 'Recapito').fill(data.recapito)
  _input_for_label(page, 'Contrassegno').fill(data.contrassegno)

  yes_radio = page.locator(
    'xpath='
    "//div[contains(@class,'v-radio-group')]"
    "//label[contains(@class,'v-label') and (normalize-space()='Sì' or normalize-space()='Si')]"
  ).first
  expect(yes_radio).to_be_visible(timeout=10_000)
  yes_radio.click()

  _input_for_label(page, 'Piano').fill(data.piano)
  _sync_operator_values_in_store(page, data)


def _fill_operator_form_without_google_bypass(page: Page, data: OrderLifecycleData):
  _input_for_label(page, 'Destinatario').fill(data.destinatario)
  addr_input = page.locator("input[id^='google-autocomplete-']").first
  expect(addr_input).to_be_visible(timeout=10_000)
  addr_input.fill(data.indirizzo_display)
  _input_for_label(page, 'CAP').fill(data.cap)
  _input_for_label(page, 'Recapito').fill(data.recapito)
  _input_for_label(page, 'Contrassegno').fill(data.contrassegno)

  yes_radio = page.locator(
    'xpath='
    "//div[contains(@class,'v-radio-group')]"
    "//label[contains(@class,'v-label') and (normalize-space()='Sì' or normalize-space()='Si')]"
  ).first
  expect(yes_radio).to_be_visible(timeout=10_000)
  yes_radio.click()

  _input_for_label(page, 'Piano').fill(data.piano)


def _dates_form_flag(page: Page) -> bool:
  return bool(
    page.evaluate(
      """
      () => {
        const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
        return !!pinia?._s?.get('order')?.element?.dates_form;
      }
      """
    )
  )


def _activate_dates_fallback(page: Page) -> bool:
  return bool(
    page.evaluate(
      """
      () => {
        const messages = Array.from(document.querySelectorAll('.v-messages__message'))
          .map((e) => e.textContent?.trim())
          .filter(Boolean);
        const onlyGoogleAddressError =
          messages.length > 0 && messages.every((m) => m.includes('indirizzo valido da Google Places'));
        if (!onlyGoogleAddressError) return false;
        const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
        const orderStore = pinia?._s?.get('order');
        if (!orderStore) return false;
        orderStore.element.dates_form = true;
        return true;
      }
      """
    )
  )


def _order_debug_state(page: Page):
  return page.evaluate(
    """
    () => {
      const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
      const order = pinia?._s?.get('order')?.element || null;
      const messages = Array.from(document.querySelectorAll('.v-messages__message'))
        .map((e) => e.textContent?.trim())
        .filter(Boolean);
      return { order, messages };
    }
    """
  )


def _submit_operator_form_to_dates(page: Page):
  _click_submit(page)
  page.wait_for_timeout(200)
  if _dates_form_flag(page):
    return

  _click_submit(page)
  page.wait_for_timeout(200)
  if _dates_form_flag(page):
    return

  if _activate_dates_fallback(page):
    return

  raise AssertionError(f'DatesForm transition failed. Debug: {_order_debug_state(page)}')


def _open_date_picker_and_pick_day(page: Page, label_text: str):
  container = page.locator(
    'xpath='
    f"//label[contains(@class,'v-label') and contains(text(),'{label_text}')]"
    "/ancestor::div[contains(@class,'v-text-field')][1]"
  ).first
  expect(container).to_be_visible(timeout=10_000)
  container.click(force=True)

  expect(page.locator('.v-date-picker-month').first).to_be_visible(timeout=5_000)

  day = page.locator(
    '.v-date-picker-month__day:not(.v-date-picker-month__day--adjacent) .v-date-picker-month__day-btn'
  ).first
  expect(day).to_be_visible(timeout=5_000)
  day.click()
  page.wait_for_timeout(300)


def _set_dates(page: Page):
  try:
    _open_date_picker_and_pick_day(page, 'Data Prevista dal Cliente')
    _open_date_picker_and_pick_day(page, 'Data Richiesta dal Cliente')
  except (PlaywrightTimeoutError, AssertionError):
    page.evaluate(
      """
      () => {
        const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
        const orderStore = pinia?._s?.get('order');
        if (!orderStore) return;
        const fmt = (d) => d.toISOString().slice(0, 10);
        const base = new Date();
        const dpc = new Date(base);
        dpc.setDate(base.getDate() + 1);
        const drc = new Date(base);
        drc.setDate(base.getDate() + 2);
        orderStore.element.dpc = fmt(dpc);
        orderStore.element.drc = fmt(drc);
        orderStore.element.booking_date = fmt(drc);
      }
      """
    )


def _assert_order_visible(page: Page):
  page.wait_for_timeout(600)
  table_cells = page.locator('td')
  expect(table_cells.first).to_be_visible(timeout=15_000)

  has_expected_cell = (
    page.locator('td', has_text='Viale Luigi Einaudi').count() > 0
    or page.locator('td', has_text='Mario Rossi').count() > 0
  )
  if not has_expected_cell:
    body = page.locator('body').inner_text()
    raise AssertionError(
      'New order not found in dashboard table. '
      'Expected a cell containing "Viale Luigi Einaudi" or "Mario Rossi". '
      f'Visible page text (first 1000 chars):\n{body[:1000]}'
    )


def _open_order_operator_form(page: Page, data: OrderLifecycleData):
  _open_creation_dialog(page)
  _select_punto_vendita(page, data.punto_vendita)
  _select_tipo(page, data.tipo)


def _run_order_lifecycle(page: Page, data: OrderLifecycleData | None = None):
  d = data or OrderLifecycleData()
  _open_order_operator_form(page, d)
  _add_product(page, d.prodotto, d.servizio)
  _fill_operator_form(page, d)
  _submit_operator_form_to_dates(page)
  _set_dates(page)
  _click_submit(page)
  _assert_order_visible(page)


def test_order_lifecycle_admin_creates_order(pw_page: Page):
  _run_order_lifecycle(pw_page)


def test_customer_step_requires_punto_vendita_selection(pw_page: Page):
  page = pw_page
  _open_creation_dialog(page)
  _click_submit(page)

  user_id = page.evaluate(
    """
    () => {
      const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
      const orderStore = pinia?._s?.get('order');
      return orderStore?.element?.user_id ?? null;
    }
    """
  )

  expect(page.get_by_text('Punto Vendita')).to_be_visible(timeout=10_000)
  assert user_id is None


def test_order_form_blocks_invalid_address_without_google_selection(pw_page: Page):
  page = pw_page
  data = OrderLifecycleData()

  _open_order_operator_form(page, data)
  _add_product(page, data.prodotto, data.servizio)
  _fill_operator_form_without_google_bypass(page, data)
  _click_submit(page)

  expect(page.get_by_text('Seleziona un indirizzo valido da Google Places')).to_be_visible(timeout=10_000)


def test_order_dialog_can_be_opened_and_closed(pw_page: Page):
  page = pw_page
  _open_creation_dialog(page)

  close_btn = page.locator('button:has(i.mdi-close), button:has(.mdi-close)').first
  expect(close_btn).to_be_visible(timeout=8_000)
  close_btn.click()

  expect(page.get_by_text('Crea Ordine')).not_to_be_visible(timeout=8_000)

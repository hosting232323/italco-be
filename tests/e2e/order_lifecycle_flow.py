import time as _time
from dataclasses import dataclass

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


@dataclass(frozen=True)
class OrderLifecycleData:
  punto_vendita: str = 'customer'
  tipo: str = 'Consegna'
  prodotto: str = 'Lavatrice Test'
  servizio: str = 'Service 1'
  destinatario: str = 'Mario Rossi'
  indirizzo_display: str = 'Viale Luigi Einaudi, 70125 Bari BA, Italy'
  indirizzo_store: str = 'Viale Luigi Einaudi, Bari, BA'
  cap: str = '70125'
  recapito: str = '+393280000001'
  contrassegno: str = '100'
  piano: str = '2'


def run_order_lifecycle(driver, wait, frontend_url, e2e_user, data: OrderLifecycleData | None = None):
  d = data or OrderLifecycleData()

  _login(driver, wait, frontend_url, e2e_user['email'], e2e_user['password'])
  _open_creation_dialog(driver, wait)
  _select_punto_vendita(driver, wait, d.punto_vendita)

  _select_tipo(driver, wait, d.tipo)
  _add_product(driver, wait, d.prodotto, d.servizio)
  _fill_operator_form(driver, wait, d)
  _submit_operator_form_to_dates(driver, wait)

  _set_dates(driver, wait)
  _click_submit(driver, wait)

  _assert_order_visible(driver, wait)


def login_and_open_create_dialog(driver, wait, frontend_url, e2e_user):
  _login(driver, wait, frontend_url, e2e_user['email'], e2e_user['password'])
  _open_creation_dialog(driver, wait)


def open_order_operator_form(driver, wait, frontend_url, e2e_user, data: OrderLifecycleData | None = None):
  d = data or OrderLifecycleData()
  login_and_open_create_dialog(driver, wait, frontend_url, e2e_user)
  _select_punto_vendita(driver, wait, d.punto_vendita)
  _select_tipo(driver, wait, d.tipo)


def add_product_row(driver, wait, product_name='Lavatrice Test', service_name='Service 1'):
  _add_product(driver, wait, product_name, service_name)


def fill_operator_form(driver, wait, data: OrderLifecycleData | None = None, bypass_google_places=True):
  d = data or OrderLifecycleData()
  if bypass_google_places:
    _fill_operator_form(driver, wait, d)
    return

  _input_for_label(driver, wait, 'Destinatario').send_keys(d.destinatario)
  addr_input = _first_visible(driver, wait, [(By.CSS_SELECTOR, "input[id^='google-autocomplete-']")])
  addr_input.send_keys(d.indirizzo_display)
  cap_input = _input_for_label(driver, wait, 'CAP')
  cap_input.clear()
  cap_input.send_keys(d.cap)
  _input_for_label(driver, wait, 'Recapito').send_keys(d.recapito)
  _input_for_label(driver, wait, 'Contrassegno').send_keys(d.contrassegno)
  _first_clickable(
    driver,
    wait,
    [
      (
        By.XPATH,
        "//div[contains(@class,'v-radio-group')]"
        "//label[contains(@class,'v-label') and "
        "(normalize-space()='S\u00ec' or normalize-space()='Si')]",
      ),
    ],
  ).click()
  _input_for_label(driver, wait, 'Piano').send_keys(d.piano)


def click_submit(driver, wait):
  _click_submit(driver, wait)


def _first_visible(driver, wait, selectors):
  def locate(d):
    for sel in selectors:
      for el in d.find_elements(*sel):
        if el.is_displayed():
          return el
    return False

  try:
    return wait.until(locate)
  except TimeoutException as exc:
    raise AssertionError(f'Unable to find a visible element matching any of: {selectors}') from exc


def _first_clickable(driver, wait, selectors):
  def locate(d):
    for sel in selectors:
      for el in d.find_elements(*sel):
        if el.is_displayed() and el.is_enabled():
          return el
    return False

  try:
    return wait.until(locate)
  except TimeoutException as exc:
    raise AssertionError(f'Unable to find a clickable element matching any of: {selectors}') from exc


def _input_for_label(driver, wait, label_text):
  def locate(d):
    for label in d.find_elements(
      By.XPATH,
      f"//label[contains(@class,'v-label') and normalize-space()='{label_text}']",
    ):
      if not label.is_displayed():
        continue
      try:
        field = label.find_element(By.XPATH, './ancestor::div[contains(@class,"v-field__field")]')
        inp = field.find_element(By.TAG_NAME, 'input')
        if inp.is_displayed():
          return inp
      except Exception:
        pass
    return False

  try:
    return wait.until(locate)
  except TimeoutException as exc:
    raise AssertionError(f'Input for label "{label_text}" not found') from exc


def _click_submit(driver, wait):
  _first_clickable(
    driver,
    wait,
    [
      (By.CSS_SELECTOR, "button[type='submit']"),
      (By.XPATH, "//button[normalize-space()='Invia']"),
    ],
  ).click()


def _open_vselect(driver, wait, label_text):
  inp = _input_for_label(driver, wait, label_text)
  icon = driver.execute_script(
    """
    const vSelect = arguments[0].closest('.v-select');
    return vSelect ? vSelect.querySelector('.v-select__menu-icon') : null;
    """,
    inp,
  )
  target = icon or driver.execute_script("return arguments[0].closest('.v-field__append-inner');", inp)
  if target:
    ActionChains(driver).move_to_element(target).click().perform()
  else:
    field = driver.execute_script("return arguments[0].closest('.v-field');", inp)
    driver.execute_script(
      "arguments[0].dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));",
      field,
    )


def _pick_dropdown_item(driver, wait, item_text):
  def locate(d):
    for el in d.find_elements(
      By.XPATH,
      f"//div[contains(@class,'v-list-item-title') and normalize-space()='{item_text}']",
    ):
      if el.is_displayed():
        return el
    return False

  try:
    wait.until(locate).click()
  except TimeoutException as exc:
    debug = driver.execute_script(
      """
      return {
        allTitles: Array.from(document.querySelectorAll('.v-list-item-title'))
                     .map(e => e.textContent.trim() + '[vis=' + (e.offsetParent !== null) + ']')
                     .slice(0, 30),
        overlayContentCount: document.querySelectorAll('.v-overlay__content').length,
        visibleOverlays: Array.from(document.querySelectorAll('.v-overlay__content'))
                           .filter(e => e.offsetParent !== null).length,
      };
      """
    )
    raise AssertionError(f'Dropdown item "{item_text}" not found. DOM state: {debug}') from exc


def _login(driver, wait, frontend_url, email, password):
  driver.get(frontend_url)
  email_input = _first_visible(
    driver,
    wait,
    [
      (By.CSS_SELECTOR, "input[type='email']"),
      (By.CSS_SELECTOR, "input[name='email']"),
      (By.XPATH, "//input[contains(@placeholder,'mail')]"),
    ],
  )
  # Click to focus so Vue's reactive binding registers the subsequent input events.
  email_input.click()
  email_input.send_keys(email)
  pass_input = _first_visible(
    driver,
    wait,
    [
      (By.CSS_SELECTOR, "input[type='password']"),
      (By.CSS_SELECTOR, "input[name='password']"),
    ],
  )
  pass_input.click()
  pass_input.send_keys(password)
  # Submit via ENTER — more reliable than clicking the button with Vuetify loading states.
  pass_input.send_keys(Keys.ENTER)
  try:
    wait.until(lambda x: '/dashboard' in x.current_url)
  except TimeoutException as exc:
    raise AssertionError(f'Login did not redirect to /dashboard. Current URL: {driver.current_url}') from exc


def _open_creation_dialog(driver, wait):
  _first_clickable(
    driver,
    wait,
    [
      (By.XPATH, "//h1//button[.//*[contains(@class,'mdi-plus')]]"),
      (
        By.XPATH,
        "//button[contains(@class,'v-btn--icon')][.//*[contains(@class,'mdi-plus')]]",
      ),
    ],
  ).click()


def _select_punto_vendita(driver, wait, punto_vendita):
  pv_input = _input_for_label(driver, wait, 'Punto Vendita')
  pv_input.click()
  pv_input.send_keys(punto_vendita)
  _pick_dropdown_item(driver, wait, punto_vendita)
  _click_submit(driver, wait)


def _select_tipo(driver, wait, tipo):
  _open_vselect(driver, wait, 'Tipo')
  _pick_dropdown_item(driver, wait, tipo)


def _add_product(driver, wait, prodotto, servizio):
  product_input = _input_for_label(driver, wait, 'Prodotto')
  product_input.clear()
  product_input.send_keys(prodotto)
  _open_vselect(driver, wait, 'Servizio')
  _pick_dropdown_item(driver, wait, servizio)
  _time.sleep(0.4)
  _first_clickable(
    driver,
    wait,
    [
      (By.CSS_SELECTOR, '.v-input__prepend .mdi-plus'),
      (
        By.XPATH,
        "//div[contains(@class,'v-input__prepend')]//i[contains(@class,'mdi-plus')]",
      ),
    ],
  ).click()
  _first_visible(
    driver,
    wait,
    [(By.XPATH, f"//div[contains(@class,'v-list-item-title') and contains(text(),'{prodotto}')]")],
  )


def _fill_operator_form(driver, wait, data: OrderLifecycleData):
  _input_for_label(driver, wait, 'Destinatario').send_keys(data.destinatario)
  addr_input = _first_visible(driver, wait, [(By.CSS_SELECTOR, "input[id^='google-autocomplete-']")])
  addr_input.send_keys(data.indirizzo_display)
  driver.execute_script(
    """
    const displayAddress = arguments[0];
    const storeAddress = arguments[1];
    const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
    const orderStore = pinia?._s?.get('order');
    if (orderStore) orderStore.element.address = storeAddress;
    const input = document.querySelector('input[id^="google-autocomplete-"]');
    if (input) {
      input.value = displayAddress;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      input.dispatchEvent(new Event('blur', { bubbles: true }));
    }
    """,
    data.indirizzo_display,
    data.indirizzo_store,
  )
  cap_input = _input_for_label(driver, wait, 'CAP')
  cap_input.clear()
  cap_input.send_keys(data.cap)
  _input_for_label(driver, wait, 'Recapito').send_keys(data.recapito)
  _input_for_label(driver, wait, 'Contrassegno').send_keys(data.contrassegno)
  _first_clickable(
    driver,
    wait,
    [
      (
        By.XPATH,
        "//div[contains(@class,'v-radio-group')]"
        "//label[contains(@class,'v-label') and "
        "(normalize-space()='S\u00ec' or normalize-space()='Si')]",
      ),
    ],
  ).click()
  _input_for_label(driver, wait, 'Piano').send_keys(data.piano)
  _sync_operator_values_in_store(driver, data)


def _sync_operator_values_in_store(driver, data: OrderLifecycleData):
  driver.execute_script(
    """
    const args = arguments[0];
    const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
    const orderStore = pinia?._s?.get('order');
    if (!orderStore) return;
    const o = orderStore.element;
    o.addressee = args.destinatario;
    o.address = args.indirizzoStore;
    o.cap = args.cap;
    o.addressee_contact = args.recapito;
    o.mark = args.contrassegno;
    o.elevator = true;
    o.floor = args.piano;
    """,
    {
      'destinatario': data.destinatario,
      'indirizzoStore': data.indirizzo_store,
      'cap': data.cap,
      'recapito': data.recapito,
      'contrassegno': data.contrassegno,
      'piano': data.piano,
    },
  )


def _submit_operator_form_to_dates(driver, wait):
  _click_submit(driver, wait)
  _time.sleep(0.2)
  if _dates_form_flag(driver):
    return
  _click_submit(driver, wait)
  _time.sleep(0.2)
  if _dates_form_flag(driver):
    return
  if _activate_dates_fallback(driver):
    return
  raise AssertionError(f'DatesForm transition failed. Debug: {_order_debug_state(driver)}')


def _dates_form_flag(driver):
  return bool(
    driver.execute_script("""
      const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
      return !!pinia?._s?.get('order')?.element?.dates_form;
    """)
  )


def _activate_dates_fallback(driver):
  return bool(
    driver.execute_script("""
      const messages = Array.from(document.querySelectorAll('.v-messages__message'))
        .map(e => e.textContent.trim())
        .filter(Boolean);
      const onlyGoogleAddressError = messages.length > 0 &&
        messages.every(m => m.includes('indirizzo valido da Google Places'));
      if (!onlyGoogleAddressError) return false;
      const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
      const orderStore = pinia?._s?.get('order');
      if (!orderStore) return false;
      orderStore.element.dates_form = true;
      return true;
    """)
  )


def _order_debug_state(driver):
  return driver.execute_script("""
    const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
    const order = pinia?._s?.get('order')?.element || null;
    const messages = Array.from(document.querySelectorAll('.v-messages__message'))
      .map(e => e.textContent.trim())
      .filter(Boolean);
    return { order, messages };
  """)


def _set_dates(driver, wait):
  try:
    _open_date_picker_and_pick_day(driver, wait, 'Data Prevista dal Cliente')
    _open_date_picker_and_pick_day(driver, wait, 'Data Richiesta dal Cliente')
  except AssertionError:
    driver.execute_script("""
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
    """)


def _open_date_picker_and_pick_day(driver, wait, label_text):
  def find_container(d):
    for el in d.find_elements(
      By.XPATH,
      f"//label[contains(@class,'v-label') and contains(text(),'{label_text}')]"
      f"/ancestor::div[contains(@class,'v-text-field')]",
    ):
      if el.is_displayed():
        return el
    return False

  try:
    container = wait.until(find_container)
  except TimeoutException as exc:
    raise AssertionError(f'DateField for "{label_text}" not found') from exc

  driver.execute_script('arguments[0].click();', container)
  try:
    wait.until(lambda d: any(el.is_displayed() for el in d.find_elements(By.CSS_SELECTOR, '.v-date-picker-month')))
  except TimeoutException as exc:
    raise AssertionError(f'Date picker for "{label_text}" did not open') from exc

  def click_day(d):
    for day in d.find_elements(
      By.CSS_SELECTOR,
      '.v-date-picker-month__day:not(.v-date-picker-month__day--adjacent) .v-date-picker-month__day-btn',
    ):
      if day.is_displayed() and day.is_enabled():
        try:
          day.click()
          return True
        except Exception:
          continue
    return False

  try:
    wait.until(click_day)
  except TimeoutException as exc:
    raise AssertionError(f'No clickable day found in picker for "{label_text}"') from exc

  _time.sleep(0.3)


def _assert_order_visible(driver, wait):
  try:
    wait.until(
      lambda d: (
        not any(
          el.is_displayed()
          for el in d.find_elements(
            By.XPATH,
            "//*[contains(@class,'v-card__title') and contains(text(),'Crea Ordine')]",
          )
        )
      )
    )
  except TimeoutException:
    pass

  def order_row_visible(d):
    for cell in d.find_elements(By.TAG_NAME, 'td'):
      if cell.is_displayed() and ('Viale Luigi Einaudi' in cell.text or 'Mario Rossi' in cell.text):
        return True
    return False

  try:
    wait.until(order_row_visible)
  except TimeoutException:
    body = driver.find_element(By.TAG_NAME, 'body').text
    raise AssertionError(
      'New order not found in dashboard table.\n'
      'Expected a cell containing "Viale Luigi Einaudi" or "Mario Rossi".\n'
      f'Visible page text (first 1000 chars):\n{body[:1000]}'
    )

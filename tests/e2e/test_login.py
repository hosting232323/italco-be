import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

pytestmark = pytest.mark.e2e


def _first_visible(driver, wait, selectors):
  def locate(current_driver):
    for selector in selectors:
      for element in current_driver.find_elements(*selector):
        if element.is_displayed():
          return element
    return False

  try:
    return wait.until(locate)
  except TimeoutException as exc:
    raise AssertionError(f'Unable to find a visible element with selectors: {selectors}') from exc


def _first_clickable(driver, wait, selectors):
  def locate(current_driver):
    for selector in selectors:
      for element in current_driver.find_elements(*selector):
        if element.is_displayed() and element.is_enabled():
          return element
    return False

  try:
    return wait.until(locate)
  except TimeoutException as exc:
    raise AssertionError(f'Unable to find a clickable element with selectors: {selectors}') from exc


def test_login_redirects_to_dashboard(driver, wait, frontend_reachable, e2e_user):
  """
  Main test flow:

  1. Opens login page (frontend_reachable fixture).
  2. Finds email/password inputs via fallback selectors.
  3. Fills credentials from e2e_user.
  4. Submits with Keys.ENTER (less click-flaky with Vuetify loading states).
  5. Waits for URL to include /dashboard.
  6. On timeout, raises diagnostic assertion with URL + body text snippet.
  7. Final assertions confirm redirect and no "Credenziali errate" text.
  """
  driver.get(frontend_reachable)

  email = _first_visible(
    driver,
    wait,
    [
      (By.CSS_SELECTOR, "input[type='email']"),
      (By.CSS_SELECTOR, "input[name='email']"),
      (By.XPATH, "//input[contains(@placeholder, 'mail') or contains(@placeholder, 'Email')]"),
    ],
  )
  password = _first_visible(
    driver,
    wait,
    [
      (By.CSS_SELECTOR, "input[type='password']"),
      (By.CSS_SELECTOR, "input[name='password']"),
    ],
  )
  email.clear()
  email.send_keys(e2e_user['email'])
  password.clear()
  password.send_keys(e2e_user['password'])
  login_button = _first_clickable(
    driver,
    wait,
    [
      (By.CSS_SELECTOR, "button[type='submit']"),
      (By.XPATH, "//button[normalize-space()='LOGIN' or normalize-space()='Login']"),
      (By.XPATH, "//button[contains(., 'LOGIN') or contains(., 'Login')]"),
    ],
  )
  login_button.click()
  try:
    wait.until(lambda current_driver: '/dashboard' in current_driver.current_url)
  except TimeoutException:
    page_text = driver.find_element(By.TAG_NAME, 'body').text
    raise AssertionError(
      f'Login did not redirect to /dashboard. Current URL: {driver.current_url}. Visible page text: {page_text[:600]}'
    )
  assert '/dashboard' in driver.current_url
  assert 'Credenziali errate' not in driver.find_element(By.TAG_NAME, 'body').text

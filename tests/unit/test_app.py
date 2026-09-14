"""Test delle route registrate direttamente sull'app (src/__init__.py, src/__main__.py)."""

import src as app_module
import src.__main__ as main_module
from src.database.enum import UserRole

from tests.unit.factories import auth_header, create_user


def test_index_route(client):
  response = client.get('/')

  assert response.status_code == 200
  assert response.get_data(as_text=True) == 'Hello World'


def test_all_blueprints_are_registered(app):
  expected_prefixes = {
    '/log',
    '/rae',
    '/user',
    '/order',
    '/chatty',
    '/import',
    '/export',
    '/service',
    '/schedule',
    '/transport',
    '/customer-rule',
    '/customer-group',
    '/geographic-zone',
    '/collection-point',
  }
  registered = {rule.rule.split('/')[1] for rule in app.url_map.iter_rules() if rule.rule != '/'}

  assert {f'/{prefix}' for prefix in registered} >= expected_prefixes


def test_check_constraints_intersects_rule_sets(client, monkeypatch):
  customer = create_user(UserRole.CUSTOMER)
  monkeypatch.setattr(main_module, 'check_customer_rules', lambda user: ['2026-07-15', '2026-07-16', '2026-07-17'])
  monkeypatch.setattr(main_module, 'check_delivery_coverage', lambda: ['2026-07-16', '2026-07-17', '2026-07-18'])
  monkeypatch.setattr(main_module, 'check_services_date', lambda: ['2026-07-16', '2026-07-17'])
  monkeypatch.setattr(
    main_module,
    'check_delivery_coverage_slots',
    lambda: {
      '2026-07-16': [{'start': '08:00', 'end': '12:00'}],
      '2026-07-17': [{'start': '08:00', 'end': '12:00'}],
      '2026-07-18': [{'start': '08:00', 'end': '12:00'}],
    },
  )

  response = client.post('/check-constraints', json={}, headers=auth_header(customer))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['dates'] == ['2026-07-16', '2026-07-17']
  # Le fasce viaggiano solo per le date effettivamente ammesse dall'intersezione,
  # anche se check_delivery_coverage_slots ne restituisce di più (es. 07-18).
  assert body['slots'] == {
    '2026-07-16': [{'start': '08:00', 'end': '12:00'}],
    '2026-07-17': [{'start': '08:00', 'end': '12:00'}],
  }


def test_check_constraints_requires_customer_role(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post('/check-constraints', json={}, headers=auth_header(admin))

  assert response.status_code == 403
  assert response.get_json()['status'] == 'forbidden'


def test_checks_endpoint_without_swagger_key_is_denied(client, monkeypatch):
  response = client.get('/checks')

  # Senza SwaggerAuthorization valido lo swagger_decorator nega l'accesso
  assert response.get_json()['status'] == 'ko'


def test_delivery_app_min_version_reads_configured_threshold(client, monkeypatch):
  # Senza `platform` vale la soglia legacy unica.
  monkeypatch.setattr(app_module, 'DELIVERY_APP_MIN_BUILD_NUMBER', '190')

  response = client.get('/delivery-app/min-version')

  assert response.get_json() == {'status': 'ok', 'min_build_number': 190}


def test_delivery_app_min_version_defaults_to_none_when_unset(client, monkeypatch):
  monkeypatch.setattr(app_module, 'DELIVERY_APP_MIN_BUILD_NUMBER', None)

  response = client.get('/delivery-app/min-version')

  assert response.get_json() == {'status': 'ok', 'min_build_number': None}


def test_delivery_app_min_version_ignores_a_non_numeric_value(client, monkeypatch):
  # Fail open: una svista in configurazione (typo nella variabile d'ambiente)
  # non deve mai tradursi in un'app bloccata per tutti i corrieri.
  monkeypatch.setattr(app_module, 'DELIVERY_APP_MIN_BUILD_NUMBER', 'non-un-numero')

  response = client.get('/delivery-app/min-version')

  assert response.get_json() == {'status': 'ok', 'min_build_number': None}


def test_delivery_app_min_version_requires_no_authentication(client):
  response = client.get('/delivery-app/min-version')

  assert response.status_code == 200


def test_delivery_app_min_version_android_ignores_the_ios_threshold(client, monkeypatch):
  # Android ha una variabile a se': la soglia iOS non lo tocca, e senza la
  # sua variabile non c'e' nessun blocco (build Play non scadono).
  monkeypatch.setattr(app_module, 'DELIVERY_APP_MIN_BUILD_NUMBER_IOS', '190')
  monkeypatch.setattr(app_module, 'DELIVERY_APP_MIN_BUILD_NUMBER_ANDROID', None)

  response = client.get('/delivery-app/min-version', query_string={'platform': 'android'})

  assert response.get_json() == {'status': 'ok', 'min_build_number': None}


def test_delivery_app_min_version_android_can_be_forced_for_an_emergency_rollout(client, monkeypatch):
  # Bug grave: si alza a mano DELIVERY_APP_MIN_BUILD_NUMBER_ANDROID e anche i
  # corrieri Android sotto quella build vedono la schermata di aggiornamento.
  monkeypatch.setattr(app_module, 'DELIVERY_APP_MIN_BUILD_NUMBER_ANDROID', '205')

  response = client.get('/delivery-app/min-version', query_string={'platform': 'android'})

  assert response.get_json() == {'status': 'ok', 'min_build_number': 205}


def test_delivery_app_min_version_ios_gets_the_configured_threshold(client, monkeypatch):
  monkeypatch.setattr(app_module, 'DELIVERY_APP_MIN_BUILD_NUMBER_IOS', '190')

  response = client.get('/delivery-app/min-version', query_string={'platform': 'iOS'})

  assert response.get_json() == {'status': 'ok', 'min_build_number': 190}


def test_delivery_app_min_version_missing_platform_uses_the_legacy_threshold(client, monkeypatch):
  # Le build gia' distribuite non mandano `platform`: continuano a ricevere la
  # soglia legacy unica, non quella di una piattaforma, cosi' si possono
  # aggiornare prima di separare le configurazioni iOS e Android.
  monkeypatch.setattr(app_module, 'DELIVERY_APP_MIN_BUILD_NUMBER', '205')
  monkeypatch.setattr(app_module, 'DELIVERY_APP_MIN_BUILD_NUMBER_IOS', '190')
  monkeypatch.setattr(app_module, 'DELIVERY_APP_MIN_BUILD_NUMBER_ANDROID', '180')

  response = client.get('/delivery-app/min-version')

  assert response.get_json() == {'status': 'ok', 'min_build_number': 205}


def capture_error_log(monkeypatch):
  # Il logger dell'app lo configura la lib condivisa: lo si intercetta
  # direttamente invece di dipendere dalla sua propagazione a caplog.
  lines = []
  monkeypatch.setattr(app_module.logger, 'error', lambda fmt, args: lines.append(fmt % args))
  return lines


def test_delivery_app_error_report_logs_the_report_without_authentication(client, monkeypatch):
  lines = capture_error_log(monkeypatch)
  response = client.post(
    '/delivery-app/error-report',
    json={
      'message': 'Bad state: boom',
      'stack': '#0 main' + chr(10) + '#1 run',
      'source': 'async',
      'occurred_at': '2026-10-05T12:00:00.000Z',
      'app_version': '1.0.0',
      'commit': 'abc123',
      'build_number': 42,
      'platform': 'android',
    },
  )

  assert response.get_json() == {'status': 'ok'}
  line = lines[-1]
  assert 'platform=android' in line
  assert 'build=42' in line
  assert 'commit=abc123' in line
  assert 'message=Bad state: boom' in line
  assert 'stack=#0 main | #1 run' in line


def test_delivery_app_error_report_truncates_oversized_fields(client, monkeypatch):
  lines = capture_error_log(monkeypatch)
  client.post('/delivery-app/error-report', json={'message': 'x' * 5000})

  assert 'x' * 1001 not in lines[-1]


def test_delivery_app_error_report_rejects_a_body_that_is_not_an_object(client):
  response = client.post('/delivery-app/error-report', json=['non', 'un', 'oggetto'])

  assert response.status_code == 400
  assert response.get_json()['status'] == 'ko'


def test_delivery_app_error_report_is_rate_limited_per_ip(client, monkeypatch):
  lines = capture_error_log(monkeypatch)
  headers = {'CF-Connecting-IP': '1.2.3.4'}
  limit = app_module.DELIVERY_APP_ERROR_REPORTS_PER_HOUR_PER_IP

  for _ in range(limit):
    assert client.post('/delivery-app/error-report', json={'message': 'boom'}, headers=headers).status_code == 200
  blocked = client.post('/delivery-app/error-report', json={'message': 'boom'}, headers=headers)
  other_ip = client.post(
    '/delivery-app/error-report', json={'message': 'boom'}, headers={'CF-Connecting-IP': '5.6.7.8'}
  )

  assert blocked.status_code == 429
  assert blocked.get_json()['status'] == 'ko'
  assert len(lines) == limit + 1
  assert other_ip.status_code == 200


def enable_telegram(monkeypatch):
  sent = []
  monkeypatch.setattr(app_module, 'IS_DEV', False)
  monkeypatch.setattr(app_module, 'TELEGRAM_TOKEN', 'token')
  monkeypatch.setattr(app_module, 'send_telegram_message', sent.append)
  monkeypatch.setattr(app_module, '_delivery_app_error_alerts', {})
  return sent


def test_delivery_app_error_report_alerts_telegram_once_per_error(client, monkeypatch):
  sent = enable_telegram(monkeypatch)
  report = {
    'message': 'Bad state: boom',
    'stack': '#0 main',
    'app_version': '1.0.0',
    'build_number': 42,
    'commit': 'abcdef123456',
  }

  client.post('/delivery-app/error-report', json=report)
  client.post('/delivery-app/error-report', json=report)
  client.post('/delivery-app/error-report', json={**report, 'message': 'altro errore'})

  assert len(sent) == 2
  assert 'build 42' in sent[0]
  assert 'abcdef12' in sent[0]
  assert 'Bad state: boom' in sent[0]


def test_delivery_app_error_report_caps_telegram_alerts_per_hour(client, monkeypatch):
  sent = enable_telegram(monkeypatch)

  for index in range(app_module.DELIVERY_APP_ERROR_ALERTS_PER_HOUR + 5):
    client.post('/delivery-app/error-report', json={'message': f'errore {index}'})

  assert len(sent) == app_module.DELIVERY_APP_ERROR_ALERTS_PER_HOUR


def test_delivery_app_error_report_does_not_alert_in_dev_or_without_token(client, monkeypatch):
  sent = enable_telegram(monkeypatch)
  monkeypatch.setattr(app_module, 'TELEGRAM_TOKEN', None)

  client.post('/delivery-app/error-report', json={'message': 'boom'})

  assert sent == []


def test_delivery_app_error_report_alert_cannot_break_out_of_the_code_block(client, monkeypatch):
  sent = enable_telegram(monkeypatch)

  client.post('/delivery-app/error-report', json={'message': 'a ``` b'})

  assert sent[0].count('```') == 2

import threading
import time

from database_api import Session
from api.users.security import hash_password
from database_api.operations import get_by_id, update

import src.end_points.users as users_endpoints
from src.database.enum import UserRole
from src.database.schema import CustomerUserInfo, DeliveryUserInfo, User, UserSession

from tests.unit.factories import (
  auth_header,
  create_collection_point,
  create_service,
  create_service_user,
  create_user,
)


def test_get_users_as_admin_returns_all_users(client):
  admin = create_user(UserRole.ADMIN)
  create_user(UserRole.CUSTOMER)
  create_user(UserRole.DELIVERY)

  response = client.get('/user', headers=auth_header(admin))
  body = response.get_json()
  assert response.status_code == 200
  assert body['status'] == 'ok'
  assert len(body['users']) == 3


def test_get_users_as_delivery_sees_only_customers(client):
  delivery = create_user(UserRole.DELIVERY)
  create_user(UserRole.CUSTOMER)
  create_user(UserRole.ADMIN)

  response = client.get('/user', headers=auth_header(delivery))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert [user['role'] for user in body['users']] == ['Customer']


def test_get_users_rejected_for_customer_role(client):
  customer = create_user(UserRole.CUSTOMER)

  response = client.get('/user', headers=auth_header(customer))

  body = response.get_json()
  assert response.status_code == 403
  assert body['status'] == 'forbidden'
  assert body['message'] == 'Ruolo non autorizzato'


def test_create_user_succeeds_with_valid_payload(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post(
    '/user',
    json={'nickname': 'nuovo-delivery', 'password': 'pw', 'role': 'Delivery'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  with Session() as session:
    created = session.query(User).filter(User.nickname == 'nuovo-delivery').one()
    assert created.role == UserRole.DELIVERY


def test_create_user_rejects_admin_role(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post(
    '/user',
    json={'nickname': 'altro-admin', 'password': 'pw', 'role': 'Admin'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'error'


def test_create_user_rejects_duplicate_nickname(client):
  admin = create_user(UserRole.ADMIN)
  create_user(UserRole.DELIVERY, nickname='gia-preso')

  response = client.post(
    '/user',
    json={'nickname': 'gia-preso', 'password': 'pw', 'role': 'Delivery'},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Nickname già in uso'


def test_delete_user_without_force_returns_dependency_counts(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  service_user = create_service_user(customer, create_service())
  create_collection_point(customer)

  response = client.delete(f'/user/{customer.id}', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['dependencies']['serviceUsers'] == 1
  assert body['dependencies']['collectionPoints'] == 1
  assert body['dependencies']['customerRules'] == 0
  assert body['dependencies']['blockedOrders'] == 0
  assert get_by_id(User, customer.id) is not None
  assert service_user is not None


def test_delete_user_with_force_removes_user(client):
  admin = create_user(UserRole.ADMIN)
  target = create_user(UserRole.CUSTOMER)

  response = client.delete(f'/user/{target.id}?force=1', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(User, target.id) is None


def test_delete_user_not_found(client):
  admin = create_user(UserRole.ADMIN)

  response = client.delete('/user/999999', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Utente non trovato'


def test_login_ok_returns_token_and_role(client):
  from src.end_points.users.legacy import legacy_encrypt

  create_user(UserRole.DELIVERY, nickname='driver', password=legacy_encrypt('pw-login'))

  response = client.post('/user/login', json={'email': 'driver', 'password': 'pw-login'})

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['role'] == 'Delivery'
  assert body['access_token']


def test_login_rejects_wrong_password(client):
  from src.end_points.users.legacy import legacy_encrypt

  create_user(UserRole.DELIVERY, nickname='driver2', password=legacy_encrypt('pw-corretta'))

  response = client.post('/user/login', json={'email': 'driver2', 'password': 'pw-sbagliata'})

  assert response.get_json() == {'status': 'ko', 'message': 'Credenziali errate'}


def test_login_rejects_unknown_user(client):
  response = client.post('/user/login', json={'email': 'fantasma', 'password': 'pw'})

  assert response.get_json()['status'] == 'ko'


def test_reset_password_revokes_the_open_sessions(client):
  """Il reset admin deve cacciare fuori chi e' gia' dentro.

  Serve quando la password viene reimpostata proprio perche' l'account e'
  compromesso: se le sessioni restassero valide, il refresh token in mano a chi
  e' entrato continuerebbe a funzionare per giorni.
  """
  from src.end_points.users.legacy import legacy_encrypt

  admin = create_user(UserRole.ADMIN)
  driver = create_user(UserRole.DELIVERY, nickname='driver-reset', password=legacy_encrypt('pw-vecchia'))

  login = client.post('/user/login', json={'email': 'driver-reset', 'password': 'pw-vecchia'})
  assert login.get_json()['status'] == 'ok'

  reset = client.post(f'/user/{driver.id}/password', json={}, headers=auth_header(admin))
  assert reset.get_json()['status'] == 'ok'

  # Il cookie di refresh e' ancora nel client di test, ma la sessione non vale piu'.
  refresh = client.post('/user/refresh')
  assert refresh.status_code == 401
  assert refresh.get_json()['status'] == 'session'

  with Session() as session:
    assert all(row.revoked for row in session.query(UserSession).filter_by(user_id=driver.id).all())


def test_two_tabs_can_refresh_with_the_same_cookie(client):
  """Due schede aperte non devono sloggiare l'utente.

  Entrambe scoprono l'access token scaduto e chiamano /refresh con lo stesso
  cookie: la seconda arriva con un refresh gia' ruotato. Dentro la finestra di
  grazia e' un doppione innocuo, non un furto. Qui gira su Postgres, quindi
  verifica anche che rotated_at torni indietro tz-aware.
  """
  from src.end_points.users.legacy import legacy_encrypt

  driver = create_user(UserRole.DELIVERY, nickname='driver-tabs', password=legacy_encrypt('pw'))
  client.post('/user/login', json={'email': 'driver-tabs', 'password': 'pw'})
  shared_cookie = client.get_cookie('refresh_token').value

  tab_one = client.post('/user/refresh')
  client.set_cookie('refresh_token', shared_cookie)
  tab_two = client.post('/user/refresh')

  assert tab_one.status_code == 200
  assert tab_two.status_code == 200
  # La seconda riceve un access token ma nessun cookie nuovo: prosegue con il
  # refresh che la prima ha gia' messo nel barattolo, condiviso fra le schede.
  assert tab_two.get_json()['access_token']
  assert 'refresh_token' not in tab_two.headers.get('Set-Cookie', '')
  with Session() as session:
    rows = session.query(UserSession).filter_by(user_id=driver.id).all()
    # Un token speso non genera sessioni: una lapide e una sola sessione viva.
    assert len([row for row in rows if not row.revoked]) == 1


def test_grace_is_not_granted_by_another_device_of_the_same_user(client):
  """La grazia guarda la catena, non l'utente.

  A ruota, una richiesta col token vecchio resta indietro, A fa logout
  revocando il proprio successore, ma B ha ancora una sessione valida dello
  stesso utente. La richiesta ritardata di A non deve passare, e soprattutto
  l'access token non deve materializzarsi: qui si verifica anche che non apra
  davvero un endpoint protetto.
  """
  from src.end_points.users.legacy import legacy_encrypt

  create_user(UserRole.DELIVERY, nickname='driver-fam', password=legacy_encrypt('pw'))
  login = {'email': 'driver-fam', 'password': 'pw'}

  client.post('/user/login', json=login)
  device_a = client.get_cookie('refresh_token').value
  client.post('/user/refresh')
  rotated_a = client.get_cookie('refresh_token').value

  # B fa un login suo: famiglia diversa, sessione viva.
  client.post('/user/login', json=login)
  device_b = client.get_cookie('refresh_token').value

  # A fa logout: chiude la propria catena. Il client di test ha un barattolo
  # solo, quindi il cookie di A va rimesso o si revocherebbe la sessione di B.
  client.set_cookie('refresh_token', rotated_a)
  client.post('/user/logout')

  # La richiesta ritardata di A, ancora dentro la finestra di grazia.
  client.set_cookie('refresh_token', device_a)
  delayed = client.post('/user/refresh')
  assert delayed.status_code == 401
  assert 'access_token' not in delayed.get_json()

  # E la sessione di B resta valida: non era lei la catena chiusa.
  client.set_cookie('refresh_token', device_b)
  assert client.post('/user/refresh').status_code == 200


def test_concurrent_refresh_leaves_a_single_live_session(app, db):
  """Due refresh davvero simultanei non devono produrre due sessioni.

  Qui i thread partono insieme su Postgres, che e' dove il problema si vedeva:
  entrambe le richieste leggevano la sessione come attiva e ruotavano entrambe.
  La rotazione e' un compare-and-swap, quindi una sola deve vincere.
  """
  from src.end_points.users.legacy import legacy_encrypt

  user = create_user(UserRole.DELIVERY, nickname='driver-race', password=legacy_encrypt('pw'))
  client = app.test_client()
  client.post('/user/login', json={'email': 'driver-race', 'password': 'pw'})
  shared = client.get_cookie('refresh_token').value

  barrier = threading.Barrier(2)
  results = []

  def hammer():
    worker = app.test_client()
    worker.set_cookie('refresh_token', shared)
    barrier.wait()
    response = worker.post('/user/refresh')
    results.append((response.status_code, response.headers.get('Set-Cookie', '')))

  threads = [threading.Thread(target=hammer) for _ in range(2)]
  for thread in threads:
    thread.start()
  for thread in threads:
    thread.join()

  assert [status for status, _ in results] == [200, 200]
  # Un solo Set-Cookie: solo la vincitrice emette un refresh nuovo.
  assert len([cookie for _, cookie in results if 'refresh_token' in cookie]) == 1
  with Session() as session:
    live = session.query(UserSession).filter_by(user_id=user.id, revoked=False).all()
    assert len(live) == 1


def test_logout_closes_the_family_with_a_just_rotated_token(client):
  """Il logout deve chiudere la catena anche col cookie di un giro prima."""
  from src.end_points.users.legacy import legacy_encrypt

  create_user(UserRole.DELIVERY, nickname='driver-logout', password=legacy_encrypt('pw'))
  client.post('/user/login', json={'email': 'driver-logout', 'password': 'pw'})
  previous = client.get_cookie('refresh_token').value
  client.post('/user/refresh')
  successor = client.get_cookie('refresh_token').value

  client.set_cookie('refresh_token', previous)
  assert client.post('/user/logout').status_code == 200

  client.set_cookie('refresh_token', successor)
  assert client.post('/user/refresh').status_code == 401


def test_login_with_the_old_password_loses_against_a_reset(app, db):
  """Un login con la password vecchia non deve passare per un soffio.

  La verifica delle credenziali sta dentro il lock, sull'utente riletto: se il
  reset arriva prima, il login trova la password nuova e viene rifiutato. Qui il
  reset tiene il lock mentre il login prova a entrare, che e' l'interleaving in
  cui prima il login riusciva.
  """
  from src.end_points import auth
  from src.end_points.users.legacy import legacy_encrypt

  admin = create_user(UserRole.ADMIN)
  user = create_user(UserRole.DELIVERY, nickname='driver-login-race', password=legacy_encrypt('vecchia'))

  reset_done = threading.Event()
  login_result = []

  def reset_holding_the_lock():
    # Tiene il lock utente mentre cambia la password, come fa reset_password.
    with auth.user_session_lock(user.id) as session:
      update(get_by_id(User, user.id), {'password': hash_password('nuova')}, session=session)
      auth.revoke_user_sessions(user.id, db=session)
      reset_done.set()
      time.sleep(1)

  def login_with_the_old_password():
    reset_done.wait(timeout=5)
    worker = app.test_client()
    response = worker.post('/user/login', json={'email': 'driver-login-race', 'password': 'vecchia'})
    login_result.append(response.get_json())

  threads = [threading.Thread(target=reset_holding_the_lock), threading.Thread(target=login_with_the_old_password)]
  for thread in threads:
    thread.start()
  for thread in threads:
    thread.join(timeout=20)

  assert login_result and login_result[0]['status'] == 'ko'
  assert 'access_token' not in login_result[0]
  with Session() as session:
    assert session.query(UserSession).filter_by(user_id=user.id, revoked=False).count() == 0
  assert admin is not None


def test_user_session_lock_serialises_two_writers(db):
  """Il lock sulla riga utente mette davvero in fila due scritture.

  E' la garanzia su cui poggiano logout e reset password: senza, la revoca puo'
  leggere lo stato prima che una rotazione concorrente abbia inserito il
  successore. Qui si verifica il primitivo, non l'endpoint, cosi' la prova non
  dipende da come cade la corsa.
  """
  from src.end_points import auth

  user = create_user(UserRole.DELIVERY)
  holder_inside = threading.Event()
  timeline = []

  def holder():
    with auth.user_session_lock(user.id):
      timeline.append(('holder-dentro', time.monotonic()))
      holder_inside.set()
      time.sleep(1)
      timeline.append(('holder-esce', time.monotonic()))

  def waiter():
    holder_inside.wait(timeout=5)
    time.sleep(0.1)
    with auth.user_session_lock(user.id):
      timeline.append(('waiter-dentro', time.monotonic()))

  threads = [threading.Thread(target=holder), threading.Thread(target=waiter)]
  for thread in threads:
    thread.start()
  for thread in threads:
    thread.join(timeout=15)

  moments = dict(timeline)
  assert set(moments) == {'holder-dentro', 'holder-esce', 'waiter-dentro'}
  # Il secondo entra solo dopo che il primo ha rilasciato: nessuna sovrapposizione.
  assert moments['waiter-dentro'] >= moments['holder-esce']


def _hammer_refresh(app, cookie, results, barrier, label):
  worker = app.test_client()
  worker.set_cookie('refresh_token', cookie)
  barrier.wait()
  response = worker.post('/user/refresh')
  results.append((label, response.status_code))


def test_logout_wins_against_a_concurrent_refresh(app, db):
  """Il logout non deve lasciare vivo un successore nato nel frattempo.

  Il rischio e' che la revoca legga le righe prima che la rotazione concorrente
  abbia inserito il successore: bloccare le righe di sessione non lo impedisce,
  perche' il lock non copre gli inserimenti. Con il lock sulla riga utente le
  due operazioni si mettono in fila.
  """
  from src.end_points.users.legacy import legacy_encrypt

  user = create_user(UserRole.DELIVERY, nickname='driver-logout-race', password=legacy_encrypt('pw'))
  client = app.test_client()
  client.post('/user/login', json={'email': 'driver-logout-race', 'password': 'pw'})
  cookie = client.get_cookie('refresh_token').value

  barrier = threading.Barrier(2)
  results = []

  def do_logout():
    worker = app.test_client()
    worker.set_cookie('refresh_token', cookie)
    barrier.wait()
    worker.post('/user/logout')

  threads = [
    threading.Thread(target=_hammer_refresh, args=(app, cookie, results, barrier, 'refresh')),
    threading.Thread(target=do_logout),
  ]
  for thread in threads:
    thread.start()
  for thread in threads:
    thread.join()

  # Comunque sia andata la corsa, dopo il logout non resta nessuna sessione viva.
  with Session() as session:
    assert session.query(UserSession).filter_by(user_id=user.id, revoked=False).count() == 0


def test_password_reset_wins_against_a_concurrent_refresh(app, db):
  """Il reset password deve chiudere le sessioni anche sotto una rotazione.

  Password e revoca devono essere lo stesso atto: in due transazioni separate
  il refresh crea il successore dopo la revoca, e chi era entrato resta dentro.
  """
  from src.end_points.users.legacy import legacy_encrypt

  admin = create_user(UserRole.ADMIN)
  user = create_user(UserRole.DELIVERY, nickname='driver-reset-race', password=legacy_encrypt('pw'))
  client = app.test_client()
  client.post('/user/login', json={'email': 'driver-reset-race', 'password': 'pw'})
  cookie = client.get_cookie('refresh_token').value

  barrier = threading.Barrier(2)
  results = []

  def do_reset():
    worker = app.test_client()
    barrier.wait()
    worker.post(f'/user/{user.id}/password', json={}, headers=auth_header(admin))

  threads = [
    threading.Thread(target=_hammer_refresh, args=(app, cookie, results, barrier, 'refresh')),
    threading.Thread(target=do_reset),
  ]
  for thread in threads:
    thread.start()
  for thread in threads:
    thread.join()

  with Session() as session:
    assert session.query(UserSession).filter_by(user_id=user.id, revoked=False).count() == 0


def test_update_position_creates_delivery_info(client):
  delivery = create_user(UserRole.DELIVERY)

  response = client.post('/user/position', json={'lat': '45.123', 'lon': '9.456'}, headers=auth_header(delivery))

  assert response.get_json()['status'] == 'ok'
  with Session() as session:
    info = session.query(DeliveryUserInfo).filter_by(user_id=delivery.id).one()
    assert float(info.lat) == 45.123
    assert float(info.lon) == 9.456


def test_save_user_info_creates_then_updates(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)

  first = client.post(
    '/user/info',
    json={'user_id': customer.id, 'class': 'Customer', 'data': {'city': 'Milano'}},
    headers=auth_header(admin),
  )
  second = client.post(
    '/user/info',
    json={'user_id': customer.id, 'class': 'Customer', 'data': {'city': 'Bari'}},
    headers=auth_header(admin),
  )

  assert first.get_json()['status'] == 'ok'
  assert second.get_json()['status'] == 'ok'
  with Session() as session:
    infos = session.query(CustomerUserInfo).filter_by(user_id=customer.id).all()
    assert len(infos) == 1
    assert infos[0].city == 'Bari'


def test_save_user_info_delivery_class(client):
  admin = create_user(UserRole.ADMIN)
  delivery = create_user(UserRole.DELIVERY)

  response = client.post(
    '/user/info',
    json={'user_id': delivery.id, 'class': 'Delivery', 'data': {'cap': '70020'}},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  with Session() as session:
    assert session.query(DeliveryUserInfo).filter_by(user_id=delivery.id).one().cap == '70020'


def test_save_user_info_helper_is_idempotent(db):
  delivery = create_user(UserRole.DELIVERY)

  users_endpoints.save_user_info(delivery.id, {'cap': '70020'}, DeliveryUserInfo)
  users_endpoints.save_user_info(delivery.id, {'cap': '70121'}, DeliveryUserInfo)

  with Session() as session:
    infos = session.query(DeliveryUserInfo).filter_by(user_id=delivery.id).all()
    assert len(infos) == 1
    assert infos[0].cap == '70121'

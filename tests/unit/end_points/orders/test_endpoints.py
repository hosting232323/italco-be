from database_api import Session
from database_api.operations import create, get_by_id

from src.database.enum import OrderStatus, UserRole
from src.database.schema import Motivation, Order, Photo

from tests.unit.factories import (
  auth_header,
  create_order,
  create_product,
  create_user,
  customer_with_service,
)


def _order_payload(service, collection_point, **extra):
  return {
    'type': 'Delivery',
    'addressee': 'Mario Rossi',
    'address': 'Via Roma 1, Bari',
    'cap': '70121',
    'dpc': '2026-07-20',
    'drc': '2026-07-18',
    'products': {
      'Lavatrice': {
        'services': [{'id': service.id}],
        'collection_point': {'id': collection_point.id},
      }
    },
    **extra,
  }


def test_create_order_as_customer(client):
  customer, service, _, collection_point = customer_with_service()

  response = client.post('/order', json=_order_payload(service, collection_point), headers=auth_header(customer))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['order']['status'] == 'Acquired'
  assert body['order']['addressee'] == 'Mario Rossi'
  with Session() as session:
    order = session.query(Order).one()
    assert order.confirmed is False or order.confirmed is None


def test_create_order_as_admin_is_confirmed_and_booked(client):
  admin = create_user(UserRole.ADMIN)
  customer, service, _, collection_point = customer_with_service()

  payload = _order_payload(service, collection_point, booking_date='2026-07-19', user_id=customer.id)
  response = client.post('/order', json=payload, headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['order']['status'] == 'Booked'
  assert body['order']['confirmed'] is True
  assert 'confirmation_date' in body['order']


def test_filter_orders_as_customer_sees_only_own_orders(client):
  customer, service, service_user, _ = customer_with_service()
  other_customer, _, other_service_user, _ = customer_with_service()
  own_order = create_order()
  create_product(own_order, service_user)
  foreign_order = create_order()
  create_product(foreign_order, other_service_user)

  response = client.post('/order/filter', json={'filters': []}, headers=auth_header(customer))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert [order['id'] for order in body['orders']] == [own_order.id]


def test_filter_orders_by_addressee(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  target = create_order(addressee='Mario Rossi')
  create_product(target, service_user)
  other = create_order(addressee='Luigi Verdi')
  create_product(other, service_user)

  response = client.post(
    '/order/filter',
    json={'filters': [{'model': 'Order', 'field': 'addressee', 'value': 'mario'}]},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert [order['id'] for order in body['orders']] == [target.id]


def test_get_order_endpoint_returns_single_order(client):
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)

  response = client.get(f'/order/{order.id}')

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['order']['id'] == order.id
  assert body['order']['price'] == 10.0


def test_get_order_endpoint_unknown_id_returns_generic_error(client):
  response = client.get('/order/999999')

  # L'handler globale trasforma l'eccezione in errore generico
  assert response.get_json() == {'status': 'ko', 'message': 'Errore generico'}


def test_update_order_endpoint_rejects_version_conflict(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)

  response = client.put(
    f'/order/{order.id}',
    json={'id': order.id, 'version': 99, 'operator_note': 'nota'},
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert 'modificato nel frattempo' in body['message']


def test_update_order_endpoint_updates_fields(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)

  response = client.put(
    f'/order/{order.id}',
    json={'id': order.id, 'version': 0, 'operator_note': 'aggiornata'},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(Order, order.id).operator_note == 'aggiornata'


def test_update_order_endpoint_with_motivation_and_status(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order(status=OrderStatus.BOOKING)
  create_product(order, service_user)

  response = client.put(
    f'/order/{order.id}',
    json={
      'id': order.id,
      'status': 'Not Delivered',
      'motivation': 'Cliente assente',
      'delay': False,
      'anomaly': False,
    },
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  refreshed = get_by_id(Order, order.id)
  assert refreshed.status == OrderStatus.NOT_DELIVERED
  assert refreshed.completion_date is not None
  with Session() as session:
    motivation = session.query(Motivation).filter_by(order_id=order.id).one()
    assert motivation.text == 'Cliente assente'


def test_delivery_details_returns_motivations_and_photos(client):
  admin = create_user(UserRole.ADMIN)
  order = create_order()
  create(Motivation, {'order_id': order.id, 'status': OrderStatus.NOT_DELIVERED, 'text': 'assente'})
  create(Photo, {'order_id': order.id, 'link': 'http://example.com/1.jpg'})

  response = client.get(f'/order/delivery-details/{order.id}', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert len(body['motivations']) == 1
  assert body['photos'] == ['http://example.com/1.jpg']


def test_delete_order_endpoint(client):
  admin = create_user(UserRole.ADMIN)
  order = create_order(status=OrderStatus.ACQUIRED)

  response = client.delete(f'/order/{order.id}', headers=auth_header(admin))

  assert response.get_json()['status'] == 'ok'
  assert get_by_id(Order, order.id) is None


def test_get_statuses_endpoint_returns_history(client):
  admin = create_user(UserRole.ADMIN)
  order = create_order(status=OrderStatus.ACQUIRED)

  response = client.get(f'/order/statuses/{order.id}', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['statuses'][0]['status'] == 'Acquired'


def test_update_order_customer_endpoint_swaps_service_user(client):
  admin = create_user(UserRole.ADMIN)
  customer, service, service_user, _ = customer_with_service()
  new_customer = create_user(UserRole.CUSTOMER)
  from tests.unit.factories import create_service_user

  new_service_user = create_service_user(new_customer, service, price=25.0)
  order = create_order()
  product = create_product(order, service_user)

  response = client.post(
    '/order/customer',
    json={'user_id': new_customer.id, 'order_id': order.id},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  with Session() as session:
    from src.database.schema import Product

    refreshed = session.get(Product, product.id)
    assert refreshed.service_user_id == new_service_user.id


def test_update_order_customer_endpoint_rejects_missing_services(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  new_customer = create_user(UserRole.CUSTOMER)  # nessun servizio associato
  order = create_order()
  create_product(order, service_user)

  response = client.post(
    '/order/customer',
    json={'user_id': new_customer.id, 'order_id': order.id},
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ko'


def test_collection_points_available_for_order(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, collection_point = customer_with_service()
  order = create_order()
  create_product(order, service_user)

  response = client.get(f'/order/collection-points/{order.id}', headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert [cp['id'] for cp in body['collection_points']] == [collection_point.id]


def test_update_order_endpoint_deletes_product(client):
  admin = create_user(UserRole.ADMIN)
  customer, service, service_user, collection_point = customer_with_service()
  order = create_order()
  create_product(order, service_user, name='Lavatrice')

  response = client.put(
    f'/order/{order.id}',
    json={
      'id': order.id,
      'version': 0,
      'user_id': customer.id,
      'products': {
        'Asciugatrice': {
          'services': [{'id': service.id}],
          'collection_point': {'id': collection_point.id},
        }
      },
      'delay': False,
    },
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'

from datetime import date, datetime

from src.database.enum import OrderStatus
from src.schedulation import assign_orders_to_groups, execute_schedulation

from tests.unit.factories import (
  create_order,
  create_product,
  create_transport,
  customer_with_service,
)
from tests.unit.schedulation.conftest import make_order


def test_assign_orders_to_groups_end_to_end():
  groups = assign_orders_to_groups(
    orders=[make_order(1, '70121'), make_order(2, '71010')],
    transports=[
      {'id': 11, 'cap': '70122'},
      {'id': 22, 'cap': '71011'},
    ],
    min_size_group=1,
    max_size_group=2,
    max_distance_km=5,
  )

  assignment = {
    tuple(item['order_id'] for item in group['schedule_items'] if item['operation_type'] == 'Order'): [
      transport['id'] for transport in group['transports']
    ]
    for group in groups
  }
  assert assignment == {(1,): [11], (2,): [22]}


def test_execute_schedulation_returns_ko_without_orders(app, db):
  with app.test_request_context(json={'services_id': []}):
    result = execute_schedulation(datetime(2026, 7, 15), 1, 5, 10)

  assert result['status'] == 'ko'
  assert result['message'] == 'Ordini non trovati in questa data'


def test_execute_schedulation_builds_groups(app, db):
  _, _, service_user, collection_point = customer_with_service(cap='70121')
  order = create_order(status=OrderStatus.BOOKED, dpc=date(2026, 7, 15), cap='70121')
  create_product(order, service_user, collection_point_id=collection_point.id)
  transport = create_transport(cap='70121')

  with app.test_request_context():
    result = execute_schedulation(datetime(2026, 7, 15), 1, 5, 10)

  assert result['status'] == 'ok'
  assert [t['id'] for t in result['transports']] == [transport.id]
  assert len(result['groups']) == 1
  # La proposta assegna il veicolo: i corrieri li porta lui.
  assert result['groups'][0]['transports'][0]['id'] == transport.id

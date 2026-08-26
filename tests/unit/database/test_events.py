from database_api import Session
from database_api.operations import update

from src.database.enum import OrderStatus, UserRole
from src.database.schema import History

from tests.unit.factories import create_order, create_user


def _histories(order_id):
  with Session() as session:
    return session.query(History).filter(History.order_id == order_id).order_by(History.id).all()


def test_new_order_tracks_initial_status(db):
  order = create_order(status=OrderStatus.ACQUIRED)

  histories = _histories(order.id)
  assert [h.status for h in histories] == [{'type': 'status', 'value': 'Acquired'}]


def test_new_confirmed_order_tracks_confirmed_flag(db):
  order = create_order(status=OrderStatus.BOOKED, confirmed=True)

  statuses = [h.status for h in _histories(order.id)]
  assert {'type': 'status', 'value': 'Booked'} in statuses
  assert {'type': 'confirmed', 'value': True} in statuses


def test_status_change_appends_history(db):
  order = create_order(status=OrderStatus.ACQUIRED)

  update(order, {'status': OrderStatus.DELIVERED})

  statuses = [h.status for h in _histories(order.id)]
  assert statuses[-1] == {'type': 'status', 'value': 'Delivered'}


def test_flag_changes_append_history(db):
  order = create_order()

  order = update(order, {'anomaly': True})
  order = update(order, {'delay': True})
  update(order, {'confirmed': True})

  tracked = {(h.status['type'], h.status['value']) for h in _histories(order.id)}
  assert ('anomaly', True) in tracked
  assert ('delay', True) in tracked
  assert ('confirmed', True) in tracked


def test_unrelated_update_does_not_append_history(db):
  order = create_order()
  before = len(_histories(order.id))

  update(order, {'operator_note': 'solo una nota'})

  assert len(_histories(order.id)) == before


def test_version_increments_on_every_update(db):
  order = create_order()
  assert order.version == 0

  order = update(order, {'operator_note': 'nota 1'})
  assert order.version == 1

  order = update(order, {'operator_note': 'nota 2'})
  assert order.version == 2


def test_non_order_entities_are_ignored_by_history(db):
  create_user(UserRole.DELIVERY)

  with Session() as session:
    assert session.query(History).count() == 0

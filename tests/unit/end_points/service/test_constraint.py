from datetime import date, timedelta

from src.end_points.service.constraint import check_services_date

from tests.unit.factories import create_order, create_product, create_service, customer_with_service


def test_all_dates_allowed_without_max_services(app, db):
  service = create_service()

  with app.test_request_context(json={'services_id': [service.id]}):
    allowed = check_services_date()

  assert date.today().strftime('%Y-%m-%d') in allowed
  assert len(allowed) >= 60


def test_day_blocked_when_orders_reach_min_max_services(app, db):
  customer, service, service_user, _ = customer_with_service()
  from database_api.operations import update

  update(service, {'max_services': 1})
  target = date.today() + timedelta(days=2)
  order = create_order(dpc=target)
  create_product(order, service_user)

  with app.test_request_context(json={'services_id': [service.id]}):
    allowed = check_services_date()

  assert target.strftime('%Y-%m-%d') not in allowed
  assert (target + timedelta(days=1)).strftime('%Y-%m-%d') in allowed


def test_min_max_across_services_wins(app, db):
  customer, service, service_user, _ = customer_with_service()
  from database_api.operations import update

  update(service, {'max_services': 5})
  strict_service = create_service(max_services=1)
  target = date.today() + timedelta(days=3)
  order = create_order(dpc=target)
  create_product(order, service_user)

  with app.test_request_context(json={'services_id': [service.id, strict_service.id]}):
    allowed = check_services_date()

  # min(5, 1) = 1: il giorno con un ordine esistente è saturo
  assert target.strftime('%Y-%m-%d') not in allowed

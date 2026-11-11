from datetime import date, timedelta

import pytest
from api.users.security import verify_password
from database_api import Session, scope

from scripts.create_review_account import (
  DEFAULT_COMPANY_NAME,
  DEFAULT_NICKNAME,
  MARKER,
  ReviewAccountError,
  customer_nickname,
  day_range,
  parse_args,
  run,
)
from src.database.enum import OrderStatus, ScheduleType, UserRole
from src.database.schema import (
  Company,
  CustomerUserInfo,
  Order,
  Product,
  Schedule,
  ScheduleItem,
  ScheduleItemActivity,
  Transport,
  User,
)
from src.end_points.schedule.delivery import get_history_for_delivery, get_items_for_delivery

from tests.unit.factories import create_order, create_user


def options(*extra):
  return parse_args(['--days', '3', '--past-days', '1', *extra])


def review_company() -> Company:
  with Session() as session:
    return session.query(Company).filter(Company.name == DEFAULT_COMPANY_NAME).one()


def count(model, company_id):
  with scope(company_id=company_id), Session() as session:
    return session.query(model).filter(model.company_id == company_id).count()


def test_creates_the_review_company_with_courier_and_one_schedule_per_day():
  summary = run(options())

  company = review_company()
  assert company.automatic_planning is False
  assert summary['created_days'] == 4  # ieri, oggi e i 2 giorni dopo
  assert count(Schedule, company.id) == 4
  assert count(Transport, company.id) == 1
  assert count(Order, company.id) == 16

  with scope(company_id=company.id), Session() as session:
    courier = session.query(User).filter(User.nickname == DEFAULT_NICKNAME).one()
    assert courier.role == UserRole.DELIVERY
    for schedule in session.query(Schedule).all():
      items = session.query(ScheduleItem).filter(ScheduleItem.schedule_id == schedule.id).all()
      kinds = sorted(item.operation_type.value for item in items)
      assert kinds == ['Activity', 'CollectionPoint', 'CollectionPoint', 'Order', 'Order', 'Order', 'Order']
      assert sorted(item.index for item in items) == [1, 2, 3, 4, 5, 6, 7]
    assert session.query(ScheduleItemActivity).count() == 4


def test_the_generated_password_is_returned_once_and_stored_hashed():
  summary = run(options())

  assert summary['password']
  with scope(company_id=review_company().id), Session() as session:
    courier = session.query(User).filter(User.nickname == DEFAULT_NICKNAME).one()
  assert courier.password != summary['password']
  assert verify_password(summary['password'], courier.password)

  second = run(options())
  assert second['password'] is None
  with scope(company_id=review_company().id), Session() as session:
    assert verify_password(
      summary['password'], session.query(User).filter(User.nickname == DEFAULT_NICKNAME).one().password
    )


def test_a_password_from_the_options_or_the_environment_is_used(monkeypatch):
  run(options('--password', 'Chiave-Demo-1'))
  with scope(company_id=review_company().id), Session() as session:
    courier = session.query(User).filter(User.nickname == DEFAULT_NICKNAME).one()
  assert verify_password('Chiave-Demo-1', courier.password)

  monkeypatch.setenv('REVIEW_PASSWORD', 'Altra-Chiave-2')
  summary = run(options())

  assert summary['password'] is None
  with scope(company_id=review_company().id), Session() as session:
    courier = session.query(User).filter(User.nickname == DEFAULT_NICKNAME).one()
  assert verify_password('Altra-Chiave-2', courier.password)


def test_a_second_run_does_not_duplicate_anything():
  run(options())
  company = review_company()
  before = {model: count(model, company.id) for model in (User, Transport, Schedule, Order, Product)}

  summary = run(options())

  assert summary['created_days'] == 0
  assert {model: count(model, company.id) for model in (User, Transport, Schedule, Order, Product)} == before
  assert before[User] == 2  # il corriere e il punto vendita


def test_a_longer_window_only_adds_the_missing_days():
  run(parse_args(['--days', '2', '--past-days', '0']))
  company = review_company()
  assert count(Schedule, company.id) == 2

  summary = run(parse_args(['--days', '5', '--past-days', '0']))

  assert summary['created_days'] == 3
  assert count(Schedule, company.id) == 5


def test_dry_run_writes_nothing(capsys):
  summary = run(options('--dry-run'))

  assert summary['dry_run'] is True
  with Session() as session:
    assert session.query(Company).filter(Company.name == DEFAULT_COMPANY_NAME).count() == 0
  assert 'non viene scritto niente' in capsys.readouterr().out


def test_dry_run_on_an_existing_company_reports_the_missing_days(capsys):
  run(parse_args(['--days', '2', '--past-days', '0']))
  company = review_company()

  run(parse_args(['--days', '5', '--past-days', '0', '--dry-run']))

  assert 'Borderò da creare: 3' in capsys.readouterr().out
  assert count(Schedule, company.id) == 2


def test_orders_cannot_send_sms_or_real_emails_and_are_marked():
  run(options())
  company = review_company()

  with scope(company_id=company.id), Session() as session:
    orders = session.query(Order).all()
    emails = [info.email for info in session.query(CustomerUserInfo).all()]

  assert orders
  assert all(order.addressee_contact is None for order in orders)
  assert all(order.external_id.startswith(MARKER) for order in orders)
  assert emails and all(email.endswith('@example.invalid') for email in emails)


def test_past_days_are_completed_and_the_others_are_ready_to_work():
  run(options())
  company = review_company()
  today = date.today()

  with scope(company_id=company.id), Session() as session:
    yesterday_items = (
      session.query(ScheduleItem).join(Schedule).filter(Schedule.date == today - timedelta(days=1)).all()
    )
    today_items = session.query(ScheduleItem).join(Schedule).filter(Schedule.date == today).all()
    statuses = {
      order.dpc: order.status
      for order in session.query(Order).filter(Order.dpc.in_([today - timedelta(days=1), today]))
    }

  assert yesterday_items and all(item.completed for item in yesterday_items)
  assert today_items and not any(item.completed for item in today_items)
  assert statuses[today - timedelta(days=1)] == OrderStatus.DELIVERED
  assert statuses[today] == OrderStatus.SCHEDULED


def test_the_delivery_app_sees_todays_schedule_and_the_history():
  run(options())
  company = review_company()

  with scope(company_id=company.id):
    with Session() as session:
      courier = session.query(User).filter(User.nickname == DEFAULT_NICKNAME).one()
    today = get_items_for_delivery(courier)
    history = get_history_for_delivery(courier)

  assert today['status'] == 'ok'
  assert today['schedule_id'] is not None
  assert [item['operation_type'] for item in today['schedule_items']] == [
    ScheduleType.COLLECTIONPOINT.value,
    ScheduleType.COLLECTIONPOINT.value,
    ScheduleType.ORDER.value,
    ScheduleType.ORDER.value,
    ScheduleType.ACTIVITY.value,
    ScheduleType.ORDER.value,
    ScheduleType.ORDER.value,
  ]
  assert [item['completed'] for item in today['schedule_items']] == [False] * 7
  assert len(history['schedules']) == 1


def test_the_courier_can_log_in_and_unlock_the_deliveries_by_completing_the_pickups(client):
  summary = run(options())
  login = client.post('/user/login', json={'email': DEFAULT_NICKNAME, 'password': summary['password']}).get_json()
  assert login['status'] == 'ok'
  assert login['role'] == 'Delivery'
  headers = {'Authorization': login['access_token']}

  today = client.get('/schedule/delivery', headers=headers).get_json()
  pickups = [item for item in today['schedule_items'] if item['operation_type'] == 'CollectionPoint']
  assert len(pickups) == 2

  with scope(company_id=review_company().id), Session() as session:
    before = {order.status for order in session.query(Order).filter(Order.dpc == date.today())}
  assert before == {OrderStatus.SCHEDULED}

  for pickup in pickups:
    response = client.put(f'/schedule/item/{pickup["id"]}', json={'completed': True}, headers=headers)
    assert response.get_json()['status'] == 'ok'

  with scope(company_id=review_company().id), Session() as session:
    after = {order.status for order in session.query(Order).filter(Order.dpc == date.today())}
  assert after == {OrderStatus.BOOKING}


def test_reset_recreates_the_schedules_and_clears_what_the_reviewer_did():
  run(options())
  company = review_company()
  with scope(company_id=company.id), Session() as session:
    item = session.query(ScheduleItem).join(Schedule).filter(Schedule.date == date.today()).first()
    item.completed = True
    order = session.query(Order).filter(Order.dpc == date.today()).first()
    order.status = OrderStatus.NOT_DELIVERED
    old_order_ids = {row[0] for row in session.query(Order.id)}
    session.commit()

  summary = run(options('--reset'))

  assert summary['removed'] == {'schedules': 4, 'orders': 16}
  assert summary['created_days'] == 4
  with scope(company_id=company.id), Session() as session:
    assert (
      session.query(ScheduleItem)
      .join(Schedule)
      .filter(Schedule.date == date.today())
      .filter(ScheduleItem.completed.is_(True))
      .count()
      == 0
    )
    new_order_ids = {row[0] for row in session.query(Order.id)}
    assert session.query(Order).filter(Order.status == OrderStatus.NOT_DELIVERED).count() == 0
  assert not old_order_ids & new_order_ids
  assert count(Order, company.id) == 16


def test_reset_never_touches_other_companies(db):
  other_customer = create_user(UserRole.CUSTOMER)
  other_order = create_order()
  run(options())

  run(options('--reset'))

  with Session() as session:
    assert session.query(User).filter(User.id == other_customer.id).count() == 1
  with scope(company_id=db.id), Session() as session:
    assert session.query(Order).filter(Order.id == other_order.id).count() == 1


def test_refuses_to_work_in_a_company_with_data_it_did_not_create():
  run(options())
  company = review_company()
  with scope(company_id=company.id):
    create_order()  # ordine senza marcatura: non e' del demo

  with pytest.raises(ReviewAccountError, match='non la tocco'):
    run(options('--reset'))

  assert count(Order, company.id) == 17


def test_refuses_a_nickname_already_used_in_another_company(db):
  create_user(UserRole.DELIVERY, nickname=DEFAULT_NICKNAME)

  with pytest.raises(ReviewAccountError, match='altra company'):
    run(options())

  with Session() as session:
    assert session.query(Company).filter(Company.name == DEFAULT_COMPANY_NAME).count() == 0


def test_custom_names_are_used():
  run(options('--company-name', 'Revisione Test', '--nickname', 'corriere.prova'))

  with Session() as session:
    company = session.query(Company).filter(Company.name == 'Revisione Test').one()
  with scope(company_id=company.id), Session() as session:
    nicknames = {user.nickname for user in session.query(User).all()}
  assert nicknames == {'corriere.prova', customer_nickname('corriere.prova')}


def test_day_range_covers_the_past_and_the_future_window():
  today = date(2026, 11, 11)

  days = day_range(today, 3, 2)

  assert days[0] == date(2026, 11, 9)
  assert days[-1] == date(2026, 11, 13)
  assert len(days) == 5


def test_parse_args_rejects_invalid_windows():
  with pytest.raises(SystemExit):
    parse_args(['--days', '0'])
  with pytest.raises(SystemExit):
    parse_args(['--past-days', '-1'])

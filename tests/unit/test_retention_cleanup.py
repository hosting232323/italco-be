from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

import database_api
from api.storage import session as session_module
from database_api import Session
from database_api.operations import create

from scripts import retention_cleanup
from src.database.enum import OrderStatus, ScheduleItemUserType, UserRole
from src.database.schema import DeliveryUserInfo, Mail, Order, Photo, ScheduleItemUser
from src.end_points.exportation.utils import get_signature_slots

from tests.unit.factories import (
  create_delivery_info,
  create_order,
  create_schedule,
  create_schedule_item_user,
  create_user,
)


def _ago(**kwargs) -> datetime:
  return datetime.now(timezone.utc) - timedelta(**kwargs)


def _set_timestamp(table: str, row_id: int, moment: datetime, column: str = 'updated_at'):
  """Scrive il timestamp a mano: updated_at si aggiorna da solo a ogni modifica via ORM."""
  with database_api.engine.begin() as connection:
    connection.execute(text(f'UPDATE {table} SET {column} = :moment WHERE id = :id'), {'moment': moment, 'id': row_id})


def _position(user_id: int):
  with Session() as session:
    info = session.query(DeliveryUserInfo).filter(DeliveryUserInfo.user_id == user_id).one()
    return tuple(None if value is None else float(value) for value in (info.lat, info.lon))


def _event_ids(schedule_id: int) -> list[int]:
  with Session() as session:
    rows = session.query(ScheduleItemUser).filter(ScheduleItemUser.schedule_id == schedule_id).all()
    return sorted(row.id for row in rows)


def _photo(order, link: str, **timestamps) -> Photo:
  photo = create(Photo, {'order_id': order.id, 'link': link})
  for column, moment in timestamps.items():
    _set_timestamp('photo', photo.id, moment, column=column)
  return photo


def _photo_links() -> list[str]:
  with Session() as session:
    return sorted(photo.link for photo in session.query(Photo).all())


def _signature(order_id: int):
  with Session() as session:
    return session.query(Order.signature).filter(Order.id == order_id).scalar()


def _run(job, *args, dry_run=False):
  with database_api.engine.begin() as connection:
    return job(connection, *args, dry_run)


# --- Ultima posizione ---------------------------------------------------------


def test_clear_old_positions_resets_only_stale_coordinates(db):
  stale = create_user(UserRole.DELIVERY)
  fresh = create_user(UserRole.DELIVERY)
  stale_info = create_delivery_info(stale, lat=41.3, lon=16.2)
  create_delivery_info(fresh, lat=41.4, lon=16.3)
  _set_timestamp('delivery_user_info', stale_info.id, _ago(hours=30))

  cleared = _run(retention_cleanup.clear_old_positions, 24)

  assert cleared == 1
  assert _position(stale.id) == (None, None)
  assert _position(fresh.id) == (41.4, 16.3)


def test_clear_old_positions_ignores_cards_without_coordinates(db):
  user = create_user(UserRole.DELIVERY)
  info = create_delivery_info(user)
  _set_timestamp('delivery_user_info', info.id, _ago(days=10))

  assert _run(retention_cleanup.clear_old_positions, 24) == 0


def test_clear_old_positions_dry_run_does_not_write(db):
  user = create_user(UserRole.DELIVERY)
  info = create_delivery_info(user, lat=41.3, lon=16.2)
  _set_timestamp('delivery_user_info', info.id, _ago(hours=48))

  counted = _run(retention_cleanup.clear_old_positions, 24, dry_run=True)

  assert counted == 1
  assert _position(user.id) == (41.3, 16.2)


# --- Eventi di posizione ------------------------------------------------------


def test_old_position_events_are_deleted_but_the_open_holder_stays(db):
  delivery = create_user(UserRole.DELIVERY)
  other = create_user(UserRole.DELIVERY)
  schedule = create_schedule()
  opening = create_schedule_item_user(delivery, schedule, ScheduleItemUserType.OPENING)
  change = create_schedule_item_user(other, schedule, ScheduleItemUserType.CHANGE)
  for event in (opening, change):
    _set_timestamp('schedule_item_user', event.id, _ago(days=400), column='created_at')

  deleted = _run(retention_cleanup.delete_old_position_events, 365)

  assert deleted == 1
  assert _event_ids(schedule.id) == [change.id]


def test_old_position_events_of_a_closed_bordero_are_all_deleted(db):
  delivery = create_user(UserRole.DELIVERY)
  schedule = create_schedule()
  events = [
    create_schedule_item_user(delivery, schedule, ScheduleItemUserType.OPENING),
    create_schedule_item_user(delivery, schedule, ScheduleItemUserType.CLOSING),
  ]
  for event in events:
    _set_timestamp('schedule_item_user', event.id, _ago(days=400), column='created_at')

  assert _run(retention_cleanup.delete_old_position_events, 365) == 2
  assert _event_ids(schedule.id) == []


def test_recent_position_events_are_kept(db):
  delivery = create_user(UserRole.DELIVERY)
  schedule = create_schedule()
  event = create_schedule_item_user(delivery, schedule, ScheduleItemUserType.OPENING)
  create_schedule_item_user(delivery, schedule, ScheduleItemUserType.CLOSING)

  assert _run(retention_cleanup.delete_old_position_events, 365) == 0
  assert event.id in _event_ids(schedule.id)


def test_position_events_dry_run_does_not_delete(db):
  delivery = create_user(UserRole.DELIVERY)
  schedule = create_schedule()
  event = create_schedule_item_user(delivery, schedule, ScheduleItemUserType.CLOSING)
  _set_timestamp('schedule_item_user', event.id, _ago(days=400), column='created_at')

  assert _run(retention_cleanup.delete_old_position_events, 365, dry_run=True) == 1
  assert _event_ids(schedule.id) == [event.id]


# --- Richieste demo -----------------------------------------------------------


def _mail(subject: str) -> Mail:
  return create(Mail, {'recipient': 'a@hubstra.it', 'subject': subject, 'content': 'Richiesta demo'})


def _mail_subjects() -> list[str]:
  with Session() as session:
    return sorted(row.subject for row in session.query(Mail).all())


def test_old_demo_requests_are_deleted(db):
  old = _mail('vecchia')
  _mail('recente')
  _set_timestamp('mail', old.id, _ago(days=400), column='created_at')

  assert _run(retention_cleanup.delete_old_demo_requests, 365) == 1
  assert _mail_subjects() == ['recente']


def test_demo_requests_dry_run_does_not_delete(db):
  old = _mail('vecchia')
  _set_timestamp('mail', old.id, _ago(days=400), column='created_at')

  assert _run(retention_cleanup.delete_old_demo_requests, 365, dry_run=True) == 1
  assert _mail_subjects() == ['vecchia']


# --- Log di audit -------------------------------------------------------------


def _write_log(log_dir, day: date, index: bool = True):
  month_dir = log_dir / day.strftime('%Y-%m')
  month_dir.mkdir(parents=True, exist_ok=True)
  (month_dir / f'{day.isoformat()}.jsonl').write_text('{}\n')
  if index:
    (month_dir / f'{day.isoformat()}.idx').write_text('{}\n')


def test_delete_old_logs_removes_files_indexes_and_empty_months(tmp_path):
  old = date.today() - timedelta(days=200)
  recent = date.today() - timedelta(days=5)
  _write_log(tmp_path, old)
  _write_log(tmp_path, recent)

  deleted = retention_cleanup.delete_old_logs(tmp_path, 90, dry_run=False)

  assert deleted == 1
  assert not (tmp_path / old.strftime('%Y-%m') / f'{old.isoformat()}.jsonl').exists()
  assert not (tmp_path / old.strftime('%Y-%m') / f'{old.isoformat()}.idx').exists()
  assert (tmp_path / recent.strftime('%Y-%m') / f'{recent.isoformat()}.jsonl').exists()
  if old.strftime('%Y-%m') != recent.strftime('%Y-%m'):
    assert not (tmp_path / old.strftime('%Y-%m')).exists()


def test_delete_old_logs_skips_files_with_unexpected_names(tmp_path):
  month_dir = tmp_path / '2020-01'
  month_dir.mkdir()
  (month_dir / 'appunti.jsonl').write_text('{}\n')

  assert retention_cleanup.delete_old_logs(tmp_path, 90, dry_run=False) == 0
  assert (month_dir / 'appunti.jsonl').exists()


def test_delete_old_logs_dry_run_does_not_delete(tmp_path):
  old = date.today() - timedelta(days=200)
  _write_log(tmp_path, old)

  assert retention_cleanup.delete_old_logs(tmp_path, 90, dry_run=True) == 1
  assert (tmp_path / old.strftime('%Y-%m') / f'{old.isoformat()}.jsonl').exists()


def test_delete_old_logs_without_folder_is_a_noop(tmp_path):
  assert retention_cleanup.delete_old_logs(tmp_path / 'assente', 90, dry_run=False) == 0


# --- Impostazioni e comando ---------------------------------------------------


def test_retention_setting_falls_back_to_default(monkeypatch):
  name = 'RETENTION_LOG_DAYS'
  monkeypatch.delenv(name, raising=False)
  assert retention_cleanup.retention_setting(name) == 90

  monkeypatch.setenv(name, 'non-un-numero')
  assert retention_cleanup.retention_setting(name) == 90

  monkeypatch.setenv(name, ' 30 ')
  assert retention_cleanup.retention_setting(name) == 30

  monkeypatch.setenv(name, '0')
  assert retention_cleanup.retention_setting(name) == 0


@pytest.fixture
def static_logs(tmp_path, monkeypatch):
  monkeypatch.setattr(retention_cleanup, 'STATIC_FOLDER', str(tmp_path))
  log_dir = tmp_path / ('test' if retention_cleanup.IS_DEV else 'prod') / 'logs'
  _write_log(log_dir, date.today() - timedelta(days=200))
  return log_dir


def _populate_everything():
  delivery = create_user(UserRole.DELIVERY)
  info = create_delivery_info(delivery, lat=41.3, lon=16.2)
  _set_timestamp('delivery_user_info', info.id, _ago(hours=48))
  schedule = create_schedule()
  event = create_schedule_item_user(delivery, schedule, ScheduleItemUserType.CLOSING)
  _set_timestamp('schedule_item_user', event.id, _ago(days=400), column='created_at')
  mail = _mail('vecchia')
  _set_timestamp('mail', mail.id, _ago(days=400), column='created_at')
  order = create_order(
    status=OrderStatus.DELIVERED, completion_date=date.today() - timedelta(days=800), signature=b'\x89PNG-fake'
  )
  _photo(order, 'http://x/order/photos/900.jpg')
  return delivery, schedule, order


def test_main_dry_run_counts_without_deleting(db, static_logs, capsys):
  delivery, schedule, order = _populate_everything()

  results = retention_cleanup.main(['--dry-run'])

  assert results == {'positions': 1, 'position_events': 1, 'demo_requests': 1, 'signatures': 1, 'photos': 1, 'logs': 1}
  assert 'da cancellare' in capsys.readouterr().out
  assert _signature(order.id) is not None
  assert _photo_links() == ['http://x/order/photos/900.jpg']
  assert _position(delivery.id) == (41.3, 16.2)
  assert len(_event_ids(schedule.id)) == 1
  assert _mail_subjects() == ['vecchia']
  assert list(static_logs.glob('*/*.jsonl'))


def test_main_deletes_everything_expired(db, static_logs, capsys):
  delivery, schedule, order = _populate_everything()

  results = retention_cleanup.main([])

  assert results == {'positions': 1, 'position_events': 1, 'demo_requests': 1, 'signatures': 1, 'photos': 1, 'logs': 1}
  assert 'cancellati' in capsys.readouterr().out
  assert _signature(order.id) is None
  assert _photo_links() == []
  assert _position(delivery.id) == (None, None)
  assert _event_ids(schedule.id) == []
  assert _mail_subjects() == []
  assert not list(static_logs.glob('*/*.jsonl'))


def test_main_skips_disabled_jobs(db, static_logs, monkeypatch, capsys):
  delivery, schedule, order = _populate_everything()
  for name in retention_cleanup.DEFAULTS:
    monkeypatch.setenv(name, '0')

  results = retention_cleanup.main([])

  assert results == {}
  assert capsys.readouterr().out.count('disattivato') == 6
  assert _signature(order.id) is not None
  assert _photo_links() == ['http://x/order/photos/900.jpg']
  assert _position(delivery.id) == (41.3, 16.2)
  assert len(_event_ids(schedule.id)) == 1
  assert _mail_subjects() == ['vecchia']
  assert list(static_logs.glob('*/*.jsonl'))


# --- Foto e firma di consegna ---------------------------------------------------


def _long_ago(days: int = 800) -> date:
  return date.today() - timedelta(days=days)


@pytest.fixture
def deleted_files(monkeypatch):
  names = []
  monkeypatch.setattr(
    session_module, 'delete_file', lambda filename, folder, **kwargs: names.append((filename, kwargs['subfolder']))
  )
  return names


def test_months_ago_clamps_to_the_last_day_and_crosses_years():
  assert retention_cleanup.months_ago(date(2026, 11, 12), 24) == date(2024, 11, 12)
  assert retention_cleanup.months_ago(date(2026, 3, 31), 1) == date(2026, 2, 28)
  assert retention_cleanup.months_ago(date(2026, 1, 15), 2) == date(2025, 11, 15)


def test_old_photos_of_closed_orders_are_deleted_with_their_files(db, deleted_files):
  old_delivered = create_order(status=OrderStatus.DELIVERED, completion_date=_long_ago())
  old_not_delivered = create_order(status=OrderStatus.NOT_DELIVERED, completion_date=_long_ago())
  recent = create_order(status=OrderStatus.DELIVERED, completion_date=date.today() - timedelta(days=30))
  _photo(old_delivered, 'http://x/order/photos/1.jpg')
  _photo(old_not_delivered, 'http://x/order/photos/2.jpg')
  _photo(recent, 'http://x/order/photos/3.jpg')

  deleted = retention_cleanup.delete_old_delivery_photos(24, False)

  assert deleted == 2
  assert _photo_links() == ['http://x/order/photos/3.jpg']
  assert sorted(deleted_files) == [('1.jpg', 'photos'), ('2.jpg', 'photos')]


def test_photos_of_open_orders_are_never_deleted(db, deleted_files):
  for status in (OrderStatus.BOOKING, OrderStatus.TO_RESCHEDULE, OrderStatus.SCHEDULED):
    order = create_order(status=status, completion_date=_long_ago())
    _photo(order, f'http://x/order/photos/{status.name}.jpg')

  assert retention_cleanup.delete_old_delivery_photos(24, False) == 0
  assert len(_photo_links()) == 3
  assert deleted_files == []


def test_photo_without_completion_date_uses_its_upload_date(db, deleted_files):
  order = create_order(status=OrderStatus.DELIVERED)
  _photo(order, 'http://x/order/photos/old.jpg', created_at=_ago(days=800))
  _photo(order, 'http://x/order/photos/new.jpg')

  assert retention_cleanup.delete_old_delivery_photos(24, False) == 1
  assert _photo_links() == ['http://x/order/photos/new.jpg']
  assert deleted_files == [('old.jpg', 'photos')]


def test_photo_dry_run_counts_without_deleting(db, deleted_files):
  order = create_order(status=OrderStatus.DELIVERED, completion_date=_long_ago())
  _photo(order, 'http://x/order/photos/1.jpg')

  assert retention_cleanup.delete_old_delivery_photos(24, True) == 1
  assert _photo_links() == ['http://x/order/photos/1.jpg']
  assert deleted_files == []


def test_photo_rows_are_deleted_even_when_the_file_is_already_missing(db, monkeypatch):
  def missing(filename, folder, **kwargs):
    raise FileNotFoundError(filename)

  monkeypatch.setattr(session_module, 'delete_file', missing)
  order = create_order(status=OrderStatus.DELIVERED, completion_date=_long_ago())
  _photo(order, 'http://x/order/photos/1.jpg')

  assert retention_cleanup.delete_old_delivery_photos(24, False) == 1
  assert _photo_links() == []


def test_photos_are_deleted_in_batches(db, deleted_files, monkeypatch):
  monkeypatch.setattr(retention_cleanup, 'PHOTO_BATCH_SIZE', 2)
  order = create_order(status=OrderStatus.DELIVERED, completion_date=_long_ago())
  for index in range(5):
    _photo(order, f'http://x/order/photos/{index}.jpg')

  assert retention_cleanup.delete_old_delivery_photos(24, False) == 5
  assert _photo_links() == []
  assert len(deleted_files) == 5


def test_old_signatures_of_closed_orders_are_cleared_but_the_order_stays(db):
  old = create_order(status=OrderStatus.DELIVERED, completion_date=_long_ago(), signature=b'\x89PNG-fake')
  old_not_delivered = create_order(
    status=OrderStatus.NOT_DELIVERED, completion_date=_long_ago(), signature=b'\x89PNG-fake'
  )
  recent = create_order(status=OrderStatus.DELIVERED, completion_date=_long_ago(30), signature=b'\x89PNG-fake')
  open_order = create_order(status=OrderStatus.BOOKING, completion_date=_long_ago(), signature=b'\x89PNG-fake')

  assert _run(retention_cleanup.clear_old_signatures, 24) == 2

  assert _signature(old.id) is None
  assert _signature(old_not_delivered.id) is None
  assert _signature(recent.id) is not None
  assert _signature(open_order.id) is not None
  with Session() as session:
    assert session.query(Order).filter(Order.id == old.id).count() == 1


def test_signature_without_completion_date_uses_the_last_update(db):
  stale = create_order(status=OrderStatus.DELIVERED, signature=b'\x89PNG-fake')
  fresh = create_order(status=OrderStatus.DELIVERED, signature=b'\x89PNG-fake')
  _set_timestamp('"order"', stale.id, _ago(days=800))

  assert _run(retention_cleanup.clear_old_signatures, 24) == 1
  assert _signature(stale.id) is None
  assert _signature(fresh.id) is not None


def test_signature_dry_run_does_not_write(db):
  order = create_order(status=OrderStatus.DELIVERED, completion_date=_long_ago(), signature=b'\x89PNG-fake')

  assert _run(retention_cleanup.clear_old_signatures, 24, dry_run=True) == 1
  assert _signature(order.id) is not None


def test_exports_cope_with_a_cleared_signature(db):
  order = create_order(status=OrderStatus.DELIVERED, completion_date=_long_ago(), signature=b'\x89PNG-fake')
  _run(retention_cleanup.clear_old_signatures, 24)

  with Session() as session:
    cleared = session.get(Order, order.id)
    assert get_signature_slots(cleared) == (None, None)

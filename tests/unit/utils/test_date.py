from datetime import date, datetime

import pytest

from src.utils.date import ROME_TZ, handle_date


def test_handle_date_parses_iso_string():
  assert handle_date('2026-07-15') == datetime(2026, 7, 15)


def test_handle_date_returns_date_objects_untouched():
  today = date(2026, 1, 31)
  assert handle_date(today) is today


def test_handle_date_returns_datetime_objects_untouched():
  now = datetime(2026, 1, 31, 12, 30)
  assert handle_date(now) is now


def test_handle_date_rejects_invalid_format():
  with pytest.raises(ValueError):
    handle_date('15/07/2026')


def test_rome_timezone_is_configured():
  assert ROME_TZ.zone == 'Europe/Rome'

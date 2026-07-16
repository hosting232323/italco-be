import pytest

from src.utils.caps import (
  CAPS_DATA,
  get_cap_by_name,
  get_cap_data_by_province,
  get_lat_lon_by_cap,
  get_province_by_cap,
)


def test_caps_data_is_loaded():
  assert isinstance(CAPS_DATA, dict)
  assert 'Bari' in CAPS_DATA


def test_get_province_by_cap_finds_province():
  assert get_province_by_cap('70020') == 'Bari'


def test_get_province_by_cap_raises_for_unknown_cap():
  with pytest.raises(ValueError, match='CAP 00000 not found'):
    get_province_by_cap('00000')


def test_get_cap_by_name_with_single_entry():
  # '70056' è un CAP con una sola città associata
  assert get_cap_by_name('Molfetta') == '70056'


def test_get_cap_by_name_with_multi_city_cap():
  # '70020' raggruppa più città in una lista
  assert get_cap_by_name('Binetto') == '70020'


def test_get_cap_by_name_is_case_insensitive():
  assert get_cap_by_name('mOLFETTA') == '70056'


def test_get_cap_by_name_raises_for_unknown_city():
  with pytest.raises(ValueError, match='not found in any CAP'):
    get_cap_by_name('Atlantide')


def test_get_lat_lon_by_cap_single_entry():
  lat, lon = get_lat_lon_by_cap('70056')
  assert lat == pytest.approx(41.1766334)
  assert lon == pytest.approx(16.5701927)


def test_get_lat_lon_by_cap_uses_first_entry_for_lists():
  lat, lon = get_lat_lon_by_cap('70020')
  assert (lat, lon) == (CAPS_DATA['Bari']['70020'][0]['lat'], CAPS_DATA['Bari']['70020'][0]['lon'])


def test_get_lat_lon_by_cap_raises_for_unknown_cap():
  with pytest.raises(ValueError, match='CAP 99999 not found'):
    get_lat_lon_by_cap('99999')


def test_get_cap_data_by_province_returns_caps():
  caps = get_cap_data_by_province('Bari')
  assert '70020' in caps


def test_get_cap_data_by_province_returns_empty_for_unknown():
  assert get_cap_data_by_province('Mordor') == []

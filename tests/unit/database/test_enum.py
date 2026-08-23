from src.database.enum import EuronicsStatus, OrderStatus, OrderType, RaeStatus, ScheduleType, UserRole


def test_user_roles():
  assert {role.value for role in UserRole} == {'Super Admin', 'Admin', 'Customer', 'Operator', 'Delivery'}


def test_order_statuses():
  assert {status.value for status in OrderStatus} == {
    'Acquired',
    'Booked',
    'Scheduled',
    'Booking',
    'Delivered',
    'Not Delivered',
    'To Reschedule',
    'Rescheduled',
  }


def test_rae_statuses():
  assert {status.value for status in RaeStatus} == {'Generated', 'Emitted', 'LDR', 'Disposed Off', 'Annulled'}


def test_euronics_statuses():
  assert len(EuronicsStatus) == 12
  assert EuronicsStatus('Cancelled to be Refunded') is EuronicsStatus.CANCELLED_TO_BE_REFUNDED


def test_order_types():
  assert {order_type.value for order_type in OrderType} == {'Delivery', 'Withdraw', 'Replacement', 'Check'}


def test_schedule_types():
  assert {schedule_type.value for schedule_type in ScheduleType} == {'Order', 'CollectionPoint'}


def test_enum_lookup_by_value_raises_for_unknown():
  import pytest

  with pytest.raises(ValueError):
    OrderStatus('Unknown')

from datetime import date, timedelta
from uuid import uuid4

from database_api.operations import create

from src.database.enum import OrderStatus, OrderType, UserRole
from src.database.schema import Order, Service, ServiceUser, User
from tests.utils import create_user_for_login


def uniq_value(prefix: str) -> str:
  return f'{prefix}.{uuid4().hex[:8]}@example.com'


def create_test_user(prefix: str, role: UserRole, password: str = 'pw') -> User:
  return create_user_for_login(uniq_value(prefix), password, role)


def create_test_service(name: str, order_type: OrderType = OrderType.DELIVERY, **overrides) -> Service:
  payload = {
    'name': name,
    'type': order_type,
    'duration': 30,
    'description': f'Description for {name}',
    'max_services': 3,
    'professional': False,
  }
  payload.update(overrides)
  return create(Service, payload)


def create_test_service_user(
  user_id: int,
  service_id: int,
  price: float = 45.0,
  code: str | None = None,
) -> ServiceUser:
  return create(
    ServiceUser,
    {
      'code': code or f'SU-{uuid4().hex[:8].upper()}',
      'price': price,
      'user_id': user_id,
      'service_id': service_id,
    },
  )


def create_acquired_order(**overrides) -> Order:
  payload = {
    'status': OrderStatus.ACQUIRED,
    'type': OrderType.DELIVERY,
    'addressee': 'Mario Rossi',
    'address': 'Via Roma 1',
    'cap': '70020',
    'dpc': date.today() + timedelta(days=2),
    'drc': date.today() + timedelta(days=2),
  }
  payload.update(overrides)
  return create(Order, payload)

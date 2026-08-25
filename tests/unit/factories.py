"""Factory minime per costruire i grafi di entità usati nei test unit.

Ogni factory crea solo ciò che serve, con default espliciti e override
puntuali, così i test dichiarano esattamente lo scenario che verificano.
"""

from datetime import date, time
from uuid import uuid4

from database_api import scope
from database_api.operations import create

from src.database.enum import OrderStatus, OrderType, RaeStatus, ScheduleType, UserRole
from src.database.schema import (
  Carrier,
  CollectionCenter,
  CollectionPoint,
  Company,
  CustomerUserInfo,
  DeliveryGroup,
  DeliveryUserInfo,
  Disposal,
  DtrDocument,
  Order,
  Product,
  RaeProduct,
  RaeProductGroup,
  Schedule,
  ScheduleItem,
  ScheduleItemOrder,
  Service,
  ServiceUser,
  Transport,
  User,
)
from src.end_points.users.session import create_jwt_token


def unique(prefix: str) -> str:
  return f'{prefix}-{uuid4().hex[:8]}'


def create_company(name: str = None, rae: bool = False) -> Company:
  return create(Company, {'name': name or unique('company'), 'rae': rae})


def create_user(role: UserRole = UserRole.ADMIN, nickname: str = None, password: str = 'pw', **extra) -> User:
  return create(
    User,
    {'nickname': nickname or unique(role.value.lower()), 'password': password, 'role': role, **extra},
  )


def create_super_admin(**extra) -> User:
  # Creato fuori scope, come fa lo script in produzione: company_id resta NULL.
  with scope(company_id=None):
    return create_user(UserRole.SUPER_ADMIN, **extra)


def auth_header(user: User, company_id: int = None) -> dict:
  # company_id esplicito serve solo al super admin, che non ne ha una propria.
  return {'Authorization': create_jwt_token(user, company_id)}


def admin_header() -> dict:
  return auth_header(create_user(UserRole.ADMIN))


def create_service(order_type: OrderType = OrderType.DELIVERY, **extra) -> Service:
  return create(Service, {'name': unique('service'), 'type': order_type, **extra})


def create_service_user(customer: User, service: Service, price: float = 10.0, **extra) -> ServiceUser:
  return create(ServiceUser, {'user_id': customer.id, 'service_id': service.id, 'price': price, **extra})


def create_collection_point(customer: User, cap: str = '70020', **extra) -> CollectionPoint:
  return create(
    CollectionPoint,
    {
      'name': unique('cp'),
      'address': 'Via Magazzino 1, Bari',
      'cap': cap,
      'user_id': customer.id,
      **extra,
    },
  )


def create_order(
  status: OrderStatus = OrderStatus.ACQUIRED, order_type: OrderType = OrderType.DELIVERY, **extra
) -> Order:
  return create(
    Order,
    {
      'status': status,
      'type': order_type,
      'addressee': extra.pop('addressee', unique('addressee')),
      'address': extra.pop('address', 'Via Consegna 1, Bari'),
      'cap': extra.pop('cap', '70020'),
      'dpc': extra.pop('dpc', date.today()),
      'drc': extra.pop('drc', date.today()),
      **extra,
    },
  )


def create_product(order: Order, service_user: ServiceUser, name: str = None, **extra) -> Product:
  return create(
    Product,
    {
      'name': name or unique('product'),
      'order_id': order.id,
      'service_user_id': service_user.id,
      **extra,
    },
  )


def create_transport(**extra) -> Transport:
  return create(Transport, {'name': unique('transport'), 'plate': unique('plate')[:10], **extra})


def create_schedule(transport: Transport = None, schedule_date: date = None, **extra) -> Schedule:
  transport = transport or create_transport()
  return create(Schedule, {'date': schedule_date or date.today(), 'transport_id': transport.id, **extra})


def create_schedule_item(
  schedule: Schedule,
  operation_type: ScheduleType = ScheduleType.ORDER,
  index: int = 0,
  **extra,
) -> ScheduleItem:
  return create(
    ScheduleItem,
    {
      'index': index,
      'schedule_id': schedule.id,
      'operation_type': operation_type,
      'start_time_slot': extra.pop('start_time_slot', time(8, 0)),
      'end_time_slot': extra.pop('end_time_slot', time(10, 0)),
      **extra,
    },
  )


def link_order_to_schedule(order: Order, schedule: Schedule, **item_extra) -> ScheduleItem:
  item = create_schedule_item(schedule, ScheduleType.ORDER, **item_extra)
  create(ScheduleItemOrder, {'order_id': order.id, 'schedule_item_id': item.id})
  return item


def create_delivery_group(delivery_user: User, schedule: Schedule) -> DeliveryGroup:
  return create(DeliveryGroup, {'user_id': delivery_user.id, 'schedule_id': schedule.id})


def create_customer_info(customer: User, **extra) -> CustomerUserInfo:
  return create(CustomerUserInfo, {'user_id': customer.id, **extra})


def create_delivery_info(delivery_user: User, **extra) -> DeliveryUserInfo:
  return create(DeliveryUserInfo, {'user_id': delivery_user.id, **extra})


def create_rae_product_group(**extra) -> RaeProductGroup:
  return create(
    RaeProductGroup,
    {'name': unique('rae-group'), 'cer_code': 200136, 'group_code': 'R4', **extra},
  )


def create_rae_product(order: Order, user: User, group: RaeProductGroup = None, **extra) -> RaeProduct:
  group = group or create_rae_product_group()
  return create(
    RaeProduct,
    {
      'order_id': order.id,
      'user_id': user.id,
      'rae_product_group_id': group.id,
      'status': extra.pop('status', RaeStatus.GENERATED),
      **extra,
    },
  )


def create_carrier(**extra) -> Carrier:
  return create(Carrier, {'company_name': unique('carrier'), **extra})


def create_collection_center(**extra) -> CollectionCenter:
  return create(CollectionCenter, {'company_name': unique('center'), **extra})


def create_disposal(carrier: Carrier = None, collection_center: CollectionCenter = None, **extra) -> Disposal:
  carrier = carrier or create_carrier()
  collection_center = collection_center or create_collection_center()
  return create(
    Disposal,
    {
      'carrier_id': carrier.id,
      'collection_center_id': collection_center.id,
      'date': extra.pop('date', date.today()),
      **extra,
    },
  )


def create_dtr_document(rae_product: RaeProduct, **extra) -> DtrDocument:
  return create(DtrDocument, {'link': unique('dtr-link'), 'rae_product_id': rae_product.id, **extra})


def customer_with_service(
  order_type: OrderType = OrderType.DELIVERY,
  price: float = 10.0,
  cap: str = '70020',
  professional: bool = False,
):
  """Cliente completo di servizio, associazione e punto di ritiro."""
  customer = create_user(UserRole.CUSTOMER)
  service = create_service(order_type, professional=professional)
  service_user = create_service_user(customer, service, price=price)
  collection_point = create_collection_point(customer, cap=cap)
  return customer, service, service_user, collection_point

import base64
from datetime import date, time, timedelta

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from database_api import Session
from database_api.operations import create

from .enum import EuronicsStatus, OrderStatus, OrderType, ScheduleType, UserRole
from .schema import (
  CollectionPoint,
  Constraint,
  CustomerGroup,
  CustomerRule,
  CustomerUserInfo,
  DeliveryGroup,
  DeliveryUserInfo,
  GeographicCode,
  GeographicZone,
  Log,
  Motivation,
  Order,
  Photo,
  Product,
  RaeProductGroup,
  Schedule,
  ScheduleItem,
  ScheduleItemCollectionPoint,
  ScheduleItemOrder,
  Service,
  ServiceUser,
  Transport,
  User,
)

SEED_PASSWORD_SECRET_KEY = 'local-dev-key-1234567890'
SEED_PASSWORD_IV = '1234567890123456'


def _encrypt_seed_password(password: str) -> str:
  key_bytes = SEED_PASSWORD_SECRET_KEY.encode('utf-8')
  iv_bytes = SEED_PASSWORD_IV.encode('utf-8')

  padder = padding.PKCS7(128).padder()
  padded = padder.update(password.encode('utf-8')) + padder.finalize()

  cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes))
  encryptor = cipher.encryptor()
  ciphertext = encryptor.update(padded) + encryptor.finalize()
  return base64.b64encode(iv_bytes + ciphertext).decode('utf-8')


DEFAULT_PASSWORD = _encrypt_seed_password('1234admin')


def seed_data():
  if not can_create():
    return

  today = date.today()

  admin_user = create(
    User,
    {
      'nickname': 'admin',
      'password': _encrypt_seed_password('1234admin'),
      'role': UserRole.ADMIN,
    },
  )
  operator_user = create(
    User,
    {
      'nickname': 'operator',
      'password': _encrypt_seed_password('1234operator'),
      'role': UserRole.OPERATOR,
    },
  )
  base_delivery_user = create(
    User,
    {
      'nickname': 'delivery',
      'password': _encrypt_seed_password('1234delivery'),
      'role': UserRole.DELIVERY,
    },
  )
  base_customer_user = create(
    User,
    {
      'nickname': 'customer',
      'password': DEFAULT_PASSWORD,
      'role': UserRole.CUSTOMER,
    },
  )

  customer_groups = []
  for index in range(10):
    customer_groups.append(create(CustomerGroup, {'name': f'Customer Group {index + 1}'}))

  delivery_users = [base_delivery_user]
  customer_users = [base_customer_user]
  for index in range(1, 10):
    delivery_users.append(
      create(
        User,
        {
          'nickname': f'delivery_{index}',
          'password': DEFAULT_PASSWORD,
          'role': UserRole.DELIVERY,
        },
      )
    )
    customer_users.append(
      create(
        User,
        {
          'nickname': f'customer_{index}',
          'password': DEFAULT_PASSWORD,
          'role': UserRole.CUSTOMER,
          'customer_group_id': customer_groups[index].id,
        },
      )
    )

  create(
    User,
    {
      'nickname': 'customer_group_owner',
      'password': DEFAULT_PASSWORD,
      'role': UserRole.CUSTOMER,
      'customer_group_id': customer_groups[0].id,
    },
  )

  for index, delivery_user in enumerate(delivery_users):
    create(
      DeliveryUserInfo,
      {
        'cap': '70020',
        'lat': 41.3 + (index * 0.01),
        'lon': 16.2 + (index * 0.01),
        'user_id': delivery_user.id,
      },
    )

  for index, customer_user in enumerate(customer_users):
    create(
      CustomerUserInfo,
      {
        'city': f'City {index + 1}',
        'import_code': f'CUST-{index + 1:03d}',
        'email': f'customer{index + 1}@example.com',
        'address': f'Via Cliente {index + 1}, Bari',
        'tax_code': f'TAXCODE{index + 1:04d}',
        'company_name': f'Cliente SPA {index + 1}',
        'user_id': customer_user.id,
      },
    )
    create(
      CustomerRule,
      {
        'day_of_week': index % 7,
        'max_orders': 2 + (index % 3),
        'user_id': customer_user.id,
      },
    )

  transports = []
  for index in range(10):
    transports.append(
      create(
        Transport,
        {
          'name': f'Furgone {index + 1}',
          'plate': f'AA{120 + index}BB',
          'cap': '70020',
        },
      )
    )

  collection_points = []
  for index in range(10):
    collection_points.append(
      create(
        CollectionPoint,
        {
          'name': f'Collection Point {index + 1}',
          'address': f'Via Magazzino {index + 1}, Barletta',
          'cap': '70020',
          'opening_time': time(hour=8 + (index % 2), minute=0),
          'closing_time': time(hour=17 + (index % 3), minute=0),
          'user_id': customer_users[index].id,
        },
      )
    )

  service_types = [OrderType.DELIVERY, OrderType.WITHDRAW, OrderType.REPLACEMENT, OrderType.CHECK]

  # 3 professional services — used only by the explicit PRO-SU service users for orders 0-2
  professional_srv_ids = []
  for i in range(3):
    srv = create(
      Service,
      {
        'name': f'RealProfessional-{i + 1}',
        'type': service_types[i % len(service_types)],
        'duration': 40 + (i * 10),
        'description': f'Professional service {i + 1}',
        'max_services': 5,
        'professional': True,
      },
    )
    professional_srv_ids.append(srv.id)

  # 10 non-professional services for the general service_users pool
  services = []
  for index in range(10):
    services.append(
      create(
        Service,
        {
          'name': f'Service {index + 1}',
          'type': service_types[index % len(service_types)],
          'duration': 30 + (index * 5),
          'description': f'Descrizione servizio {index + 1}',
          'max_services': 3 + (index % 4),
          'professional': False,
        },
      )
    )

  service_users = []
  for index in range(10):
    service_users.append(
      create(
        ServiceUser,
        {
          'code': f'SVC-{index + 1:03d}',
          'price': 39.0 + (index * 7.5),
          'user_id': delivery_users[index].id,
          'service_id': services[index].id,
        },
      )
    )

  # fill out the rest of the 10 services as before

  # E2E: give the base customer user access to the first DELIVERY service so that
  # the admin can create an order on their behalf in end-to-end tests.
  create(
    ServiceUser,
    {
      'code': 'E2E-CUST-001',
      'price': 50.0,
      'user_id': base_customer_user.id,
      'service_id': services[0].id,
    },
  )

  schedules = []
  for index in range(10):
    schedules.append(
      create(
        Schedule,
        {
          'date': today + timedelta(days=index),
          'transport_id': transports[index].id,
        },
      )
    )

  schedule_items = []
  for index in range(10):
    schedule_items.append(
      create(
        ScheduleItem,
        {
          'index': index + 1,
          'start_time_slot': time(hour=8 + (index % 3), minute=0),
          'end_time_slot': time(hour=10 + (index % 3), minute=30),
          'operation_type': ScheduleType.ORDER,
          'schedule_id': schedules[index].id,
        },
      )
    )
    create(
      ScheduleItemCollectionPoint,
      {
        'schedule_item_id': schedule_items[index].id,
        'collection_point_id': collection_points[index].id,
      },
    )
    create(
      DeliveryGroup,
      {
        'user_id': delivery_users[index].id,
        'schedule_id': schedules[index].id,
      },
    )

  rae_products = []
  for index in range(10):
    rae_products.append(
      create(
        RaeProductGroup,
        {
          'name': f'RAE Product {index + 1}',
          'cer_code': 200000 + index,
          'group_code': f'G{index + 1:02d}',
        },
      )
    )

  geographic_zones = []
  for index in range(10):
    geographic_zones.append(create(GeographicZone, {'name': f'Zona {index + 1}'}))
    create(
      GeographicCode,
      {
        'zone_id': geographic_zones[index].id,
        'code': '70020',
        'type': index % 2 == 0,
      },
    )
    create(
      Constraint,
      {
        'zone_id': geographic_zones[index].id,
        'day_of_week': index % 7,
        'max_orders': 5 + (index % 4),
      },
    )

  orders = []
  for index in range(20):
    orders.append(
      create(
        Order,
        {
          'status': OrderStatus.BOOKED,
          'type': service_types[index % len(service_types)],
          'addressee': f'Destinatario {index + 1}',
          'address': f'Via Consegna {index + 1}, Bari',
          'cap': '70020',
          'dpc': today,
          'drc': today,
          'anomaly': index % 6 == 0,
          'delay': index % 5 == 0,
          'confirmed': True,
          'floor': (index % 4) + 1,
          'elevator': index % 3 != 0,
          'addressee_contact': f'+39080000{index + 1:03d}',
          'booking_date': today,
          'confirmation_date': None,
          'completion_date': None,
          'customer_note': f'Nota cliente {index + 1}',
          'operator_note': 'Ordine seed per pianificazione admin',
          'mark': float((index % 5) + 1),
          'external_id': f'PLAN-{1000 + index}',
          'external_status': EuronicsStatus.CONFIRMED,
        },
      )
    )

    if index < 3:
      # For the first three, force linking to professional services
      su = create(
        ServiceUser,
        {
          'code': f'PRO-SU-{index + 1}',
          'price': 99.99 + index,
          'user_id': delivery_users[index].id,
          'service_id': professional_srv_ids[index],
        },
      )
      create(
        Product,
        {
          'name': f'ProdottoPro-{index + 1}',
          'order_id': orders[index].id,
          'service_user_id': su.id,
          'collection_point_id': collection_points[index % 10].id,
        },
      )
    else:
      create(
        Product,
        {
          'name': f'Prodotto {index + 1}',
          'order_id': orders[index].id,
          'service_user_id': service_users[index % 10].id,
          'collection_point_id': collection_points[index % 10].id,
        },
      )

  for index in range(10):
    create(
      Photo,
      {
        'link': f'https://example.com/photos/order-{orders[index].id}.jpg',
        'order_id': orders[index].id,
      },
    )
    create(
      Motivation,
      {
        'text': f'Motivazione {index + 1}',
        'delay': index % 2 == 0,
        'anomaly': index % 3 == 0,
        'status': OrderStatus.NOT_DELIVERED if index % 2 == 0 else OrderStatus.REDELIVERY,
        'order_id': orders[index].id,
      },
    )
    create(
      Log,
      {
        'content': f'Log operativo seed {index + 1}',
        'user_id': operator_user.id if index % 2 == 0 else admin_user.id,
      },
    )


def can_create() -> bool:
  tracked_models = [
    User,
    DeliveryUserInfo,
    CustomerUserInfo,
    CustomerGroup,
    CustomerRule,
    DeliveryGroup,
    Transport,
    Order,
    Motivation,
    Schedule,
    ScheduleItem,
    ScheduleItemOrder,
    ScheduleItemCollectionPoint,
    Photo,
    CollectionPoint,
    Service,
    ServiceUser,
    Product,
    RaeProductGroup,
    GeographicZone,
    GeographicCode,
    Constraint,
    Log,
  ]
  with Session() as session:
    return all(session.query(model).count() == 0 for model in tracked_models)

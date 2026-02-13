from datetime import date

from database_api import Session
from database_api.operations import create
from .enum import UserRole, OrderType, OrderStatus
from .schema import User, Transport, CollectionPoint, Service, ServiceUser, Order, Product


def seed_data():
  if can_create():
    create(
      User,
      {
        'nickname': 'admin',
        'password': 'MTIzNDU2Nzg5MDEyMzQ1Nk74aeshlmbNA9Dmmq+dowI=',
        'role': UserRole.get_enum_option('Admin'),
      },
    )
    create(
      User,
      {
        'nickname': 'operator',
        'password': 'MTIzNDU2Nzg5MDEyMzQ1NhB1m3hNtcmV3SS6RJWD/lM=',
        'role': UserRole.get_enum_option('Operator'),
      },
    )
    create(
      User,
      {
        'nickname': 'delivery',
        'password': 'MTIzNDU2Nzg5MDEyMzQ1NveX8dFMr4LXoKyncdgq94g=',
        'role': UserRole.get_enum_option('Delivery'),
      },
    )
    create(
      User,
      {
        'nickname': 'customer',
        'password': 'MTIzNDU2Nzg5MDEyMzQ1NlDCtaLDuTiPZS2I6jtlNI4=',
        'role': UserRole.get_enum_option('Customer'),
      },
    )

    create(Transport, {'name': 'Auto', 'plate': 'AA123BB'})

    create(
      CollectionPoint,
      {'name': 'Punto di ritiro', 'address': 'Barletta, 76121 Barletta BT, Italia', 'cap': '76121', 'user_id': 4},
    )

    create(Service, {'name': 'Servizio', 'type': OrderType.DELIVERY})

    create(ServiceUser, {'price': 10, 'user_id': 4, 'service_id': 1})

    create(
      Order,
      {
        'status': OrderStatus.NEW,
        'type': OrderType.DELIVERY,
        'addressee': 'Destinatario di prova',
        'address': "27, Via Simone D'Orsenigo, Milano, MI",
        'cap': '20135',
        'dpc': date.today().strftime('%Y-%m-%d'),
        'drc': date.today().strftime('%Y-%m-%d'),
      },
    )

    create(
      Product,
      {'order_id': 1, 'name': 'Prodotto di prova', 'service_user_id': 1, 'collection_point_id': 1},
    )


def can_create() -> bool:
  with Session() as session:
    return all(
      [
        session.query(User).count() == 0,
        session.query(Transport).count() == 0,
        session.query(CollectionPoint).count() == 0,
        session.query(Service).count() == 0,
        session.query(ServiceUser).count() == 0,
        session.query(Order).count() == 0,
        session.query(Product).count() == 0,
      ]
    )

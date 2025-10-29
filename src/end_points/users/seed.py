from database_api import Session
from database_api.operations import create
from ...database.enum import UserRole, OrderType
from ...database.schema import User, Transport, CollectionPoint, Service, ServiceUser


def seed_data():
  with Session() as session:
    if all(
      [
        session.query(User).count() == 0,
        session.query(Transport).count() == 0,
        session.query(CollectionPoint).count() == 0,
        session.query(Service).count() == 0,
        session.query(ServiceUser).count() == 0,
      ]
    ):
      create(
        User,
        {
          'nickname': 'admin',
          'password': 'MTIzNDU2Nzg5MDEyMzQ1Nk74aeshlmbNA9Dmmq+dowI=',
          'role': UserRole.get_enum_option('Admin'),
        },
        session=session,
      )
      create(
        User,
        {
          'nickname': 'operator',
          'password': 'MTIzNDU2Nzg5MDEyMzQ1NhB1m3hNtcmV3SS6RJWD/lM=',
          'role': UserRole.get_enum_option('Operator'),
        },
        session=session,
      )
      create(
        User,
        {
          'nickname': 'delivery',
          'password': 'MTIzNDU2Nzg5MDEyMzQ1NveX8dFMr4LXoKyncdgq94g=',
          'role': UserRole.get_enum_option('Delivery'),
        },
        session=session,
      )
      create(
        User,
        {
          'nickname': 'customer',
          'password': 'MTIzNDU2Nzg5MDEyMzQ1NlDCtaLDuTiPZS2I6jtlNI4=',
          'role': UserRole.get_enum_option('Customer'),
        },
        session=session,
      )

      create(Transport, {'name': 'Auto', 'plate': 'AA123BB'}, session=session)

      create(
        CollectionPoint,
        {'name': 'Punto di ritiro', 'address': 'Barletta, 76121 Barletta BT, Italia', 'cap': '76121', 'user_id': 4},
        session=session,
      )

      create(Service, {'name': 'Servizio', 'type': OrderType.DELIVERY}, session=session)

      create(ServiceUser, {'price': 10, 'user_id': 4, 'service_id': 1}, session=session)

      session.commit()

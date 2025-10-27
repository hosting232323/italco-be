from database_api import Session
from ...database.enum import UserRole, OrderType
from ...database.schema import User, Transport, CollectionPoint, Service, ServiceUser
from database_api.operations import create


def seed_data():
  with Session() as session:
    if not session.query(User).count():
      for user in CONFIG:
        create(User,
          {'nickname': user['nickname'], 'password': user['password'], 'role': UserRole.get_enum_option(user['role'])},
        session=session)

    if not session.query(Transport).count():
      create(Transport,
        {'name': 'Auto', 'plate': 'AA123BB'},
        session=session)

    if not session.query(CollectionPoint).count():
      create(CollectionPoint,
        {'name': 'Punto di ritiro', 'address': 'Barletta, 76121 Barletta BT, Italia', 'cap': '76121', 'user_id': 4},
        session=session)

    if not session.query(Service).count():
      create(Service,
        {'name': 'Servizio', 'type': OrderType.DELIVERY},
        session=session)

    if not session.query(ServiceUser).count():
      create(ServiceUser,
        {'price': 10, 'user_id': 4, 'service_id': 1},
        session=session)
    
    session.commit()


CONFIG = [
  {'nickname': 'admin', 'password': 'MTIzNDU2Nzg5MDEyMzQ1Nk74aeshlmbNA9Dmmq+dowI=', 'role': 'Admin'},
  {'nickname': 'operator', 'password': 'MTIzNDU2Nzg5MDEyMzQ1NhB1m3hNtcmV3SS6RJWD/lM=', 'role': 'Operator'},
  {'nickname': 'delivery', 'password': 'MTIzNDU2Nzg5MDEyMzQ1NveX8dFMr4LXoKyncdgq94g=', 'role': 'Delivery'},
  {'nickname': 'customer', 'password': 'MTIzNDU2Nzg5MDEyMzQ1NlDCtaLDuTiPZS2I6jtlNI4=', 'role': 'Customer'},
]

from database_api import Session
from ...database.enum import UserRole
from ...database.schema import ItalcoUser
from database_api.operations import create


def seed_users():
  with Session() as session:
    if not session.query(ItalcoUser).count():
      for user in CONFIG:
        create(ItalcoUser, {
          'email': user['email'],
          'password': user['password'],
          'role': UserRole.get_enum_option(user['role'])
        })


CONFIG = [
  {
    'email': 'admin',
    'password': 'MTIzNDU2Nzg5MDEyMzQ1Nk74aeshlmbNA9Dmmq+dowI=',
    'role': 'Admin'
  },
  {
    'email': 'operator',
    'password': 'MTIzNDU2Nzg5MDEyMzQ1NhB1m3hNtcmV3SS6RJWD/lM=',
    'role': 'Operator'
  },
  {
    'email': 'delivery',
    'password': 'MTIzNDU2Nzg5MDEyMzQ1NveX8dFMr4LXoKyncdgq94g=',
    'role': 'Delivery'
  },
  {
    'email': 'customer',
    'password': 'MTIzNDU2Nzg5MDEyMzQ1NlDCtaLDuTiPZS2I6jtlNI4=',
    'role': 'Customer'
  }
]

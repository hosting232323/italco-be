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
    'password': '1234admin',
    'role': 'Admin'
  },
  {
    'email': 'operator',
    'password': '1234operator',
    'role': 'Operator'
  },
  {
    'email': 'delivery',
    'password': '1234delivery',
    'role': 'Delivery'
  },
  {
    'email': 'customer',
    'password': '1234customer',
    'role': 'Customer'
  }
]

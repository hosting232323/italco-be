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
    'password': 'dW5kZWZpbmVk4NWOv2Of1hCY7cc6a6r1yw==',
    'role': 'Admin'
  },
  {
    'email': 'operator',
    'password': 'dW5kZWZpbmVkrQF4qKkmtc017w13p+kO4w==',
    'role': 'Operator'
  },
  {
    'email': 'delivery',
    'password': 'dW5kZWZpbmVkrv4msa1rrnqOIb5c8/L91Q==',
    'role': 'Delivery'
  },
  {
    'email': 'customer',
    'password': 'dW5kZWZpbmVkEhxq/DiYm5YEi0p8QmsrZA==',
    'role': 'Customer'
  }
]

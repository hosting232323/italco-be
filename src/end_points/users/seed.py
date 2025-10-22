from database_api import Session
from ...database.enum import UserRole
from ...database.schema import User
from database_api.operations import create


def seed_users():
  with Session() as session:
    if not session.query(User).count():
      for user in CONFIG:
        create(
          User,
          {'nickname': user['nickname'], 'password': user['password'], 'role': UserRole.get_enum_option(user['role'])},
        )


CONFIG = [
  {'nickname': 'admin', 'password': 'MTIzNDU2Nzg5MDEyMzQ1Nk74aeshlmbNA9Dmmq+dowI=', 'role': 'Admin'},
  {'nickname': 'operator', 'password': 'MTIzNDU2Nzg5MDEyMzQ1NhB1m3hNtcmV3SS6RJWD/lM=', 'role': 'Operator'},
  {'nickname': 'delivery', 'password': 'MTIzNDU2Nzg5MDEyMzQ1NveX8dFMr4LXoKyncdgq94g=', 'role': 'Delivery'},
  {'nickname': 'customer', 'password': 'MTIzNDU2Nzg5MDEyMzQ1NlDCtaLDuTiPZS2I6jtlNI4=', 'role': 'Customer'},
]

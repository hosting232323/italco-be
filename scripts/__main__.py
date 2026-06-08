import os

from database_api import set_database


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])

  # Good job bro

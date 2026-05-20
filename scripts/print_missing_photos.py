import os

from sqlalchemy import select

from src.database.schema import Photo
from database_api import Session, set_database

photos = [
  '15045.png',
  '15046.png',
  '15047.png',
  '15048.png',
  '15049.png',
  '15050.png',
  '15070.png',
  '15071.png',
  '15760.png',
  '17785.png',
  '17786.png',
  '17787.png',
  '17788.png'
]

if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])

  with Session() as session:
    for photo in photos:
      result = session.execute(
        select(Photo).where(Photo.link.like(f'%/{photo}'))
      ).scalar_one_or_none()

      print(result)

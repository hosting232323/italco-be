import os
from tqdm import tqdm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as session_type

from src.database.schema import Photo
from database_api.operations import get_by_id, update
from src.end_points.orders.photo import PHOTO_HOSTNAME


OLD_ENGINE_DB_URL = 'XXX'


def get_old_photos(Session: sessionmaker) -> list[Photo]:
  with Session() as session:
    session: session_type
    return session.query(Photo).all()


if __name__ == '__main__':
  old_Session = sessionmaker(bind=create_engine(OLD_ENGINE_DB_URL))
  new_Session = sessionmaker(bind=create_engine(os.environ['DATABASE_URL']))

  for old_photo in tqdm(get_old_photos(old_Session)):
    new_photo: Photo = get_by_id(Photo, old_photo.id, session=new_Session())
    if new_photo:
      update(
        new_photo,
        {'link': f'{PHOTO_HOSTNAME}{os.path.basename(old_photo.link)}'},
        session=new_Session(),
      )

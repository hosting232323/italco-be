import os
from tqdm import tqdm
from pathlib import Path
from sqlalchemy import func

from database_api import set_database, Session
from database_api.operations import update
from src.database.schema import Photo


PHOTOS_DIR = Path("/media/vanni/Volume/Italco/photos")
BATCH_SIZE = 182


def get_photos() -> list[Photo]:
  with Session() as session:
    return session.query(Photo).filter(
      Photo.id > session.query(func.max(Photo.id)).filter(
        Photo.photo.is_(None)
      ).scalar()
    ).order_by(
      Photo.id.asc()
    ).limit(
      BATCH_SIZE
    ).all()


def guess_extension(mime_type: str) -> str:
  if mime_type == "image/jpeg":
    return ".jpg"
  if mime_type == "image/png":
    return ".png"
  if mime_type == "image/webp":
    return ".webp"
  return ""


def save_file(photo_obj: Photo):
  PHOTOS_DIR.mkdir(exist_ok=True)
  ext = guess_extension(photo_obj.mime_type)
  file_path = PHOTOS_DIR / f"{photo_obj.id}{ext}"

  with open(file_path, "wb") as f:
    f.write(photo_obj.photo)

  return str(file_path)


def migrate_photo(photo_obj: Photo):
  new_path = save_file(photo_obj)
  update(photo_obj, {"photo": None, "path": new_path})


if __name__ == "__main__":
  set_database(os.environ['DATABASE_URL'])

  for photo in tqdm(get_photos()):
    migrate_photo(photo)

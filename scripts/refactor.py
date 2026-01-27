import os
from tqdm import tqdm

from database_api import set_database
from database_api.operations import get_all
from src.database.schema import Photo


FOLDER_1 = r"C:\Users\giuse\Desktop\backup\backup_nagasaki\photos\prod"
FOLDER_2 = r"C:\Users\giuse\Desktop\backup\photos-backup-atene\photos"


def extract_photo_id(url: str) -> str | None:
  if not url:
    return None
  filename = url.split('/')[-1]
  return os.path.splitext(filename)[0]


def exists_in_folders(photo_id: str) -> bool:
  for folder in (FOLDER_1, FOLDER_2):
    if not os.path.isdir(folder):
      continue
    for file in os.listdir(folder):
      if photo_id in file:
        return True
  return False


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])

  photos = get_all(Photo)

  missing = []

  for photo in tqdm(photos):
    photo_id = extract_photo_id(photo.link)
    if not photo_id:
      continue

    if not exists_in_folders(photo_id):
      missing.append(photo)

  missing.sort(key=lambda p: p.created_at)

  for photo in missing:
    print(photo)

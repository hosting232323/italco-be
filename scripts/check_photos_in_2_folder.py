import os
from tqdm import tqdm

FOLDER1 = r"C:\Users\giuse\Desktop\cartella1"
FOLDER2 = r"C:\Users\giuse\Desktop\cartella2"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png",}

def list_photos(folder: str) -> set[str]:
    if not os.path.isdir(folder):
        return set()
    return {os.path.splitext(f)[0] for f in os.listdir(folder) 
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS}

def photos_missing_in_folder1(folder1: str, folder2: str) -> list[str]:
    photos1 = list_photos(folder1)
    photos2 = list_photos(folder2)

    missing = photos1 - photos2
    return sorted(missing)

if __name__ == "__main__":
    missing_photos = photos_missing_in_folder1(FOLDER1, FOLDER2)

    print(f"Foto presenti in {FOLDER1} ma non in {FOLDER2}:")
    for photo in tqdm(missing_photos):
        print(photo)

import os
import hashlib
import shutil
from tqdm import tqdm

FOLDER1 = r"/home/gralogic/Scrivania/solo_id/photos"
FOLDER2 = r"/home/gralogic/Scrivania/STATIC_FOLDER/photos/prod"
OUTPUT_FOLDER = r"/home/gralogic/Scrivania/unique_photos"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def file_hash(path):
    hasher = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def collect_files(folder):
    files = []
    for root, dirs, filenames in os.walk(folder):
        for name in filenames:
            files.append(os.path.join(root, name))
    return files


print("Raccolta file...")

files1 = collect_files(FOLDER1)
files2 = collect_files(FOLDER2)

print(f"File in FOLDER1: {len(files1)}")
print(f"File in FOLDER2: {len(files2)}")

hashes = {}

print("Calcolo hash FOLDER1...")

for f in tqdm(files1):
    h = file_hash(f)
    hashes[h] = f

print("Confronto con FOLDER2...")

unique_files = []

for f in tqdm(files2):
    h = file_hash(f)

    if h not in hashes:
        unique_files.append(f)

print(f"\nFile unici trovati: {len(unique_files)}")

print("Copiando i file unici...")

for f in tqdm(unique_files):
    filename = os.path.basename(f)
    dest = os.path.join(OUTPUT_FOLDER, filename)
    shutil.copy2(f, dest)

print("\nOperazione completata.")
print(f"I file unici sono in: {OUTPUT_FOLDER}")
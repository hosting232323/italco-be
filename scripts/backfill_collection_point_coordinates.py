"""Ricalcola le coordinate dei punti di ritiro che stanno nel posto sbagliato.

Un punto salvato prima che la ricerca tenesse conto del CAP può essere finito in
un altro comune ("Via Cesare Battisti, 742, Taranto, TA" a Ginosa). Si
ricalcola la posizione con il CAP e si cambia solo dove la nuova distanza dal
vecchio punto supera la soglia: i punti già giusti non si toccano.

  python -m scripts.backfill_collection_point_coordinates --dry-run     # mostra cosa cambierebbe
  python -m scripts.backfill_collection_point_coordinates               # scrive
  python -m scripts.backfill_collection_point_coordinates --min-km 1    # soglia di spostamento
"""

# ruff: noqa: T201
import argparse
import math
import os

from sqlalchemy import create_engine, text

from src.utils.caps import get_lat_lon_by_address


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
  lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
  haversine = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
  return 6371 * 2 * math.asin(math.sqrt(haversine))


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--dry-run', action='store_true', help='mostra le differenze, non scrive')
  parser.add_argument('--min-km', type=float, default=5, help='sposta solo se la nuova posizione dista almeno cosi')
  args = parser.parse_args(argv)

  with create_engine(os.environ['DATABASE_URL']).begin() as connection:
    points = connection.execute(
      text('SELECT id, name, address, cap, lat, lon FROM collection_point WHERE address IS NOT NULL')
    ).all()
    update = text('UPDATE collection_point SET lat = :lat, lon = :lon WHERE id = :id')
    changed = 0
    for point in points:
      new = get_lat_lon_by_address(point.address, point.cap)
      if new[0] is None:
        continue
      if point.lat is not None:
        km = distance_km((point.lat, point.lon), new)
        if km < args.min_km:
          continue
        print(f'#{point.id} {point.name} - {point.address} ({point.cap}): {km:.0f} km di differenza')
      else:
        print(f'#{point.id} {point.name} - {point.address} ({point.cap}): senza coordinate, nuove {new}')
      changed += 1
      if not args.dry_run:
        connection.execute(update, {'id': point.id, 'lat': new[0], 'lon': new[1]})
    print(f'{changed} punti {"da aggiornare" if args.dry_run else "aggiornati"} su {len(points)}')


if __name__ == '__main__':
  main()

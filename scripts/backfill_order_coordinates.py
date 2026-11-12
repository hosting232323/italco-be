"""Salva le coordinate dell'indirizzo sugli ordini che non le hanno.

Gli ordini nuovi scelti dal menu Google le portano dal form; quelli già nel
database (e gli importati) no, e vengono geocodificati a ogni pianificazione.
Qui si salvano una volta per tutte, ma solo quando Nominatim trova l'indirizzo
completo: la colonna è "la posizione vera". Per gli indirizzi che si trovano
solo al livello della via o del comune resta il ripiego a runtime
(get_lat_lon_by_address), che non va congelato come se fosse esatto.

  python -m scripts.backfill_order_coordinates             # ordini con dpc da oggi in poi
  python -m scripts.backfill_order_coordinates --all       # tutti gli ordini
  python -m scripts.backfill_order_coordinates --dry-run   # conta e basta
"""

# ruff: noqa: T201
import argparse
import os
from concurrent.futures import ThreadPoolExecutor

import requests
from sqlalchemy import create_engine, text

from src.utils.caps import _postcode_matches, _search


def exact_coordinates(address: str, cap: str | None = None) -> tuple[float, float] | tuple[None, None]:
  try:
    results = _search(q=address)
  except requests.RequestException:
    return None, None
  # La ricerca libera trova la prima via con quel nome nella provincia: se cade
  # in un altro CAP e' un altro comune, e non va congelata come posizione vera.
  results = [result for result in results if not cap or _postcode_matches(result, cap)]
  if not results:
    return None, None
  return float(results[0]['lat']), float(results[0]['lon'])


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--all', action='store_true', help='anche gli ordini con dpc passata')
  parser.add_argument('--dry-run', action='store_true', help='geocodifica e conta, non scrive')
  args = parser.parse_args(argv)

  query = 'SELECT DISTINCT address, cap FROM "order" WHERE address_lat IS NULL'
  if not args.all:
    query += ' AND dpc >= CURRENT_DATE'

  with create_engine(os.environ['DATABASE_URL']).begin() as connection:
    addresses = [(row.address, row.cap) for row in connection.execute(text(query))]
    print(f'{len(addresses)} indirizzi senza coordinate')
    with ThreadPoolExecutor(max_workers=8) as executor:
      resolved = dict(zip(addresses, executor.map(lambda item: exact_coordinates(*item), addresses)))

    found = {address: coords for address, coords in resolved.items() if coords[0] is not None}
    print(f"{len(found)} trovati con l'indirizzo completo, {len(addresses) - len(found)} lasciati al ripiego")
    if args.dry_run:
      return

    update = text(
      'UPDATE "order" SET address_lat = :lat, address_lon = :lon '
      'WHERE address = :address AND cap = :cap AND address_lat IS NULL'
    )
    for (address, cap), (lat, lon) in found.items():
      connection.execute(update, {'address': address, 'cap': cap, 'lat': lat, 'lon': lon})
    print('fatto')


if __name__ == '__main__':
  main()

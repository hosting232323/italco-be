"""Genera ordini BOOKED per una data, da usare come banco di prova della
pianificazione automatica (motore a regole o strategy=ai).

Riusa i cataloghi gia' presenti (ServiceUser, Service, CollectionPoint): serve
quindi un database gia' seedato. Gli ordini vengono distribuiti su piu' CAP
baresi cosi' che il raggruppamento geografico abbia qualcosa da fare, e circa
un quarto usa un servizio professionale per esercitare il limite per gruppo.

Uso:
  python -m scripts.seed_planning_orders                     # domani, 18 ordini
  python -m scripts.seed_planning_orders --date 2026-09-15 --count 24
  python -m scripts.seed_planning_orders --company-id 1 --cap 70121 --cap 70019
"""

import argparse
import os
import random
from datetime import date, datetime, timedelta

from database_api import Session, scope, set_database
from database_api.operations import create

from src.database.enum import EuronicsStatus, OrderStatus
from src.database.schema import CollectionPoint, Company, Order, Product, Service, ServiceUser, User


# CAP dell'area barese; quelli assenti da CAPS_DATA vengono scartati a runtime.
DEFAULT_CAPS = [
  '70121', '70122', '70123', '70124', '70125', '70126', '70129', '70131',
  '70132', '70019', '70032', '70026', '70056', '70010', '70017',
]


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  tomorrow = date.today() + timedelta(days=1)
  parser.add_argument('--date', type=_iso_date, default=tomorrow, help='YYYY-MM-DD, default domani')
  parser.add_argument('--count', type=int, default=18, help='numero di ordini, default 18')
  parser.add_argument('--company-id', type=int, help='obbligatorio solo se ci sono piu\' company')
  parser.add_argument('--cap', action='append', dest='caps', help='CAP da usare (ripetibile); default: area barese')
  parser.add_argument('--seed', type=int, default=0, help='seed del random per una distribuzione riproducibile')
  return parser.parse_args()


def _iso_date(value: str) -> date:
  return datetime.strptime(value, '%Y-%m-%d').date()


def resolve_company_id(explicit: int | None) -> int:
  with Session() as session:
    if explicit is not None:
      company = session.get(Company, explicit)
      if not company:
        raise SystemExit(f'Company {explicit} inesistente')
      return company.id

    companies = session.query(Company).all()
    if not companies:
      raise SystemExit('Nessuna company: esegui prima il seed')
    if len(companies) == 1:
      return companies[0].id
    named = [company for company in companies if company.name == 'Ares Logistics']
    if named:
      return named[0].id
    listing = ', '.join(f'{company.id}:{company.name}' for company in companies)
    raise SystemExit(f'Piu\' company presenti, passa --company-id (una fra {listing})')


def valid_caps(requested: list[str] | None) -> list[str]:
  from src.utils.caps import get_lat_lon_by_cap

  usable = []
  for cap in requested or DEFAULT_CAPS:
    try:
      get_lat_lon_by_cap(cap)
      usable.append(cap)
    except (ValueError, KeyError):
      print(f'  CAP {cap} assente da CAPS_DATA, lo salto')
  if not usable:
    raise SystemExit('Nessun CAP valido tra quelli richiesti')
  return usable


def load_catalog(session) -> tuple[list, list, list]:
  rows = session.query(ServiceUser, Service).join(Service, Service.id == ServiceUser.service_id).all()
  if not rows:
    raise SystemExit('Nessun ServiceUser nel database: esegui prima il seed (python -m src.database.seed)')
  professional = [(su, srv) for su, srv in rows if srv.professional]
  standard = [(su, srv) for su, srv in rows if not srv.professional] or professional

  collection_points = session.query(CollectionPoint).all()
  if not collection_points:
    any_user = session.query(User).first()
    collection_points = [
      create(
        CollectionPoint,
        {
          'name': 'Punto di ritiro test AI',
          'address': 'Via Magazzino 1, Bari',
          'cap': '70121',
          'user_id': any_user.id,
        },
      )
    ]
  return professional, standard, collection_points


def main() -> None:
  set_database(os.environ['DATABASE_URL'])
  args = parse_args()
  random.seed(args.seed)

  caps = valid_caps(args.caps)
  company_id = resolve_company_id(args.company_id)

  with scope(company_id=company_id):
    with Session() as session:
      professional, standard, collection_points = load_catalog(session)

    created = []
    for index in range(args.count):
      cap = caps[index % len(caps)]
      use_professional = professional and index % 4 == 0
      service_user, service = random.choice(professional if use_professional else standard)
      collection_point = collection_points[index % len(collection_points)]

      order = create(
        Order,
        {
          'status': OrderStatus.BOOKED,
          'type': service.type,
          'addressee': f'Cliente AI {index + 1}',
          'address': f'Via di Prova {index + 1}, Bari',
          'cap': cap,
          'dpc': args.date,
          'drc': args.date,
          'booking_date': args.date,
          'confirmed': True,
          'addressee_contact': f'+390800{index + 1:05d}',
          'operator_note': 'Ordine di test per la pianificazione automatica',
          'external_id': f'AIPLAN-{args.date.isoformat()}-{index + 1:02d}',
          'external_status': EuronicsStatus.CONFIRMED,
        },
      )
      create(
        Product,
        {
          'name': f'Prodotto AI {index + 1}',
          'order_id': order.id,
          'service_user_id': service_user.id,
          'collection_point_id': collection_point.id,
        },
      )
      created.append((order.id, cap, service.type.value, service.professional))

  print(f'\nCreati {len(created)} ordini BOOKED per il {args.date.isoformat()} (company {company_id}):')
  per_cap: dict[str, int] = {}
  professional_count = 0
  for _, cap, _type, is_pro in created:
    per_cap[cap] = per_cap.get(cap, 0) + 1
    professional_count += 1 if is_pro else 0
  for cap, amount in sorted(per_cap.items()):
    print(f'  {cap}: {amount}')
  print(f'  di cui professionali: {professional_count}')
  print(f'  id: {min(o[0] for o in created)}..{max(o[0] for o in created)}')


if __name__ == '__main__':
  main()

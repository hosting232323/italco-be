# ruff: noqa: E402, T201
"""Crea (o rigenera) la company di revisione per Apple: un corriere demo con i borderò pronti da provare.

Serve a far girare Hubstra Delivery al revisore di App Store Connect su dati inventati, senza toccare
nessun cliente vero. Crea, in una company a parte:

  - il corriere demo (nickname e password da mandare ad Apple) sul suo veicolo;
  - un cliente (punto vendita) fittizio con 2 punti di ritiro, un servizio e i prodotti;
  - un borderò per ogni giorno, da `--past-days` giorni fa a `--days` giorni da oggi, ognuno con
    2 ritiri, 4 consegne e 1 attività, così il revisore può completare un ritiro, chiudere una consegna
    con foto e firma, segnare "non consegnato", "da riprogrammare" e un'anomalia. I giorni passati sono
    già completati e riempiono lo "Storico".

  python -m scripts.create_review_account --dry-run
  python -m scripts.create_review_account
  python -m scripts.create_review_account --days 45 --password '...'
  python -m scripts.create_review_account --reset

Il comando e' idempotente: un secondo lancio aggiunge solo i giorni che mancano e non duplica utenti,
veicolo, punti di ritiro e prodotti. `--reset` elimina i borderò e gli ordini della company di
revisione e li ricrea da oggi (per ripartire da dati intatti dopo che il revisore ha completato
operazioni). Non tocca mai altre company.

Sicurezza:
  - gli ordini hanno `addressee_contact` vuoto: con un numero, `delay_sms_check` manderebbe SMS veri;
  - le email dei clienti finti sono su `@example.invalid`, dominio che non recapita. In produzione
    `mailer_check` (orders/mailer.py) manda comunque una email agli indirizzi di `MAILS` quando il
    revisore segna "non consegnato", un ritardo o un'anomalia: va messo in conto;
  - la password generata si stampa una sola volta a fine comando e non viene scritta da nessuna parte.

Marcatura dei dati creati qui: gli ordini hanno `external_id` che inizia per "REVIEW-" e gli utenti sono
solo il corriere e il suo punto vendita. Se la company col nome dato contiene altro, lo script si rifiuta
di lavorarci.
"""

import argparse
import os
import secrets
import sys
from datetime import date, time, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from api.users.security import hash_password
from database_api import Session, scope, set_database
from database_api.operations import create, update

from src.database.enum import OrderStatus, OrderType, ScheduleType, UserRole
from src.database.schema import (
  Company,
  CollectionPoint,
  CustomerGroup,
  CustomerUserInfo,
  DeliveryUserInfo,
  History,
  Order,
  OrderTrackingToken,
  Photo,
  Product,
  Schedule,
  ScheduleItem,
  ScheduleItemActivity,
  ScheduleItemCollectionPoint,
  ScheduleItemOrder,
  ScheduleItemUser,
  Service,
  ServiceUser,
  Transport,
  User,
)


DEFAULT_COMPANY_NAME = 'Revisione Apple'
DEFAULT_NICKNAME = 'revisore.apple'
DEFAULT_DAYS = 30
DEFAULT_PAST_DAYS = 7
MARKER = 'REVIEW-'
EMAIL_DOMAIN = 'example.invalid'
PASSWORD_ALPHABET = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
PASSWORD_LENGTH = 14

PICKUPS = [
  {
    'name': 'Punto di ritiro Demo 1',
    'address': 'Via Magazzino 10, Barletta',
    'cap': '70051',
    'lat': 41.3197,
    'lon': 16.2814,
    'slot': (time(8, 0), time(9, 0)),
  },
  {
    'name': 'Punto di ritiro Demo 2',
    'address': 'Via Industria 5, Bari',
    'cap': '70132',
    'lat': 41.1255,
    'lon': 16.8300,
    'slot': (time(9, 0), time(10, 0)),
  },
]

# (destinatario, indirizzo, cap, lat, lon): ruotano di giorno in giorno così i borderò non sono tutti uguali.
ADDRESSEES = [
  ('Rossi Mario', 'Via Garibaldi 12, Barletta', '70051', 41.3190, 16.2850),
  ('Bianchi Anna', 'Via Roma 45, Bari', '70121', 41.1171, 16.8719),
  ('Verdi Luca', 'Corso Vittorio Emanuele 8, Monopoli', '70043', 40.9531, 17.3005),
  ('Esposito Giulia', 'Via Dante 3, Bisceglie', '70052', 41.2417, 16.5051),
  ('Ferrari Paolo', 'Via Mazzini 20, Trani', '70059', 41.2761, 16.4156),
  ('Romano Sara', 'Via Cavour 7, Molfetta', '70056', 41.2000, 16.5988),
]
PRODUCTS = ['Lavatrice Demo', 'Frigorifero Demo', 'Lavastoviglie Demo', 'Forno Demo']
# Le consegne ritirano i prodotti dai due punti: le prime due dal primo, le altre dal secondo.
DELIVERY_SLOTS = [
  (time(10, 0), time(12, 0)),
  (time(12, 0), time(13, 30)),
  (time(14, 0), time(16, 0)),
  (time(16, 0), time(18, 0)),
]
ACTIVITY_SLOT = (time(13, 30), time(14, 0))


class ReviewAccountError(Exception):
  """Situazione in cui lo script si ferma senza scrivere nulla."""


def customer_nickname(courier_nickname: str) -> str:
  return f'{courier_nickname}.punto-vendita'


def generate_password() -> str:
  # Senza caratteri ambigui (0/O, 1/l/I): il revisore la digita a mano su un iPhone.
  return ''.join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))


def find_company(name: str) -> Company | None:
  with Session() as session:
    return session.query(Company).filter(Company.name == name).first()


def find_user_anywhere(nickname: str) -> User | None:
  """Cerca l'utente in tutte le company: il nickname e' unico sull'intera piattaforma."""
  with Session() as session:
    session.info.pop('company_id', None)
    return session.query(User).filter(User.nickname == nickname).first()


def check_company_is_ours(company: Company, nicknames: set[str]):
  """Rifiuta di lavorare in una company che contiene dati non creati da questo script."""
  with scope(company_id=company.id), Session() as session:
    foreign_orders = (
      session.query(Order)
      .filter(Order.company_id == company.id)
      .filter((Order.external_id.is_(None)) | (~Order.external_id.startswith(MARKER)))
      .count()
    )
    foreign_users = session.query(User).filter(User.company_id == company.id, User.nickname.notin_(nicknames)).count()
  if foreign_orders or foreign_users:
    raise ReviewAccountError(
      f'La company "{company.name}" contiene dati che non arrivano da questo script '
      f'({foreign_orders} ordini senza marcatura "{MARKER}", {foreign_users} utenti diversi dal demo): non la tocco.'
    )


def get_or_create(model, lookup: dict, values: dict | None = None):
  with Session() as session:
    found = session.query(model).filter_by(**lookup).first()
  if found:
    return found, False
  return create(model, {**lookup, **(values or {})}), True


def ensure_courier(company: Company, nickname: str, password: str | None):
  """Restituisce (corriere, creato, password_generata). La password generata esiste solo alla creazione."""
  generated = None
  if not password and not find_user_anywhere(nickname):
    generated = password = generate_password()

  courier, created = get_or_create(
    User, {'nickname': nickname}, {'role': UserRole.DELIVERY, 'password': hash_password(password or '')}
  )
  if not created and password:
    courier = update(courier, {'password': hash_password(password)})
  return courier, created, generated


def check_nicknames_are_free(company: Company | None, nicknames: set[str]):
  for nickname in sorted(nicknames):
    clash = find_user_anywhere(nickname)
    if clash and (company is None or clash.company_id != company.id):
      raise ReviewAccountError(
        f'Il nickname "{nickname}" è già usato in un\'altra company: scegline un altro con --nickname.'
      )


def ensure_master_data(company: Company, nickname: str, courier: User) -> dict:
  """Veicolo, punto vendita, punti di ritiro, servizio e prodotti: si creano una volta sola."""
  transport, _ = get_or_create(
    Transport,
    {'name': 'Furgone Demo', 'plate': 'DEMO01'},
    {'address': 'Via Magazzino 10, Barletta', 'cap': '70051'},
  )

  info, created = get_or_create(DeliveryUserInfo, {'user_id': courier.id}, {'transport_id': transport.id})
  if not created and info.transport_id != transport.id:
    update(info, {'transport_id': transport.id})

  group, _ = get_or_create(CustomerGroup, {'name': 'Gruppo Demo'})
  customer, _ = get_or_create(
    User,
    {'nickname': customer_nickname(nickname)},
    {
      'role': UserRole.CUSTOMER,
      # Il punto vendita non fa mai login: password casuale, mai mostrata.
      'password': hash_password(secrets.token_urlsafe(32)),
      'customer_group_id': group.id,
    },
  )
  get_or_create(
    CustomerUserInfo,
    {'user_id': customer.id},
    {
      'company_name': 'Punto Vendita Demo',
      'city': 'Bari',
      'address': 'Via Roma 1, Bari',
      'email': f'punto.vendita@{EMAIL_DOMAIN}',
      'import_code': f'{MARKER}CUST',
    },
  )

  pickups = []
  for pickup in PICKUPS:
    point, _ = get_or_create(
      CollectionPoint,
      {'name': pickup['name'], 'user_id': customer.id},
      {
        'address': pickup['address'],
        'cap': pickup['cap'],
        'lat': pickup['lat'],
        'lon': pickup['lon'],
        'opening_time': time(8, 0),
        'closing_time': time(18, 0),
      },
    )
    pickups.append(point)

  service, _ = get_or_create(
    Service,
    {'name': 'Consegna al piano Demo', 'type': OrderType.DELIVERY},
    {'duration': 30, 'description': 'Servizio di prova per la revisione', 'max_services': 10, 'professional': False},
  )
  service_user, _ = get_or_create(
    ServiceUser, {'service_id': service.id, 'user_id': customer.id}, {'code': f'{MARKER}SVC', 'price': 49.0}
  )
  return {'transport': transport, 'customer': customer, 'pickups': pickups, 'service_user': service_user}


def existing_schedule_dates(company_id: int, transport_id: int) -> set[date]:
  with scope(company_id=company_id), Session() as session:
    rows = (
      session.query(Schedule.date)
      .filter(Schedule.company_id == company_id, Schedule.transport_id == transport_id)
      .all()
    )
  return {row[0] for row in rows}


def create_day(day: date, today: date, master: dict):
  """Un borderò: 2 ritiri, 4 consegne e 1 attivita'. I giorni passati sono gia' completati."""
  past = day < today
  schedule = create(Schedule, {'date': day, 'transport_id': master['transport'].id})
  index = 0

  def add_item(operation_type: ScheduleType, slot: tuple[time, time]) -> ScheduleItem:
    nonlocal index
    index += 1
    return create(
      ScheduleItem,
      {
        'index': index,
        'completed': past,
        'start_time_slot': slot[0],
        'end_time_slot': slot[1],
        'operation_type': operation_type,
        'schedule_id': schedule.id,
      },
    )

  for pickup, point in zip(PICKUPS, master['pickups']):
    item = add_item(ScheduleType.COLLECTIONPOINT, pickup['slot'])
    create(ScheduleItemCollectionPoint, {'schedule_item_id': item.id, 'collection_point_id': point.id})

  offset = day.toordinal() % len(ADDRESSEES)
  for position, (product_name, slot) in enumerate(zip(PRODUCTS, DELIVERY_SLOTS)):
    if position == 2:
      activity_item = add_item(ScheduleType.ACTIVITY, ACTIVITY_SLOT)
      create(
        ScheduleItemActivity,
        {
          'title': 'Pausa pranzo (demo)',
          'note': "Attivita' di prova per la revisione",
          'duration_minutes': 30,
          'schedule_item_id': activity_item.id,
        },
      )

    addressee, address, cap, lat, lon = ADDRESSEES[(offset + position) % len(ADDRESSEES)]
    order = create(
      Order,
      {
        'status': OrderStatus.DELIVERED if past else OrderStatus.SCHEDULED,
        'type': OrderType.DELIVERY,
        'addressee': addressee,
        'address': address,
        'cap': cap,
        'address_lat': lat,
        'address_lon': lon,
        'dpc': day,
        'drc': day,
        'booking_date': day,
        'confirmation_date': day,
        'completion_date': day if past else None,
        'delivery_slot_start': slot[0],
        'delivery_slot_end': slot[1],
        'confirmed': True,
        'floor': (position % 3) + 1,
        'elevator': position % 2 == 0,
        # Vuoto di proposito: con un numero, delay_sms_check manderebbe un SMS vero.
        'addressee_contact': None,
        'customer_note': 'Ordine di prova per la revisione di App Store Connect',
        'operator_note': 'Dati inventati: nessun cliente reale',
        'external_id': f'{MARKER}{day:%Y%m%d}-{position + 1}',
      },
    )
    create(
      Product,
      {
        'name': product_name,
        'order_id': order.id,
        'service_user_id': master['service_user'].id,
        # Due consegne ritirano dal primo punto, due dal secondo: completati i ritiri si sbloccano.
        'collection_point_id': master['pickups'][position // 2].id,
        'collected': past,
      },
    )
    order_item = add_item(ScheduleType.ORDER, slot)
    create(ScheduleItemOrder, {'order_id': order.id, 'schedule_item_id': order_item.id})
  return schedule


def delete_generated_data(company: Company) -> dict:
  """Elimina borderò e ordini della company di revisione (e solo di quella)."""
  removed = {'schedules': 0, 'orders': 0}
  with scope(company_id=company.id), Session() as session:
    schedule_ids = [row[0] for row in session.query(Schedule.id).filter(Schedule.company_id == company.id)]
    item_ids = [
      row[0] for row in session.query(ScheduleItem.id).filter(ScheduleItem.schedule_id.in_(schedule_ids or [0]))
    ]
    order_ids = [
      row[0]
      for row in session.query(Order.id).filter(Order.company_id == company.id, Order.external_id.startswith(MARKER))
    ]

    def delete(model, *conditions):
      return session.query(model).filter(*conditions).delete(synchronize_session=False)

    if schedule_ids:
      delete(ScheduleItemUser, ScheduleItemUser.schedule_id.in_(schedule_ids))
    if item_ids:
      delete(ScheduleItemOrder, ScheduleItemOrder.schedule_item_id.in_(item_ids))
      delete(ScheduleItemCollectionPoint, ScheduleItemCollectionPoint.schedule_item_id.in_(item_ids))
      delete(ScheduleItemActivity, ScheduleItemActivity.schedule_item_id.in_(item_ids))
      delete(ScheduleItem, ScheduleItem.id.in_(item_ids))
    if schedule_ids:
      removed['schedules'] = delete(Schedule, Schedule.id.in_(schedule_ids), Schedule.company_id == company.id)
    if order_ids:
      delete(Photo, Photo.order_id.in_(order_ids))
      delete(History, History.order_id.in_(order_ids))
      delete(OrderTrackingToken, OrderTrackingToken.order_id.in_(order_ids))
      delete(Product, Product.order_id.in_(order_ids))
      removed['orders'] = delete(Order, Order.id.in_(order_ids), Order.company_id == company.id)
    # La posizione del corriere torna vuota, come prima di attivarla.
    delete_position = session.query(DeliveryUserInfo).filter(DeliveryUserInfo.company_id == company.id)
    delete_position.update({'lat': None, 'lon': None}, synchronize_session=False)
    session.commit()
  return removed


def day_range(today: date, days: int, past_days: int) -> list[date]:
  return [today + timedelta(days=offset) for offset in range(-past_days, days)]


def describe_plan(options, company: Company | None, nicknames: set[str]):
  """Stampa cosa farebbe il comando, senza scrivere nulla."""
  today = date.today()
  wanted = day_range(today, options.days, options.past_days)
  print('Simulazione (--dry-run): non viene scritto niente.')
  if not company:
    print(f'- Company "{options.company_name}": da creare')
    print(f'- Corriere "{options.nickname}", veicolo, punto vendita, 2 punti di ritiro, servizio: da creare')
    missing = wanted
  else:
    print(f'- Company "{options.company_name}": esiste (id {company.id})')
    with scope(company_id=company.id), Session() as session:
      transport = session.query(Transport).filter(Transport.name == 'Furgone Demo').first()
    existing = existing_schedule_dates(company.id, transport.id) if transport else set()
    if options.reset:
      print(f'- --reset: verrebbero eliminati {len(existing)} borderò e i loro ordini, poi ricreati')
      missing = wanted
    else:
      missing = [day for day in wanted if day not in existing]
  print(
    f'- Borderò da creare: {len(missing)} (dal {wanted[0]:%d/%m/%Y} al {wanted[-1]:%d/%m/%Y}, {len(wanted)} giorni)'
  )
  print(f'- Ordini da creare: {len(missing) * len(PRODUCTS)} (nessun numero di telefono, email su @{EMAIL_DOMAIN})')


def run(options) -> dict:
  """Esegue il comando e restituisce un riepilogo. Se la password e' stata generata, e' in `password`."""
  nicknames = {options.nickname, customer_nickname(options.nickname)}
  company = find_company(options.company_name)
  if company:
    check_company_is_ours(company, nicknames)
  check_nicknames_are_free(company, nicknames)

  if options.dry_run:
    describe_plan(options, company, nicknames)
    return {'dry_run': True, 'password': None}

  password = options.password or os.environ.get('REVIEW_PASSWORD') or None
  company = company or create(Company, {'name': options.company_name, 'automatic_planning': False, 'rae': False})

  summary = {'dry_run': False, 'removed': {'schedules': 0, 'orders': 0}, 'created_days': 0, 'password': None}
  with scope(company_id=company.id):
    courier, created, generated = ensure_courier(company, options.nickname, password)
    summary['courier_created'] = created
    summary['password'] = generated
    summary['password_set'] = bool(password)

    master = ensure_master_data(company, options.nickname, courier)

    if options.reset:
      summary['removed'] = delete_generated_data(company)
      existing = set()
    else:
      existing = existing_schedule_dates(company.id, master['transport'].id)

    today = date.today()
    for day in day_range(today, options.days, options.past_days):
      if day in existing:
        continue
      create_day(day, today, master)
      summary['created_days'] += 1

  summary['company_id'] = company.id
  return summary


def parse_args(argv=None):
  parser = argparse.ArgumentParser(description='Crea o rigenera la company di revisione per Apple.')
  parser.add_argument(
    '--company-name', default=DEFAULT_COMPANY_NAME, help=f'nome della company (default "{DEFAULT_COMPANY_NAME}")'
  )
  parser.add_argument(
    '--nickname', default=DEFAULT_NICKNAME, help=f'username del corriere demo (default "{DEFAULT_NICKNAME}")'
  )
  parser.add_argument('--password', help='password del corriere (o variabile REVIEW_PASSWORD); se manca viene generata')
  parser.add_argument(
    '--days', type=int, default=DEFAULT_DAYS, help=f'giorni di borderò da oggi (default {DEFAULT_DAYS})'
  )
  parser.add_argument(
    '--past-days',
    type=int,
    default=DEFAULT_PAST_DAYS,
    help=f"giorni passati gia' completati per lo Storico (default {DEFAULT_PAST_DAYS})",
  )
  parser.add_argument(
    '--reset', action='store_true', help='elimina borderò e ordini della company di revisione e li ricrea da oggi'
  )
  parser.add_argument('--dry-run', action='store_true', help='stampa cosa farebbe senza scrivere')
  options = parser.parse_args(argv)
  if options.days < 1 or options.past_days < 0:
    parser.error('--days deve essere almeno 1 e --past-days non negativo')
  return options


def main(argv=None) -> int:
  options = parse_args(argv)
  set_database(os.environ['DATABASE_URL'])
  try:
    summary = run(options)
  except ReviewAccountError as error:
    print(f'Errore: {error}')
    return 1

  if summary['dry_run']:
    return 0

  print(f'Company "{options.company_name}" (id {summary["company_id"]}).')
  if summary['removed']['schedules'] or summary['removed']['orders']:
    print(f'Eliminati {summary["removed"]["schedules"]} borderò e {summary["removed"]["orders"]} ordini.')
  print(f'Borderò creati: {summary["created_days"]}.')
  print(f'Corriere: {options.nickname}')
  if summary['password']:
    print(f'Password (generata, la vedi solo ora): {summary["password"]}')
  elif summary.get('password_set'):
    print('Password: impostata con quella che hai passato.')
  else:
    print("Password: invariata (gia' impostata in precedenza).")
  return 0


if __name__ == '__main__':
  sys.exit(main())

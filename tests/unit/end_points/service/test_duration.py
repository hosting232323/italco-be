from datetime import date, time, timedelta
from unittest.mock import patch

import requests
from sqlalchemy.orm import joinedload

from database_api import Session
from src.database.schema import DeliveryCoverageCap, DeliveryCoverageEntry, Order
from src.end_points.service.duration import (
  PICKUP_POINT_MINUTES_PER_PRODUCT,
  calculate_order_pickup_minutes,
  calculate_orders_pickup_minutes,
  calculate_payload_pickup_minutes,
  entry_front_slot_minutes,
  entry_lead_minutes,
  entry_occupied_duration,
  is_first_entry_of_day,
  order_pickup_collection_point_ids,
  payload_pickup_collection_point_ids,
  query_entry_orders,
)

from database_api.operations import create

from tests.unit.factories import (
  create_collection_point,
  create_order,
  create_product_row,
  create_transport,
  customer_with_service,
)


def _entry(transport, day_of_week=0, start='08:00:00', end='09:00:00', caps=('70051',)):
  entry = create(
    DeliveryCoverageEntry,
    {
      'day_of_week': day_of_week,
      'transport_id': transport.id,
      'start_time': time.fromisoformat(start),
      'end_time': time.fromisoformat(end),
    },
  )
  for cap in caps:
    create(DeliveryCoverageCap, {'entry_id': entry.id, 'cap': cap})
  # query_entry_orders/query_slot_orders leggono entry.caps in lazy-load: l'oggetto
  # tornato da create() è scollegato dalla sessione (stessa cosa in delivery_coverage.py,
  # get_entry_dict/query_entries), quindi va riletto con i caps precaricati.
  with Session() as session:
    return (
      session.query(DeliveryCoverageEntry)
      .options(joinedload(DeliveryCoverageEntry.caps))
      .filter(DeliveryCoverageEntry.id == entry.id)
      .one()
    )


def _with_products(order):
  # order_pickup_collection_point_ids/calculate_order_pickup_minutes leggono
  # order.product in lazy-load: create_order() torna un oggetto scollegato dalla
  # sessione, va riletto con i prodotti precaricati (stessa forma di query_slot_orders).
  with Session() as session:
    return session.query(Order).options(joinedload(Order.product)).filter(Order.id == order.id).one()


def test_order_pickup_collection_point_ids_ignores_products_without_one(db):
  customer, service, service_user, collection_point = customer_with_service()
  order = create_order()
  create_product_row(order, service_user, name='Con ritiro', collection_point_id=collection_point.id)
  create_product_row(order, service_user, name='Senza ritiro')

  assert order_pickup_collection_point_ids(_with_products(order)) == [collection_point.id]


def test_calculate_order_pickup_minutes_counts_n_times_number_of_products(db):
  customer, service, service_user, collection_point = customer_with_service()
  other_point = create_collection_point(customer)
  order = create_order()
  create_product_row(order, service_user, name='P1', collection_point_id=collection_point.id)
  create_product_row(order, service_user, name='P2', collection_point_id=other_point.id)

  assert calculate_order_pickup_minutes(_with_products(order)) == 2 * PICKUP_POINT_MINUTES_PER_PRODUCT


def test_calculate_order_pickup_minutes_excludes_already_seen_collection_points(db):
  customer, service, service_user, collection_point = customer_with_service()
  order = create_order()
  create_product_row(order, service_user, collection_point_id=collection_point.id)

  order = _with_products(order)
  assert calculate_order_pickup_minutes(order, exclude_collection_point_ids={collection_point.id}) == 0


def test_calculate_orders_pickup_minutes_dedupes_shared_collection_point(db):
  customer, service, service_user, collection_point = customer_with_service()
  first_order = create_order()
  create_product_row(first_order, service_user, collection_point_id=collection_point.id)
  second_order = create_order()
  create_product_row(second_order, service_user, collection_point_id=collection_point.id)

  # Stesso punto di ritiro sui due ordini: contato una volta sola, non due.
  orders = [_with_products(first_order), _with_products(second_order)]
  assert calculate_orders_pickup_minutes(orders) == PICKUP_POINT_MINUTES_PER_PRODUCT


def test_calculate_orders_pickup_minutes_counts_distinct_points_separately(db):
  customer, service, service_user, collection_point = customer_with_service()
  other_point = create_collection_point(customer)
  first_order = create_order()
  create_product_row(first_order, service_user, collection_point_id=collection_point.id)
  second_order = create_order()
  create_product_row(second_order, service_user, collection_point_id=other_point.id)

  orders = [_with_products(first_order), _with_products(second_order)]
  assert calculate_orders_pickup_minutes(orders) == 2 * PICKUP_POINT_MINUTES_PER_PRODUCT


def test_entry_occupied_duration_includes_pickup_point_time(db):
  target = date.today() + timedelta(days=3)
  customer, service, service_user, collection_point = customer_with_service()
  entry = _entry(create_transport(), day_of_week=target.weekday())
  order = create_order(cap='70051', dpc=target, delivery_slot_start=entry.start_time, delivery_slot_end=entry.end_time)
  create_product_row(order, service_user, collection_point_id=collection_point.id)

  assert entry_occupied_duration(entry, target) == PICKUP_POINT_MINUTES_PER_PRODUCT


def test_entry_occupied_duration_dedupes_pickup_point_shared_between_orders(db):
  target = date.today() + timedelta(days=3)
  customer, service, service_user, collection_point = customer_with_service()
  entry = _entry(create_transport(), day_of_week=target.weekday())
  for _ in range(2):
    order = create_order(
      cap='70051', dpc=target, delivery_slot_start=entry.start_time, delivery_slot_end=entry.end_time
    )
    create_product_row(order, service_user, collection_point_id=collection_point.id)

  # Due ordini sullo stesso punto di ritiro nella stessa fascia: contato una volta sola.
  assert entry_occupied_duration(entry, target) == PICKUP_POINT_MINUTES_PER_PRODUCT


def test_payload_pickup_collection_point_ids_ignores_non_dict_payload():
  assert payload_pickup_collection_point_ids(None) == []
  assert payload_pickup_collection_point_ids('not a dict') == []


def test_payload_pickup_collection_point_ids_ignores_products_without_collection_point():
  products = {'Frigo': {'services': [{'id': 1}]}, 'Lavatrice': 'not a dict'}
  assert payload_pickup_collection_point_ids(products) == []


def test_calculate_payload_pickup_minutes_counts_n_times_number_of_products():
  products = {'Frigo': {'collection_point': {'id': 1}}, 'TV': {'collection_point': {'id': 2}}}
  assert calculate_payload_pickup_minutes(products) == 2 * PICKUP_POINT_MINUTES_PER_PRODUCT


def test_calculate_payload_pickup_minutes_excludes_already_seen_collection_points():
  products = {'Frigo': {'collection_point': {'id': 1}}}
  assert calculate_payload_pickup_minutes(products, exclude_collection_point_ids={1}) == 0


def test_query_entry_orders_reuses_vehicle_already_covering_the_same_pickup_point(db):
  """Fasce sovrapposte (stesso giorno/orario, veicoli diversi): un ordine con un punto

  di ritiro già presente sul veicolo a cui è stato assegnato un altro ordine resta lì
  a costo marginale zero, invece di far scattare il passaggio al veicolo successivo
  (criterio di base della gestione delle fasce sovrapposte)."""
  target = date.today() + timedelta(days=3)
  _, _, service_user_full, _ = customer_with_service(duration=60)
  _, _, service_user_zero, point_a = customer_with_service()

  first_vehicle = create_transport()
  second_vehicle = create_transport()
  first_entry = _entry(first_vehicle, day_of_week=target.weekday(), caps=('70051',))
  second_entry = _entry(second_vehicle, day_of_week=target.weekday(), caps=('70051',))

  # Riempie il primo veicolo con un ordine puramente di servizio (60/60 min, nessun ritiro).
  order_fill = create_order(
    cap='70051', dpc=target, delivery_slot_start=first_entry.start_time, delivery_slot_end=first_entry.end_time
  )
  create_product_row(order_fill, service_user_full, name='Servizio pieno')

  # Primo ordine sul punto A: il primo veicolo è pieno, va sul secondo.
  order_point_a_1 = create_order(
    cap='70051', dpc=target, delivery_slot_start=first_entry.start_time, delivery_slot_end=first_entry.end_time
  )
  create_product_row(order_point_a_1, service_user_zero, name='Ritiro A (1)', collection_point_id=point_a.id)

  # Secondo ordine sullo STESSO punto A: il primo veicolo resta pieno, ma il punto A è
  # già presente sul secondo veicolo (per via di order_point_a_1): ci resta a costo zero.
  order_point_a_2 = create_order(
    cap='70051', dpc=target, delivery_slot_start=first_entry.start_time, delivery_slot_end=first_entry.end_time
  )
  create_product_row(order_point_a_2, service_user_zero, name='Ritiro A (2)', collection_point_id=point_a.id)

  # Order non ha __eq__ per valore (identità di default): il confronto è per id, gli
  # oggetti tornano da una query fresca e non sono le stesse istanze Python create sopra.
  assert [order.id for order in query_entry_orders(first_entry, target)] == [order_fill.id]
  assert [order.id for order in query_entry_orders(second_entry, target)] == [
    order_point_a_1.id,
    order_point_a_2.id,
  ]
  # Punto di ritiro condiviso da entrambi gli ordini del secondo veicolo: contato una volta sola.
  assert entry_occupied_duration(second_entry, target) == PICKUP_POINT_MINUTES_PER_PRODUCT


# ---------------------------------------------------------------------------
# Tratta di avvicinamento: dal punto in cui si trova il veicolo alla prima tappa
# ---------------------------------------------------------------------------

BARI = (41.1171, 16.8719)
MOLFETTA = (41.2007, 16.5992)
BISCEGLIE = (41.2428, 16.5053)


def _entry_with_orders(transport, target, day_offset=0, start='08:00:00', end='12:00:00'):
  """Una fascia del veicolo con un ordine dentro, con punto di ritiro."""
  customer, service, service_user, collection_point = customer_with_service()
  entry = _entry(transport, day_of_week=target.weekday(), start=start, end=end)
  order = create_order(cap='70051', dpc=target, delivery_slot_start=entry.start_time, delivery_slot_end=entry.end_time)
  create_product_row(order, service_user, collection_point_id=collection_point.id)
  return entry


def test_is_first_entry_of_day_looks_at_the_same_vehicle_and_day(db):
  transport = create_transport()
  morning = _entry(transport, day_of_week=1, start='08:00:00', end='12:00:00')
  afternoon = _entry(transport, day_of_week=1, start='14:00:00', end='18:00:00')
  # Stessa ora ma su un altro veicolo: non e' la stessa giornata lavorativa.
  other_vehicle = _entry(create_transport(), day_of_week=1, start='06:00:00', end='07:00:00')

  with Session() as session:
    assert is_first_entry_of_day(morning, session) is True
    assert is_first_entry_of_day(afternoon, session) is False
    assert is_first_entry_of_day(other_vehicle, session) is True


def test_is_first_entry_of_day_ignores_other_days_of_the_week(db):
  transport = create_transport()
  monday = _entry(transport, day_of_week=0, start='14:00:00', end='18:00:00')
  _entry(transport, day_of_week=1, start='06:00:00', end='07:00:00')

  with Session() as session:
    # Il lunedì resta la prima fascia del lunedì: il martedì non c'entra.
    assert is_first_entry_of_day(monday, session) is True


@patch('src.end_points.service.travel.sequential_travel_minutes', return_value=25)
@patch('src.end_points.service.travel.get_lat_lon_by_address')
def test_entry_occupied_duration_counts_the_drive_from_the_vehicle(mock_geocode, _mock_travel, db):
  mock_geocode.side_effect = lambda address: BISCEGLIE if 'Deposito' in address else MOLFETTA
  target = date.today() + timedelta(days=3)
  transport = create_transport(address='Via Deposito 1, Bisceglie', cap='76011')
  entry = _entry_with_orders(transport, target)

  # Servizi (0) + ritiro (N) + avvicinamento del veicolo alla prima tappa (25).
  assert entry_occupied_duration(entry, target) == PICKUP_POINT_MINUTES_PER_PRODUCT + 25


@patch('src.end_points.service.travel.sequential_travel_minutes', return_value=25)
@patch('src.end_points.service.travel.get_lat_lon_by_address')
def test_entry_occupied_duration_skips_the_drive_for_later_slots(mock_geocode, _mock_travel, db):
  """Nelle fasce successive il veicolo e' gia' in giro: non riparte dal deposito."""
  mock_geocode.side_effect = lambda address: BISCEGLIE if 'Deposito' in address else MOLFETTA
  target = date.today() + timedelta(days=3)
  transport = create_transport(address='Via Deposito 1, Bisceglie', cap='76011')
  _entry(transport, day_of_week=target.weekday(), start='06:00:00', end='07:00:00')
  entry = _entry_with_orders(transport, target)

  assert entry_occupied_duration(entry, target) == PICKUP_POINT_MINUTES_PER_PRODUCT


@patch('src.end_points.service.travel.sequential_travel_minutes', return_value=25)
def test_entry_occupied_duration_without_a_vehicle_location_is_unchanged(_mock_travel, db):
  """Veicolo senza indirizzo ne' CAP: si ripiega sul comportamento di prima."""
  target = date.today() + timedelta(days=3)
  entry = _entry_with_orders(create_transport(), target)

  assert entry_occupied_duration(entry, target) == PICKUP_POINT_MINUTES_PER_PRODUCT


@patch('src.end_points.service.travel.sequential_travel_minutes', return_value=25)
@patch('src.end_points.service.travel.get_lat_lon_by_address')
def test_entry_occupied_duration_drive_is_counted_once_not_per_order(mock_geocode, _mock_travel, db):
  """La tratta di avvicinamento e' una sola: il veicolo parte una volta al giorno."""
  mock_geocode.side_effect = lambda address: BISCEGLIE if 'Deposito' in address else MOLFETTA
  target = date.today() + timedelta(days=3)
  transport = create_transport(address='Via Deposito 1, Bisceglie', cap='76011')
  customer, service, service_user, collection_point = customer_with_service()
  entry = _entry(transport, day_of_week=target.weekday(), start='08:00:00', end='12:00:00')
  for _ in range(3):
    order = create_order(
      cap='70051', dpc=target, delivery_slot_start=entry.start_time, delivery_slot_end=entry.end_time
    )
    create_product_row(order, service_user, collection_point_id=collection_point.id)

  assert entry_occupied_duration(entry, target) == PICKUP_POINT_MINUTES_PER_PRODUCT + 25


# ---------------------------------------------------------------------------
# Margine tra l'apertura dell'attivita' e l'inizio della fascia
# ---------------------------------------------------------------------------

_FRONT = 'src.end_points.service.duration'


def _front_slot(pickup_minutes, *, route, lead, first=True):
  """entry_front_slot_minutes con strada, margine e "prima fascia" fissati: prova l'aritmetica pura."""
  with (
    patch(f'{_FRONT}.is_first_entry_of_day', return_value=first),
    patch(f'{_FRONT}.entry_front_route_minutes', return_value=route),
    patch(f'{_FRONT}.entry_lead_minutes', return_value=lead),
  ):
    return entry_front_slot_minutes(object(), [], pickup_minutes, object())


def test_front_slot_is_free_when_the_work_fits_in_the_lead_window():
  # Apre alle 9, la fascia parte alle 10: 60 minuti di margine per 25 di strada e 4 di ritiro.
  assert _front_slot(4, route=25, lead=60) == 0


def test_front_slot_charges_only_what_overflows_the_lead_window():
  # 60 di strada + 15 di ritiro = 75 di lavoro in testa, 60 stanno nel margine: 15 sulla fascia.
  assert _front_slot(15, route=60, lead=60) == 15


def test_front_slot_charges_everything_without_a_lead_window():
  # Senza orario di apertura (o fascia che parte all'apertura) il margine e' zero.
  assert _front_slot(4, route=25, lead=0) == 29


def test_front_slot_never_goes_negative():
  assert _front_slot(0, route=0, lead=120) == 0


def test_front_slot_of_a_later_slot_is_only_the_pickup_minutes():
  # Nelle fasce successive il veicolo e' gia' in giro: niente strada, niente margine.
  assert _front_slot(4, route=25, lead=60, first=False) == 4


def test_entry_lead_minutes_is_the_gap_between_opening_and_slot_start(db):
  from database_api.operations import update

  update(db, {'activity_start_time': time(9, 0)})
  entry = _entry(create_transport(), start='10:00:00', end='12:00:00')

  with Session() as session:
    assert entry_lead_minutes(entry, session) == 60


def test_entry_lead_minutes_is_zero_without_a_company_opening_time(db):
  entry = _entry(create_transport(), start='10:00:00', end='12:00:00')

  with Session() as session:
    assert entry_lead_minutes(entry, session) == 0


def test_entry_lead_minutes_is_zero_when_the_slot_starts_before_opening(db):
  from database_api.operations import update

  update(db, {'activity_start_time': time(11, 0)})
  entry = _entry(create_transport(), start='10:00:00', end='12:00:00')

  with Session() as session:
    assert entry_lead_minutes(entry, session) == 0


@patch('src.end_points.service.travel.sequential_travel_minutes', return_value=25)
@patch('src.end_points.service.travel.get_lat_lon_by_address')
def test_entry_occupied_duration_does_not_charge_the_slot_for_work_done_before_it_starts(mock_geocode, _travel, db):
  from database_api.operations import update

  mock_geocode.side_effect = lambda address: BISCEGLIE if 'Deposito' in address else MOLFETTA
  target = date.today() + timedelta(days=3)
  update(db, {'activity_start_time': time(9, 0)})
  transport = create_transport(address='Via Deposito 1, Bisceglie', cap='76011')
  entry = _entry_with_orders(transport, target, start='10:00:00', end='14:00:00')

  # 25 di strada + 4 di ritiro stanno nell'ora tra l'apertura e la fascia: la fascia resta libera.
  assert entry_occupied_duration(entry, target) == 0


@patch('src.end_points.service.travel.sequential_travel_minutes', return_value=25)
@patch('src.end_points.service.travel.get_lat_lon_by_address')
def test_entry_occupied_duration_charges_the_part_that_does_not_fit_before_the_slot(mock_geocode, _travel, db):
  from database_api.operations import update

  mock_geocode.side_effect = lambda address: BISCEGLIE if 'Deposito' in address else MOLFETTA
  target = date.today() + timedelta(days=3)
  # Apre alle 9:45, la fascia parte alle 10: solo 15 minuti di margine per 29 di lavoro in testa.
  update(db, {'activity_start_time': time(9, 45)})
  transport = create_transport(address='Via Deposito 1, Bisceglie', cap='76011')
  entry = _entry_with_orders(transport, target, start='10:00:00', end='14:00:00')

  assert entry_occupied_duration(entry, target) == 25 + PICKUP_POINT_MINUTES_PER_PRODUCT - 15


@patch('src.end_points.service.travel.get_lat_lon_by_address', side_effect=requests.ConnectionError('giu'))
def test_entry_occupied_duration_survives_an_unreachable_geocoder(_geocode, db):
  """Il geocoder giu' non deve bloccare la prenotazione: la strada in testa vale zero."""
  target = date.today() + timedelta(days=3)
  transport = create_transport(address='Via Deposito 1, Bisceglie', cap='76011')
  entry = _entry_with_orders(transport, target)

  assert entry_occupied_duration(entry, target) == PICKUP_POINT_MINUTES_PER_PRODUCT


# ---------------------------------------------------------------------------
# Collaudo: strada in testa, margine dell'apertura e ripartizione tra veicoli
# ---------------------------------------------------------------------------

DEPOT_ADDRESS = 'Via Deposito 1, Bisceglie'


def _geo_places(geo, minutes=25):
  """Deposito a Bisceglie, ritiri a Molfetta, consegne a Bari; ogni percorso dura `minutes`."""
  geo.places.update({'Deposito': BISCEGLIE, 'Magazzino': MOLFETTA, 'Consegna': BARI, 'Nuova': BARI})
  geo.minutes = minutes


def _vehicle(with_address=True):
  if with_address:
    return create_transport(address=DEPOT_ADDRESS, cap='76011')
  return create_transport()


def test_front_route_without_pickups_is_the_drive_to_the_first_delivery(offline_geo, db):
  _geo_places(offline_geo)
  target = date.today() + timedelta(days=3)
  entry = _entry(_vehicle(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00')
  create_order(cap='70051', dpc=target, delivery_slot_start=entry.start_time, delivery_slot_end=entry.end_time)

  # Nessun ritiro: il veicolo va dritto dal deposito alla consegna.
  assert entry_occupied_duration(entry, target) == 25
  assert offline_geo.paths[-1] == [BISCEGLIE, BARI]


def test_front_route_goes_through_the_pickups_before_the_delivery(offline_geo, db):
  _geo_places(offline_geo)
  target = date.today() + timedelta(days=3)
  entry = _entry_with_orders(_vehicle(), target)

  # Deposito -> ritiro (Molfetta) -> consegna (Bari): una sola chiamata, in quest'ordine.
  entry_occupied_duration(entry, target)
  assert offline_geo.paths[-1] == [BISCEGLIE, MOLFETTA, BARI]


def test_the_new_order_is_a_candidate_for_the_first_delivery(offline_geo, db):
  """Alla creazione del primo ordine la fascia è vuota: la prima consegna è proprio il nuovo ordine."""
  _geo_places(offline_geo)
  target = date.today() + timedelta(days=3)
  entry = _entry(_vehicle(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00')

  occupied = entry_occupied_duration(entry, target, new_cap='70051', new_address='Via Nuova 5, Bari')

  assert occupied == 25
  assert offline_geo.paths[-1] == [BISCEGLIE, BARI]


def test_the_new_order_falls_back_to_its_cap_when_the_address_is_not_found(offline_geo, db):
  _geo_places(offline_geo)
  offline_geo.caps['70051'] = MOLFETTA
  target = date.today() + timedelta(days=3)
  entry = _entry(_vehicle(), day_of_week=target.weekday(), start='08:00:00', end='12:00:00')

  entry_occupied_duration(entry, target, new_cap='70051', new_address='Via Introvabile 99')

  assert offline_geo.paths[-1] == [BISCEGLIE, MOLFETTA]


def test_an_unreachable_geocoder_does_not_block_the_booking(offline_geo, db):
  """Nominatim giù con ordini già nella fascia: la stima degrada, la richiesta non cade."""
  _geo_places(offline_geo)
  target = date.today() + timedelta(days=3)
  entry = _entry_with_orders(_vehicle(), target)
  offline_geo.unreachable = True

  occupied = entry_occupied_duration(entry, target, new_cap='70051', new_address='Via Nuova 5, Bari')

  # Né strada in testa né sovrapprezzo di percorso: restano i minuti di ritiro.
  assert occupied == PICKUP_POINT_MINUTES_PER_PRODUCT


def test_the_lead_window_is_used_only_by_the_first_slot_of_the_vehicle(offline_geo, db):
  from database_api.operations import update

  _geo_places(offline_geo)
  target = date.today() + timedelta(days=3)
  update(db, {'activity_start_time': time(7, 0)})
  vehicle = _vehicle()
  _entry(vehicle, day_of_week=target.weekday(), start='08:00:00', end='09:00:00')
  later = _entry_with_orders(vehicle, target, start='13:00:00', end='17:00:00')

  # Il margine di 6 ore esiste solo per la prima fascia: la seconda non ha strada in
  # testa da assorbire e paga i suoi ritiri per intero.
  assert entry_occupied_duration(later, target) == PICKUP_POINT_MINUTES_PER_PRODUCT


def test_lead_minutes_of_an_entry_without_start_time_is_zero(db):
  from types import SimpleNamespace

  with Session() as session:
    assert entry_lead_minutes(SimpleNamespace(start_time=None, company_id=db.id), session) == 0


def _two_vehicles_two_orders(target):
  """Due veicoli sulla stessa fascia 10-11 e due ordini con un ritiro ciascuno.

  A: 30 min di servizio; B: 20 min. La fascia ne contiene 60.
  """
  first = _entry(_vehicle(), day_of_week=target.weekday(), start='10:00:00', end='11:00:00')
  second = _entry(_vehicle(), day_of_week=target.weekday(), start='10:00:00', end='11:00:00')
  orders = []
  for duration in (30, 20):
    _, _, service_user, collection_point = customer_with_service(duration=duration)
    order = create_order(
      cap='70051', dpc=target, delivery_slot_start=first.start_time, delivery_slot_end=first.end_time
    )
    create_product_row(order, service_user, collection_point_id=collection_point.id)
    orders.append(order)
  return first, second, orders


def test_without_a_lead_window_the_second_order_overflows_to_the_next_vehicle(offline_geo, db):
  _geo_places(offline_geo, minutes=20)
  target = date.today() + timedelta(days=3)
  first, second, (order_a, order_b) = _two_vehicles_two_orders(target)

  # Da solo A ci sta (30 + 20 di strada + ritiro), con B no: 50 di servizio + strada e due ritiri.
  assert [o.id for o in query_entry_orders(first, target)] == [order_a.id]
  assert [o.id for o in query_entry_orders(second, target)] == [order_b.id]


def test_with_a_lead_window_both_orders_stay_on_the_first_vehicle(offline_geo, db):
  """Stesso scenario, ma l'attività apre alle 9: strada e ritiri si fanno prima delle 10."""
  from database_api.operations import update

  _geo_places(offline_geo, minutes=20)
  update(db, {'activity_start_time': time(9, 0)})
  target = date.today() + timedelta(days=3)
  first, second, (order_a, order_b) = _two_vehicles_two_orders(target)

  assert [o.id for o in query_entry_orders(first, target)] == [order_a.id, order_b.id]
  assert query_entry_orders(second, target) == []


def test_overlapping_slots_count_the_pickups_of_the_orders_already_assigned(offline_geo, db):
  """La ripartizione somma i ritiri dell'intero gruppo, non solo quelli del nuovo ordine."""
  _geo_places(offline_geo)
  target = date.today() + timedelta(days=3)
  n = PICKUP_POINT_MINUTES_PER_PRODUCT
  first = _entry(_vehicle(with_address=False), day_of_week=target.weekday(), start='08:00:00', end='09:00:00')
  second = _entry(_vehicle(with_address=False), day_of_week=target.weekday(), start='08:00:00', end='09:00:00')

  customer, _, service_user_a, point_1 = customer_with_service(duration=30)
  _, _, service_user_zero, _ = customer_with_service()
  point_2 = create_collection_point(customer)
  order_a = create_order(
    cap='70051', dpc=target, delivery_slot_start=first.start_time, delivery_slot_end=first.end_time
  )
  create_product_row(order_a, service_user_a, name='A1', collection_point_id=point_1.id)
  create_product_row(order_a, service_user_zero, name='A2', collection_point_id=point_2.id)

  # B pesa quanto basta perché 30 + B + 3 ritiri sfori i 60, ma 30 + B + 1 ritiro no.
  _, _, service_user_b, point_3 = customer_with_service(duration=31 - 3 * n)
  order_b = create_order(
    cap='70051', dpc=target, delivery_slot_start=first.start_time, delivery_slot_end=first.end_time
  )
  create_product_row(order_b, service_user_b, name='B1', collection_point_id=point_3.id)

  assert [o.id for o in query_entry_orders(first, target)] == [order_a.id]
  assert [o.id for o in query_entry_orders(second, target)] == [order_b.id]

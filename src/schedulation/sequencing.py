"""Ordine di visita delle tappe di un giro.

Lo usano sia la pianificazione automatica (``routing.py``, borderò già in DB)
sia le proposte borderò (``schedulation/__init__.py``, tappe ancora da salvare).

Il giro è un percorso aperto che parte da dove si trova il veicolo (il suo
deposito, l'ultima tappa già fatta o l'ultima della fascia prima) e rispetta una
sola regola: un punto di ritiro viene prima delle consegne che ne dipendono.
Non serve che il ritiro stia attaccato alle sue consegne: se un ordine senza
ritiri sta di strada tra il ritiro e la consegna, il giro ci passa.

Le durate di guida tra tutte le tappe si chiedono a OSRM una volta sola (table
service); se OSRM non risponde si stimano dalla distanza in linea d'aria. Sulla
matrice:

- fino a ``_MAX_EXACT_STOPS`` tappe (il caso normale di una fascia) si calcola il
  giro più corto in assoluto, per programmazione dinamica sugli insiemi di tappe
  già visitate (Held-Karp), ammettendo una tappa solo dopo i suoi ritiri;
- oltre, si costruisce il giro in due modi (tappa più vicina tra quelle già
  visitabili; inserimento al minor costo) e li si migliora spostando tratti di
  1-3 tappe (or-opt) e invertendo tratti (2-opt), tenendo solo le mosse che
  accorciano il giro senza portare una consegna prima del suo ritiro.

Tappe nello stesso punto (stesso indirizzo, o stesso CAP quando l'indirizzo non
si geocodifica) distano zero e finiscono quindi una dopo l'altra: ordini della
stessa zona non vengono più spezzati da un'altra zona in mezzo.
"""

from concurrent.futures import ThreadPoolExecutor

from geopy.distance import geodesic

from ..end_points.service.travel import get_lat_lon_by_cap, travel_time_matrix_osrm
from ..utils.caps import get_lat_lon_by_address
from .building import set_schedule_index

Coord = tuple[float, float]

# Velocità con cui si stimano i secondi di guida senza OSRM: serve solo a
# confrontare un giro con un altro, non a promettere orari.
_FALLBACK_SPEED_KMH = 30.0
# Coordinate massime per una richiesta al table service (max-table-size di OSRM):
# oltre si stima in linea d'aria invece di farsi rifiutare la richiesta.
_MAX_OSRM_POINTS = 100
# Il giro esatto costa 2^n * n^2 passi: con 10 tappe sono circa centomila,
# una frazione di secondo. Oltre si passa all'euristica.
_MAX_EXACT_STOPS = 10
# Il miglioramento costa O(n^3) a giro: sopra questa soglia ci si ferma alla
# costruzione, che resta buona. Un borderò ha poche decine di tappe per fascia.
_MAX_IMPROVED_STOPS = 60
_MAX_IMPROVEMENT_ROUNDS = 50
_MAX_MOVED_SEGMENT = 3


# ---------------------------------------------------------------------------
# Coordinate delle tappe
# ---------------------------------------------------------------------------


def stop_coord(address: str | None, cap: str | None, stored: tuple = (None, None)) -> Coord | None:
  """Coordinata di una tappa: quella salvata se c'e', poi l'indirizzo completo se
  geocodificabile, altrimenti il centroide del CAP.

  Il CAP da solo tratterebbe come "vicini" ordini/punti di ritiro distanti
  chilometri ma nello stesso CAP (frequente nei CAP che coprono più comuni o
  zone rurali), falsando l'ordine di visita.
  """
  if stored[0] is not None and stored[1] is not None:
    return stored
  if address:
    lat, lon = get_lat_lon_by_address(address, cap)
    if lat is not None:
      return (lat, lon)
  if not cap:
    return None
  lat, lon = get_lat_lon_by_cap(cap)
  return (lat, lon) if lat is not None else None


def resolve_stop_coords(stops: list[tuple[str | None, str | None, tuple]], max_workers: int = 10) -> list[Coord | None]:
  """``stop_coord`` per ogni ``(indirizzo, cap, coordinate salvate)``, in parallelo."""
  if not stops:
    return []
  with ThreadPoolExecutor(max_workers=min(max_workers, len(stops))) as executor:
    return list(executor.map(lambda stop: stop_coord(*stop), stops))


def duration_matrix(points: list[Coord]) -> list[list[float]]:
  """Secondi di guida tra ogni coppia di ``points``: OSRM, o linea d'aria se non risponde."""
  if len(points) < 2:
    return [[0.0] * len(points) for _ in points]
  matrix = travel_time_matrix_osrm(points) if len(points) <= _MAX_OSRM_POINTS else None
  if matrix:
    return matrix
  return [[geodesic(a, b).kilometers / _FALLBACK_SPEED_KMH * 3600 for b in points] for a in points]


# ---------------------------------------------------------------------------
# Giro sulla matrice
# ---------------------------------------------------------------------------


def route_cost(matrix: list[list[float]], route: list[int], start: int | None = None) -> float:
  """Durata del giro ``route`` (indici della matrice), dal punto ``start`` se c'e'."""
  cost = matrix[start][route[0]] if start is not None and route else 0.0
  return cost + sum(matrix[a][b] for a, b in zip(route, route[1:]))


def respects_precedence(route: list[int], predecessors: dict[int, set[int]]) -> bool:
  position = {stop: index for index, stop in enumerate(route)}
  return all(position[before] < position[stop] for stop, befores in predecessors.items() for before in befores)


def sequence_stops(
  matrix: list[list[float]],
  stops: list[int],
  start: int | None = None,
  predecessors: dict[int, set[int]] = None,
) -> list[int]:
  """Ordine di visita di ``stops`` (indici della matrice) partendo da ``start``.

  ``predecessors[stop]`` sono le tappe da visitare prima di ``stop`` (i ritiri
  di una consegna); quelle fuori da ``stops`` si considerano già fatte. Senza
  ``start`` il giro parte dalla tappa che lo rende più corto.
  """
  stop_set = set(stops)
  predecessors = {
    stop: {before for before in befores if before in stop_set}
    for stop, befores in (predecessors or {}).items()
    if stop in stop_set
  }
  if len(stops) <= 1:
    return list(stops)
  if len(stops) <= _MAX_EXACT_STOPS:
    return _exact_route(matrix, stops, start, predecessors)

  if start is not None:
    nearest = _nearest_neighbour(matrix, stops, start, predecessors)
  else:
    firsts = [stop for stop in stops if not predecessors.get(stop)]
    nearest = min(
      (_nearest_neighbour(matrix, stops, first, predecessors, first_is_stop=True) for first in firsts),
      key=lambda candidate: route_cost(matrix, candidate),
    )
  routes = [nearest, _cheapest_insertion(matrix, stops, start, predecessors)]

  if len(stops) <= _MAX_IMPROVED_STOPS:
    routes = [_improve(matrix, route, start, predecessors) for route in routes]
  return min(routes, key=lambda route: route_cost(matrix, route, start))


def _exact_route(matrix, stops, start, predecessors) -> list[int]:
  """Il giro più corto in assoluto (Held-Karp), con i ritiri prima delle loro consegne.

  ``best[visited][last]`` e' la durata minima per visitare l'insieme di tappe
  ``visited`` (bit per posizione in ``stops``) finendo in ``last``.
  """
  size = len(stops)
  position = {stop: index for index, stop in enumerate(stops)}
  required = [sum(1 << position[before] for before in predecessors.get(stop, ())) for stop in stops]
  infinity = float('inf')
  best = [[infinity] * size for _ in range(1 << size)]
  previous = [[-1] * size for _ in range(1 << size)]

  for index, stop in enumerate(stops):
    if not required[index]:
      best[1 << index][index] = matrix[start][stop] if start is not None else 0.0

  for visited in range(1, 1 << size):
    for last in range(size):
      cost = best[visited][last]
      if cost == infinity:
        continue
      row = matrix[stops[last]]
      for following in range(size):
        bit = 1 << following
        if visited & bit or required[following] & ~visited:
          continue
        candidate = cost + row[stops[following]]
        if candidate < best[visited | bit][following]:
          best[visited | bit][following] = candidate
          previous[visited | bit][following] = last

  visited = (1 << size) - 1
  last = min(range(size), key=lambda index: best[visited][index])
  route = []
  while last != -1:
    route.append(stops[last])
    visited, last = visited & ~(1 << last), previous[visited][last]
  return route[::-1]


def _cheapest_insertion(matrix, stops, start, predecessors) -> list[int]:
  """Giro costruito inserendo ogni volta la tappa (e il punto) che lo allunga meno.

  Una tappa entra solo dopo i suoi ritiri, e mai prima di loro nel giro: le
  consegne che dipendono da lei non ci sono ancora, quindi basta questo.
  """
  route: list[int] = []
  remaining = list(stops)
  while remaining:
    done = set(route)
    choice = None
    for stop in remaining:
      befores = predecessors.get(stop, set())
      if not befores <= done:
        continue
      first_allowed = max((route.index(before) + 1 for before in befores), default=0)
      for at in range(first_allowed, len(route) + 1):
        before = route[at - 1] if at > 0 else start
        after = route[at] if at < len(route) else None
        added = (matrix[before][stop] if before is not None else 0.0) + (
          matrix[stop][after] if after is not None else 0.0
        )
        removed = matrix[before][after] if before is not None and after is not None else 0.0
        if choice is None or added - removed < choice[0]:
          choice = (added - removed, stop, at)
    _delta, stop, at = choice
    route.insert(at, stop)
    remaining.remove(stop)
  return route


def _nearest_neighbour(matrix, stops, start, predecessors, first_is_stop=False) -> list[int]:
  remaining = list(stops)
  route = []
  current = start
  if first_is_stop:
    route.append(start)
    remaining.remove(start)
  while remaining:
    done = set(route)
    available = [stop for stop in remaining if predecessors.get(stop, set()) <= done]
    # A parità di distanza vince la tappa che veniva prima: il risultato non
    # dipende dall'ordine in cui il set restituisce gli elementi.
    following = available[0] if current is None else min(available, key=lambda stop: matrix[current][stop])
    route.append(following)
    remaining.remove(following)
    current = following
  return route


def _improve(matrix, route, start, predecessors) -> list[int]:
  best = route_cost(matrix, route, start)
  for _round in range(_MAX_IMPROVEMENT_ROUNDS):
    improved = False
    for candidate in _neighbour_routes(route):
      cost = route_cost(matrix, candidate, start)
      # Il margine evita di girare a vuoto su mosse che cambiano il costo solo per arrotondamento.
      if cost < best - 1e-6 and respects_precedence(candidate, predecessors):
        route, best, improved = candidate, cost, True
        break
    if not improved:
      break
  return route


def _neighbour_routes(route: list[int]):
  size = len(route)
  # or-opt: il tratto route[i:i+k] si sposta in un altro punto del giro
  for length in range(1, min(_MAX_MOVED_SEGMENT, size - 1) + 1):
    for i in range(size - length + 1):
      segment = route[i : i + length]
      rest = route[:i] + route[i + length :]
      for j in range(len(rest) + 1):
        if j != i:
          yield rest[:j] + segment + rest[j:]
  # 2-opt: il tratto route[i..j] si percorre al contrario
  for i in range(size - 1):
    for j in range(i + 1, size):
      yield route[:i] + route[i : j + 1][::-1] + route[j + 1 :]


# ---------------------------------------------------------------------------
# Tappe delle proposte borderò (dizionari, non ancora salvate)
# ---------------------------------------------------------------------------


def transport_start_coord(transport: dict | None) -> Coord | None:
  """Deposito del veicolo (indirizzo, o CAP se manca), o None se non si sa dov'e'."""
  if not transport or not (transport.get('address') or transport.get('cap')):
    return None
  return stop_coord(transport.get('address'), transport.get('cap'))


def sequence_schedule_items(schedule_items: list[dict], start: Coord | None = None) -> list[dict]:
  """Le tappe di una proposta nell'ordine di visita, con ``index`` rinumerato.

  La proposta (e il borderò che ne nasce) mostra prima i punti di ritiro e poi
  le consegne: si fanno quindi prima tutti i ritiri, nel giro più corto dal
  deposito, poi tutte le consegne, nel giro più corto dall'ultimo ritiro. Le
  tappe senza coordinate restano ai bordi: ritiri in testa, consegne in coda.
  """
  coords = resolve_stop_coords([_item_stop(item) for item in schedule_items])
  located = [index for index, coord in enumerate(coords) if coord is not None]
  offset = 1 if start is not None else 0
  matrix = duration_matrix(([start] if start is not None else []) + [coords[index] for index in located])
  matrix_index = {item_index: offset + position for position, item_index in enumerate(located)}

  pickups = [matrix_index[i] for i in located if schedule_items[i]['operation_type'] == 'CollectionPoint']
  predecessors = {matrix_index[i]: set(pickups) for i in located if schedule_items[i]['operation_type'] == 'Order'}
  route = sequence_stops(matrix, list(matrix_index.values()), 0 if start is not None else None, predecessors)
  item_by_matrix_index = {position: schedule_items[i] for i, position in matrix_index.items()}

  unlocated = [schedule_items[i] for i, coord in enumerate(coords) if coord is None]
  ordered = (
    [item for item in unlocated if item['operation_type'] == 'CollectionPoint']
    + [item_by_matrix_index[position] for position in route]
    + [item for item in unlocated if item['operation_type'] != 'CollectionPoint']
  )
  return [set_schedule_index(item, index) for index, item in enumerate(ordered)]


def _item_stop(item: dict) -> tuple:
  keys = ('address_lat', 'address_lon') if item['operation_type'] == 'Order' else ('lat', 'lon')
  return (item.get('address'), item.get('cap'), (item.get(keys[0]), item.get(keys[1])))

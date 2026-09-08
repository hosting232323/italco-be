"""Orchestrazione della pianificazione AI: prompt -> CLI -> validazione -> gruppi.

La proposta arriva intera dal modello (gruppi di id + corriere per gruppo). Qui
non si costruisce nulla di logistico a partire dal testo libero: si validano gli
id e i vincoli contro i dati di input e, solo se tutto torna, si ricompongono gli
schedule item con lo stesso builder del motore a regole. Qualsiasi scostamento
alza AiPlanningError con il motivo preciso.
"""

import itertools
import logging
from typing import Any

from geopy.distance import geodesic

from ..building import build_schedule_items
from ..clustering_rules.professional_services_limit import MAX_PROFESSIONAL_ORDERS
from .caps import order_coordinates
from .cli import ClaudeCliError, run_claude
from .prompt import RESPONSE_JSON_SCHEMA, SYSTEM_PROMPT, build_user_prompt, parse_response


logger = logging.getLogger('italco.schedulation.ai')


class AiPlanningError(RuntimeError):
  """La proposta del modello non e' utilizzabile (chiamata fallita o non valida)."""


# Anche con --json-schema il modello puo' concludere con un testo libero
# invece che con l'output strutturato (osservato in prova): la CLI in quel
# caso non segnala errore, restituisce solo una risposta non interpretabile.
# Un paio di ritentativi assorbono la parte stocastica senza mascherare un
# problema persistente (CLI irraggiungibile, vincoli infattibili, ecc.), che
# dopo MAX_ATTEMPTS torna comunque come AiPlanningError.
MAX_ATTEMPTS = 3


def ai_execute_schedulation(
  orders: list[dict[str, Any]],
  delivery_users: list[dict[str, Any]],
  transports: list[dict[str, Any]],
  context: Any,
) -> list[dict[str, Any]]:
  logger.info(
    'pianificazione AI: %d ordini, %d corrieri, vincoli min=%d max=%d distanza=%dkm',
    len(orders),
    len(delivery_users),
    context.min_size_group,
    context.max_size_group,
    context.max_distance_km,
  )
  prompt = build_user_prompt(orders, delivery_users, context, max_professional_orders=MAX_PROFESSIONAL_ORDERS)

  groups = None
  last_error: AiPlanningError | None = None
  for attempt in range(1, MAX_ATTEMPTS + 1):
    try:
      raw = run_claude(prompt, system=SYSTEM_PROMPT, json_schema=RESPONSE_JSON_SCHEMA)
    except ClaudeCliError as error:
      raise AiPlanningError(f'Chiamata al modello fallita: {error}') from error

    try:
      groups = _validated_groups(parse_response(raw), orders, delivery_users, context)
      break
    except (ValueError, AiPlanningError) as error:
      last_error = error if isinstance(error, AiPlanningError) else AiPlanningError(str(error))
      logger.warning(
        "tentativo %d/%d: proposta non utilizzabile (%s) - %s",
        attempt,
        MAX_ATTEMPTS,
        last_error,
        'ritento' if attempt < MAX_ATTEMPTS else 'rinuncio',
      )

  if groups is None:
    raise last_error

  logger.info('proposta accettata: %d gruppi', len(groups))
  orders_by_id = {order['id']: order for order in orders}
  users_by_id = {user['id']: user for user in delivery_users}

  return [
    {
      'schedule_items': build_schedule_items([orders_by_id[order_id] for order_id in group['order_ids']]),
      'delivery_users': [users_by_id[group['delivery_user_id']]] if group['delivery_user_id'] is not None else [],
      'transports': [],
    }
    for group in groups
  ]


def _validated_groups(
  response: dict[str, Any],
  orders: list[dict[str, Any]],
  delivery_users: list[dict[str, Any]],
  context: Any,
) -> list[dict[str, Any]]:
  raw_groups = response.get('groups')
  if not isinstance(raw_groups, list) or not raw_groups:
    raise AiPlanningError('Il modello non ha restituito alcun gruppo')

  input_ids = {order['id'] for order in orders}
  known_user_ids = {user['id'] for user in delivery_users}
  seen_ids: set[int] = set()
  used_user_ids: set[int] = set()
  groups: list[dict[str, Any]] = []

  for position, raw_group in enumerate(raw_groups, start=1):
    order_ids = raw_group.get('order_ids') if isinstance(raw_group, dict) else None
    if not isinstance(order_ids, list) or not order_ids:
      raise AiPlanningError(f'Gruppo {position}: order_ids mancante o vuoto')
    order_ids = [int(order_id) for order_id in order_ids]

    unknown = [order_id for order_id in order_ids if order_id not in input_ids]
    if unknown:
      raise AiPlanningError(f'Gruppo {position}: id ordine inesistenti {unknown}')
    repeated = [order_id for order_id in order_ids if order_id in seen_ids]
    if repeated:
      raise AiPlanningError(f"Gruppo {position}: id ordine gia' assegnati altrove {repeated}")
    seen_ids.update(order_ids)

    if not context.min_size_group <= len(order_ids) <= context.max_size_group:
      raise AiPlanningError(
        f'Gruppo {position}: {len(order_ids)} ordini fuori dai limiti '
        f'[{context.min_size_group}, {context.max_size_group}]'
      )

    professional = sum(1 for order_id in order_ids if _is_professional(orders, order_id))
    if professional > MAX_PROFESSIONAL_ORDERS:
      raise AiPlanningError(
        f'Gruppo {position}: {professional} ordini professionali (limite {MAX_PROFESSIONAL_ORDERS})'
      )

    over = _max_pairwise_distance_km(orders, order_ids)
    if over is not None and over > context.max_distance_km:
      raise AiPlanningError(
        f'Gruppo {position}: distanza interna {over:.1f} km oltre il limite di {context.max_distance_km} km'
      )

    delivery_user_id = raw_group.get('delivery_user_id')
    if delivery_user_id is not None:
      delivery_user_id = int(delivery_user_id)
      if delivery_user_id not in known_user_ids:
        raise AiPlanningError(f'Gruppo {position}: corriere {delivery_user_id} non tra quelli disponibili')
      if delivery_user_id in used_user_ids:
        raise AiPlanningError(f"Gruppo {position}: corriere {delivery_user_id} gia' assegnato a un altro gruppo")
      used_user_ids.add(delivery_user_id)

    groups.append({'order_ids': order_ids, 'delivery_user_id': delivery_user_id})

  missing = input_ids - seen_ids
  if missing:
    raise AiPlanningError(f'Ordini non pianificati dal modello: {sorted(missing)}')
  return groups


def _is_professional(orders: list[dict[str, Any]], order_id: int) -> bool:
  order = next(order for order in orders if order['id'] == order_id)
  for product in order.get('products', {}).values():
    for service in product.get('services', []) or []:
      if isinstance(service, dict) and service.get('professional'):
        return True
  return False


def _max_pairwise_distance_km(orders: list[dict[str, Any]], order_ids: list[int]) -> float | None:
  by_id = {order['id']: order for order in orders}
  coords = []
  for order_id in order_ids:
    lat, lon = order_coordinates(by_id[order_id])
    if lat is not None and lon is not None:
      coords.append((lat, lon))
  if len(coords) < 2:
    return None
  return max(geodesic(a, b).km for a, b in itertools.combinations(coords, 2))

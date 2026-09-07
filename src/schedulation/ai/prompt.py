"""Costruzione del prompt e parsing della risposta per la pianificazione AI.

Il modello vede un payload compatto (un ordine = poche chiavi) e deve rispondere
SOLO con un oggetto JSON che partiziona gli id ordine in gruppi e assegna a
ciascun gruppo un corriere. Non gli si chiede di costruire gli schedule item:
quelli li ricompone il codice a partire dagli id, cosi' la superficie da
validare resta minima.
"""

import json
from typing import Any

from .caps import order_coordinates


SYSTEM_PROMPT = (
  'Sei un pianificatore logistico. Ricevi ordini di consegna/ritiro di una '
  'singola giornata, i corrieri disponibili e dei vincoli numerici. Devi '
  'raggruppare gli ordini in borderò e assegnare a ogni borderò al più un '
  'corriere.\n'
  'Regole:\n'
  '- ogni id ordine ricevuto deve finire in esattamente un gruppo; non '
  'inventare id.\n'
  '- rispetta min_size_group e max_size_group sul numero di ordini per gruppo.\n'
  '- al massimo max_professional_orders ordini professionali per gruppo.\n'
  '- tieni vicini gli ordini con CAP uguali o limitrofi; non mettere nello '
  'stesso gruppo ordini a più di max_distance_km di distanza stimata.\n'
  '- un corriere può stare in un solo gruppo; se non sei sicuro lascia '
  'delivery_user_id a null.\n'
  'Rispondi con SOLO un oggetto JSON valido, senza testo attorno, in questa '
  'forma:\n'
  '{"groups": [{"order_ids": [int], "delivery_user_id": int|null, "reason": '
  '"stringa breve"}]}'
)


def build_user_prompt(
  orders: list[dict[str, Any]],
  delivery_users: list[dict[str, Any]],
  context: Any,
  *,
  max_professional_orders: int,
) -> str:
  payload = {
    'constraints': {
      'min_size_group': context.min_size_group,
      'max_size_group': context.max_size_group,
      'max_distance_km': context.max_distance_km,
      'max_professional_orders': max_professional_orders,
    },
    'delivery_users': [_delivery_user_view(user) for user in delivery_users],
    'orders': [_order_view(order) for order in orders],
  }
  return json.dumps(payload, ensure_ascii=False, default=str)


def parse_response(raw: str) -> dict[str, Any]:
  """Estrae l'oggetto JSON dalla risposta, tollerando fence e testo attorno."""
  candidate = raw.strip()
  if candidate.startswith('```'):
    candidate = candidate.split('```', 2)[1]
    if candidate.startswith('json'):
      candidate = candidate[4:]
    candidate = candidate.strip()

  try:
    return json.loads(candidate)
  except json.JSONDecodeError:
    pass

  start = candidate.find('{')
  end = candidate.rfind('}')
  if start != -1 and end > start:
    try:
      return json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
      pass
  raise ValueError(f'Risposta del modello non contiene JSON valido: {raw[:500]}')


def _order_view(order: dict[str, Any]) -> dict[str, Any]:
  lat, lon = order_coordinates(order)
  return {
    'id': order['id'],
    'type': order.get('type'),
    'status': order.get('status'),
    'cap': order.get('cap'),
    'city': order.get('city'),
    'professional': _is_professional(order),
    'lat': lat,
    'lon': lon,
    'collection_point_caps': sorted(
      {
        product['collection_point']['cap']
        for product in order.get('products', {}).values()
        if product.get('collection_point')
      }
    ),
  }


def _delivery_user_view(user: dict[str, Any]) -> dict[str, Any]:
  info = user.get('delivery_user_info') or {}
  return {'id': user['id'], 'nickname': user.get('nickname'), 'cap': info.get('cap')}


def _is_professional(order: dict[str, Any]) -> bool:
  for product in order.get('products', {}).values():
    for service in product.get('services', []) or []:
      if isinstance(service, dict) and service.get('professional'):
        return True
  return False

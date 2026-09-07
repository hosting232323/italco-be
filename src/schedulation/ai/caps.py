"""Coordinate di un ordine, con lo stesso ripiego usato dal motore a regole.

Un ordine puo' non avere CAP, o averne uno assente dalla tabella CAPS_DATA
(get_lat_lon_by_cap solleva): in quei casi si torna (None, None) e i controlli
di distanza a valle semplicemente saltano quell'ordine, come gia' fa il
clustering deterministico per gli ordini senza CAP.
"""

from typing import Any

from ...utils.caps import get_lat_lon_by_cap


def order_coordinates(order: dict[str, Any]) -> tuple[float | None, float | None]:
  cap = order.get('cap')
  if not cap:
    return None, None
  try:
    return get_lat_lon_by_cap(cap)
  except (ValueError, KeyError):
    return None, None

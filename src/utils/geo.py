def point_in_polygon(point: tuple[float, float], polygon: list) -> bool:
  """Ray-casting (even-odd rule): `point` e `polygon` sono coppie [lat, lon].

  Nessuna libreria geometrica in più: i poligoni sono zone di copertura
  disegnate manualmente sulla mappa, non serve gestire self-intersection o
  topologie complesse.
  """
  if not polygon or len(polygon) < 3:
    return False

  lat, lon = point
  inside = False
  n = len(polygon)
  j = n - 1
  for i in range(n):
    lat_i, lon_i = polygon[i]
    lat_j, lon_j = polygon[j]
    intersects = ((lon_i > lon) != (lon_j > lon)) and (lat < (lat_j - lat_i) * (lon - lon_i) / (lon_j - lon_i) + lat_i)
    if intersects:
      inside = not inside
    j = i
  return inside


# Le consegne sono tutte in Italia: una coordinata fuori da qui (o 0,0 di un
# client che manda campi vuoti) non è una posizione, è un dato sporco.
ITALY_BOUNDS = ((35.0, 48.0), (6.0, 19.0))


def parse_coordinates(lat, lon) -> tuple[float, float] | tuple[None, None]:
  """Coordinate inviate dal client, o (None, None) se mancano o non sono plausibili."""
  try:
    lat, lon = float(lat), float(lon)
  except (TypeError, ValueError):
    return None, None
  (min_lat, max_lat), (min_lon, max_lon) = ITALY_BOUNDS
  if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
    return None, None
  return lat, lon

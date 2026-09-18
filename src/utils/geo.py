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

from types import SimpleNamespace
from unittest.mock import patch

from src.schedulation.routing import (
  StopContext,
  _build_clusters,
  _first_coord,
  _order_cluster,
  _osrm_or_original_order,
)


def _item(id):
  return SimpleNamespace(id=id, index=0)


def _order_stop(id, coord=(41.0, 16.0)):
  return StopContext(item=_item(id), kind='order', coord=coord, entity_id=id)


def _cp_stop(id, coord=(41.0, 16.0)):
  return StopContext(item=_item(id), kind='collection_point', coord=coord, entity_id=id)


# ---------------------------------------------------------------------------
# _osrm_or_original_order
# ---------------------------------------------------------------------------


def test_osrm_or_original_order_returns_identity_for_zero_or_one_stop():
  assert _osrm_or_original_order(0, []) == []
  assert _osrm_or_original_order(1, [(1.0, 2.0)]) == [0]


@patch('src.schedulation.routing.trip_order_osrm')
def test_osrm_or_original_order_uses_trip_result(mock_trip):
  mock_trip.return_value = [2, 0, 1]
  coords = [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]

  assert _osrm_or_original_order(3, coords) == [2, 0, 1]
  mock_trip.assert_called_once_with(coords)


@patch('src.schedulation.routing.trip_order_osrm')
def test_osrm_or_original_order_falls_back_when_osrm_unavailable(mock_trip):
  mock_trip.return_value = None

  assert _osrm_or_original_order(3, [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]) == [0, 1, 2]


def test_osrm_or_original_order_falls_back_with_less_than_two_valid_coords():
  assert _osrm_or_original_order(3, [(1.0, 1.0), None, None]) == [0, 1, 2]


@patch('src.schedulation.routing.trip_order_osrm')
def test_osrm_or_original_order_appends_unresolvable_coords_at_the_end(mock_trip):
  # coords[1] non geocodificabile: OSRM vede solo indici 0 e 2, in quest'ordine
  mock_trip.return_value = [1, 0]  # visita prima il secondo valido (indice originale 2), poi il primo (0)
  coords = [(1.0, 1.0), None, (3.0, 3.0)]

  assert _osrm_or_original_order(3, coords) == [2, 0, 1]
  mock_trip.assert_called_once_with([(1.0, 1.0), (3.0, 3.0)])


# ---------------------------------------------------------------------------
# _build_clusters
# ---------------------------------------------------------------------------


def test_build_clusters_keeps_independent_orders_separate():
  order_a, order_b = _order_stop(1), _order_stop(2)

  clusters = _build_clusters([order_a, order_b], [], dependencies={})

  assert len(clusters) == 2
  assert all(cps == [] for cps, _orders in clusters)
  assert {orders[0].entity_id for _cps, orders in clusters} == {1, 2}


def test_build_clusters_groups_order_with_its_required_collection_point():
  order = _order_stop(1)
  cp = _cp_stop(10)

  clusters = _build_clusters([order], [cp], dependencies={order.item.id: {10}})

  assert len(clusters) == 1
  cps, orders = clusters[0]
  assert cps == [cp]
  assert orders == [order]


def test_build_clusters_merges_orders_sharing_the_same_collection_point():
  order_a, order_b = _order_stop(1), _order_stop(2)
  cp = _cp_stop(10)
  dependencies = {order_a.item.id: {10}, order_b.item.id: {10}}

  clusters = _build_clusters([order_a, order_b], [cp], dependencies)

  assert len(clusters) == 1
  cps, orders = clusters[0]
  assert cps == [cp]
  assert {o.entity_id for o in orders} == {1, 2}


def test_build_clusters_ignores_dependency_on_collection_point_not_in_schedule():
  order = _order_stop(1)

  clusters = _build_clusters([order], [], dependencies={order.item.id: {999}})

  assert len(clusters) == 1
  cps, orders = clusters[0]
  assert cps == []
  assert orders == [order]


# ---------------------------------------------------------------------------
# _order_cluster / _first_coord
# ---------------------------------------------------------------------------


def test_order_cluster_puts_collection_points_before_orders():
  # Un solo punto di ritiro e un solo ordine: nessuna chiamata OSRM necessaria
  # (_osrm_or_original_order va in identity per liste di lunghezza <= 1), quindi
  # l'unico comportamento da verificare è la precedenza cps-poi-orders.
  order = _order_stop(1)
  cp = _cp_stop(10)

  sequence = _order_cluster([cp], [order])

  assert sequence == [cp, order]


def test_first_coord_returns_first_non_none_coordinate():
  stops = [_order_stop(1, coord=None), _order_stop(2, coord=(41.0, 16.0)), _order_stop(3, coord=(42.0, 17.0))]

  assert _first_coord(stops) == (41.0, 16.0)


def test_first_coord_returns_none_when_all_unresolvable():
  stops = [_order_stop(1, coord=None), _order_stop(2, coord=None)]

  assert _first_coord(stops) is None

from src.schedulation.building import build_schedule_items
from src.schedulation.clustering_rules import ClusteringContext
from src.schedulation.clustering_rules.professional_services_limit import (
  MAX_PROFESSIONAL_ORDERS,
  ProfessionalServicesLimitRule,
  _count_professional_orders,
  _is_professional_order,
)

from tests.unit.schedulation.conftest import count_orders, count_professional, make_order


PRO = [{'id': 1, 'name': 'Pro', 'professional': True}]
NON_PRO = [{'id': 2, 'name': 'Std', 'professional': False}]


def _group(pro_count, non_pro_count, cap='70020'):
  orders = [make_order(i, cap, collection_point_id=i, services=PRO) for i in range(1, pro_count + 1)] + [
    make_order(100 + i, cap, collection_point_id=100 + i, services=NON_PRO) for i in range(non_pro_count)
  ]
  return build_schedule_items(orders)


def _apply(groups, min_size=1, max_size=10):
  return ProfessionalServicesLimitRule().apply(
    groups, ClusteringContext(min_size_group=min_size, max_size_group=max_size, max_distance_km=500)
  )


def test_is_professional_order_detects_professional_service():
  assert _is_professional_order(make_order(1, '70020', services=PRO)) is True
  assert _is_professional_order(make_order(1, '70020', services=NON_PRO)) is False


def test_count_professional_orders():
  group = _group(pro_count=2, non_pro_count=1)

  assert _count_professional_orders(group) == 2


def test_rule_keeps_group_within_limit():
  group = _group(pro_count=2, non_pro_count=2)

  result = _apply([group], min_size=1, max_size=10)

  assert len(result) == 1
  assert count_professional(result[0]) <= MAX_PROFESSIONAL_ORDERS


def test_rule_splits_when_professional_limit_exceeded():
  group = _group(pro_count=4, non_pro_count=0)

  result = _apply([group], min_size=1, max_size=2)

  assert all(count_professional(sub) <= MAX_PROFESSIONAL_ORDERS for sub in result)
  assert sum(count_orders(sub) for sub in result) == 4


def test_rule_rebalances_uneven_split():
  # Stato post-split sbilanciato [12, 8] (2 pro + 1 pro): con min=9 max=12
  # la regola deve ribilanciare a due gruppi entrambi >= 9.
  big_group = _group(pro_count=2, non_pro_count=10)
  small_group = _group(pro_count=1, non_pro_count=7)
  # ID collection point distinti tra i due gruppi per evitare collisioni
  for item in small_group:
    if item['operation_type'] == 'CollectionPoint':
      item['collection_point_id'] += 1000

  result = _apply([big_group, small_group], min_size=9, max_size=12)

  counts = sorted(count_orders(sub) for sub in result)
  assert len(result) == 2
  assert all(count >= 9 for count in counts)
  assert all(count_professional(sub) <= MAX_PROFESSIONAL_ORDERS for sub in result)


def test_rule_moves_overflow_pro_orders_to_extra_groups():
  # 5 gruppi da 1 pro ciascuno con capacità 2 pro per gruppo: nessun overflow atteso,
  # ma con un solo gruppo di partenza e 5 pro l'overflow diventa gruppi extra.
  group = _group(pro_count=5, non_pro_count=0)

  result = _apply([group], min_size=1, max_size=10)

  assert sum(count_professional(sub) for sub in result) == 5
  assert all(count_professional(sub) <= MAX_PROFESSIONAL_ORDERS for sub in result)

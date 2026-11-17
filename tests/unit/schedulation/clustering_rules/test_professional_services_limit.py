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


def test_rule_keeps_orders_of_the_same_cap_together_when_rebalancing():
  # Due zone da 6 ordini con min=7: il ribilanciamento serve, ma ogni proposta
  # deve restare fatta di ordini consecutivi per CAP, non mescolati alla rinfusa.
  bari = [make_order(i, '70121', collection_point_id=1, services=NON_PRO) for i in range(1, 7)]
  foggia = [make_order(i, '71010', collection_point_id=2, services=NON_PRO) for i in range(7, 13)]
  groups = [build_schedule_items(bari), build_schedule_items(foggia)]

  result = _apply(groups, min_size=7, max_size=12)

  caps_per_group = [{item['cap'] for item in group if item['operation_type'] == 'Order'} for group in result]
  assert caps_per_group == [{'70121'}, {'71010'}]


def test_rule_moves_a_pro_order_to_the_next_proposal_instead_of_a_random_one():
  # Tre professionali nella prima zona: il terzo passa alla proposta successiva.
  first = [make_order(i, '70121', collection_point_id=1, services=PRO) for i in range(1, 4)] + [
    make_order(i, '70121', collection_point_id=1, services=NON_PRO) for i in range(4, 7)
  ]
  second = [make_order(i, '71010', collection_point_id=2, services=NON_PRO) for i in range(7, 13)]

  result = _apply([build_schedule_items(first), build_schedule_items(second)], min_size=1, max_size=12)

  assert [count_orders(group) for group in result] == [6, 6]
  assert all(count_professional(group) <= MAX_PROFESSIONAL_ORDERS for group in result)
  assert sum(count_professional(group) for group in result) == 3

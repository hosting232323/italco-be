from . import ClusteringRule, ScheduleItemGroup, ClusteringContext, ScheduleItem


# Maximum number of professional orders allowed per schedule group
MAX_PROFESSIONAL_ORDERS = 2


class ProfessionalServicesLimitRule(ClusteringRule):
  def apply(
    self,
    schedule_item_groups: list[ScheduleItemGroup],
    context: ClusteringContext,
  ) -> list[ScheduleItemGroup]:
    # Fast path: skip redistribution only when every group already satisfies
    # both the professional-order limit AND the min/max size constraints.
    # If Split left an unbalanced result (e.g. [12, 8] with min=9), the size
    # check will fail and we fall through to rebalance.
    def _order_count(g: ScheduleItemGroup) -> int:
      return sum(1 for item in g if item.get('operation_type') == 'Order')

    if all(
      _count_professional_orders(g) <= MAX_PROFESSIONAL_ORDERS
      and context.min_size_group <= _order_count(g) <= context.max_size_group
      for g in schedule_item_groups
    ):
      return schedule_item_groups

    # Gather all collection points globally (keyed by collection_point_id)
    all_cp = {
      item['collection_point_id']: item
      for g in schedule_item_groups
      for item in g
      if item.get('operation_type') == 'CollectionPoint'
    }

    # Separate all orders globally into professional and non-professional
    all_pro = [
      item
      for g in schedule_item_groups
      for item in g
      if item.get('operation_type') == 'Order' and _is_professional_order(item)
    ]
    all_non_pro = [
      item
      for g in schedule_item_groups
      for item in g
      if item.get('operation_type') == 'Order' and not _is_professional_order(item)
    ]

    n_groups = len(schedule_item_groups)
    max_pro_capacity = n_groups * MAX_PROFESSIONAL_ORDERS

    # Pro orders that fit across the existing groups; any surplus goes to extra groups
    main_pro = all_pro[:max_pro_capacity]
    overflow_pro = all_pro[max_pro_capacity:]

    # Compute balanced sizes for the main groups so that a skewed split
    # (e.g. [12, 8] for 20 orders with max=12) does not survive redistribution.
    main_total = len(main_pro) + len(all_non_pro)
    base = main_total // n_groups
    extra = main_total % n_groups
    group_sizes = [base + (1 if i < extra else 0) for i in range(n_groups)]

    pro_iter = iter(main_pro)
    non_pro_iter = iter(all_non_pro)
    new_groups = []

    for size in group_sizes:
      orders: list[ScheduleItem] = []
      for _ in range(min(MAX_PROFESSIONAL_ORDERS, size)):
        order = next(pro_iter, None)
        if order is None:
          break
        orders.append(order)
      while len(orders) < size:
        order = next(non_pro_iter, None)
        if order is None:
          break
        orders.append(order)
      cp_ids = {
        product.get('collection_point', {}).get('id') for o in orders for product in o.get('products', {}).values()
      }
      cp_items = [all_cp[cp_id] for cp_id in cp_ids if cp_id in all_cp]
      new_groups.append(cp_items + orders)

    # Overflow pro orders that cannot fit in the main groups become extra groups.
    # These may be smaller than min_size_group — that is acceptable.
    for i in range(0, len(overflow_pro), MAX_PROFESSIONAL_ORDERS):
      chunk = overflow_pro[i : i + MAX_PROFESSIONAL_ORDERS]
      cp_ids = {
        product.get('collection_point', {}).get('id') for o in chunk for product in o.get('products', {}).values()
      }
      cp_items = [all_cp[cp_id] for cp_id in cp_ids if cp_id in all_cp]
      new_groups.append(cp_items + chunk)

    return new_groups


def _count_professional_orders(group: ScheduleItemGroup) -> int:
  """Count the number of professional orders in a group."""
  return sum(1 for item in group if item.get('operation_type') == 'Order' and _is_professional_order(item))


def _is_professional_order(item: ScheduleItem) -> bool:
  """Return True if the order has at least one product with a professional service."""
  for product in item.get('products', {}).values():
    for service in product.get('services', []):
      if isinstance(service, dict) and service.get('professional'):
        return True
  return False

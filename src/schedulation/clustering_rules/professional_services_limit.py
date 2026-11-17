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

    # Le nuove proposte si ritagliano come tratti consecutivi di un'unica fila
    # di ordini: i gruppi così come sono (già raggruppati per zona) e, dentro
    # ciascuno, per CAP. Così gli ordini dello stesso CAP restano insieme invece
    # di essere distribuiti tra le proposte nell'ordine in cui capitano.
    all_orders = [
      item
      for g in schedule_item_groups
      for item in sorted(
        (item for item in g if item.get('operation_type') == 'Order'), key=lambda item: item.get('cap') or ''
      )
    ]

    n_groups = len(schedule_item_groups)
    max_pro_capacity = n_groups * MAX_PROFESSIONAL_ORDERS
    pro_count = sum(1 for order in all_orders if _is_professional_order(order))

    # Compute balanced sizes for the main groups so that a skewed split
    # (e.g. [12, 8] for 20 orders with max=12) does not survive redistribution.
    # The pro orders beyond the capacity of the main groups go to extra groups.
    main_total = len(all_orders) - max(0, pro_count - max_pro_capacity)
    base = main_total // n_groups
    extra = main_total % n_groups
    group_sizes = [base + (1 if i < extra else 0) for i in range(n_groups)]

    # Un professionale che troverebbe la proposta già al limite passa alla
    # successiva, che è la più vicina nella fila.
    chunks: list[list[ScheduleItem]] = []
    pending_pro: list[ScheduleItem] = []
    position = 0
    for size in group_sizes:
      orders: list[ScheduleItem] = []
      while pending_pro and len(orders) < size and _count_professional_orders(orders) < MAX_PROFESSIONAL_ORDERS:
        orders.append(pending_pro.pop(0))
      while len(orders) < size and position < len(all_orders):
        order = all_orders[position]
        position += 1
        if _is_professional_order(order) and _count_professional_orders(orders) >= MAX_PROFESSIONAL_ORDERS:
          pending_pro.append(order)
        else:
          orders.append(order)
      chunks.append(orders)

    # Quel che resta sono solo professionali (gli altri entrano sempre). Vanno
    # nella proposta più vicina in fondo alla fila che ne ha ancora posto; se è
    # piena le cede un ordine normale verso la proposta rimasta corta.
    overflow_pro = []
    for order in pending_pro + all_orders[position:]:
      target = next(
        (i for i in reversed(range(len(chunks))) if _count_professional_orders(chunks[i]) < MAX_PROFESSIONAL_ORDERS),
        None,
      )
      if target is not None and len(chunks[target]) >= group_sizes[target]:
        short = next((i for i in range(len(chunks)) if len(chunks[i]) < group_sizes[i]), None)
        moved = next((item for item in reversed(chunks[target]) if not _is_professional_order(item)), None)
        if short is None or moved is None:
          target = None
        else:
          chunks[target].remove(moved)
          chunks[short].append(moved)
      if target is None:
        overflow_pro.append(order)
      else:
        chunks[target].append(order)

    new_groups = [_with_collection_points(orders, all_cp) for orders in chunks if orders]

    # Overflow pro orders that cannot fit in the main groups become extra groups.
    # These may be smaller than min_size_group — that is acceptable.
    for i in range(0, len(overflow_pro), MAX_PROFESSIONAL_ORDERS):
      new_groups.append(_with_collection_points(overflow_pro[i : i + MAX_PROFESSIONAL_ORDERS], all_cp))

    return new_groups


def _with_collection_points(orders: list[ScheduleItem], all_cp: dict[int, ScheduleItem]) -> ScheduleItemGroup:
  """La proposta con i suoi ordini e, davanti, i punti di ritiro che servono a loro."""
  cp_ids = {
    (product.get('collection_point') or {}).get('id') for o in orders for product in o.get('products', {}).values()
  }
  cp_items = [all_cp[cp_id] for cp_id in sorted(cp_id for cp_id in cp_ids if cp_id in all_cp)]
  return cp_items + orders


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

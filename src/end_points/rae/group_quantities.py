from collections import defaultdict
from collections.abc import Iterable


def group_quantities_by_disposal(rows: Iterable[tuple[int, str, int | None]]) -> dict[int, dict[str, int]]:
  quantities: dict[int, dict[str, int]] = defaultdict(dict)
  for disposal_id, group_code, quantity in rows:
    quantities[disposal_id][group_code] = quantities[disposal_id].get(group_code, 0) + (quantity or 0)

  return {disposal_id: dict(sorted(groups.items())) for disposal_id, groups in quantities.items()}

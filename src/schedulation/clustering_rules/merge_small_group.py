from geopy.distance import geodesic

from ...utils.caps import get_lat_lon_by_cap
from . import ClusteringRule, ScheduleItemGroup, ClusteringContext


class MergeSmallGroupsRule(ClusteringRule):
  def apply(
    self,
    schedule_item_groups: list[ScheduleItemGroup],
    context: ClusteringContext,
  ) -> list[ScheduleItemGroup]:
    return merge_small_groups(
      schedule_item_groups,
      context.min_size_group,
      context.max_size_group,
      context.max_distance_km,
    )


def merge_small_groups(schedule_item_groups, min_size_group, max_size_group, max_distance_km):
  small_groups = []
  large_groups = []
  for group in schedule_item_groups:
    length = len([item for item in group if item['operation_type'] == 'Order'])
    if length < min_size_group:
      lat, lon = get_group_centroid(group)
      if lat is not None and lon is not None:
        small_groups.append({'group': group, 'centroid': (lat, lon), 'merged': False, 'length': length})
    else:
      large_groups.append(group)

  merged_groups = []
  for first_index, first_group in enumerate(small_groups):
    if first_group['merged']:
      continue

    first_group['merged'] = True
    for second_index, second_group in enumerate(small_groups):
      if (
        first_index != second_index
        and not second_group['merged']
        and first_group['length'] + second_group['length'] <= max_size_group
        and geodesic(first_group['centroid'], second_group['centroid']).kilometers <= max_distance_km
      ):
        second_group['merged'] = True
        first_group['group'] += second_group['group']
        first_group['length'] += second_group['length']
        lat, lon = get_group_centroid(first_group['group'])
        if lat is not None and lon is not None:
          first_group['centroid'] = (lat, lon)

    merged_groups.append(first_group['group'])
  return large_groups + merged_groups


def get_group_centroid(schedule_items):
  coords = []
  for item in schedule_items:
    lat, lon = get_lat_lon_by_cap(item['cap'])
    if lat is not None and lon is not None:
      coords.append((lat, lon))

  if not coords:
    return None, None

  return sum(lat for lat, lon in coords) / len(coords), sum(lon for lat, lon in coords) / len(coords)

from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Any, Callable, TypeAlias


ScheduleItem: TypeAlias = dict[str, Any]
ScheduleItemGroup: TypeAlias = list[ScheduleItem]
ScheduleItemBuilder: TypeAlias = Callable[[list[dict[str, Any]]], ScheduleItemGroup]


@dataclass(frozen=True, slots=True)
class ClusteringContext:
  min_size_group: int
  max_size_group: int
  max_distance_km: float


class ClusteringRule(ABC):
  @abstractmethod
  def apply(
    self,
    schedule_item_groups: list[ScheduleItemGroup],
    context: ClusteringContext,
  ) -> list[ScheduleItemGroup]:
    raise NotImplementedError

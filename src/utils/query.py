from sqlalchemy import select
from sqlalchemy.orm import Query


def limit_per_entity(query: Query, id_column, limit: int) -> Query:
  ids_subquery = query.with_entities(id_column).group_by(id_column).limit(limit).subquery()
  return query.filter(id_column.in_(select(ids_subquery)))

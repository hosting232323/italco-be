from sqlalchemy import select
from sqlalchemy.orm import Query, InstrumentedAttribute


def limit_per_entity(
  query: Query, id_column: InstrumentedAttribute, limit: int, subquery_order_by: tuple = None
) -> Query:
  ids_query = query.with_entities(id_column).group_by(id_column)
  if subquery_order_by:
    # quando l'order_by esterno usa colonne di tabelle joinate, nella subquery
    # raggruppata vanno passate in forma aggregata (es. func.max)
    ids_query = ids_query.order_by(None).order_by(*subquery_order_by)
  return query.filter(id_column.in_(select(ids_query.limit(limit).subquery())))

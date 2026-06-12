from sqlalchemy.orm import Session
from sqlalchemy import event, inspect

from .enum import OrderStatus
from .schema import Order, History


@event.listens_for(Session, 'before_flush')
def track_order_history(session: Session, flush_context, instances):
  for obj in session.new:
    if isinstance(obj, Order):
      create_history(session, obj, 'status', obj.status if obj.status else OrderStatus.ACQUIRED)
      if obj.confirmed:
        create_history(session, obj, 'confirmed', True)

  for obj in session.dirty:
    if isinstance(obj, Order):
      state = inspect(obj)
      for field in ['status', 'anomaly', 'delay', 'confirmed']:
        if state.attrs[field].history.has_changes():
          create_history(session, obj, field, getattr(obj, field))


def create_history(session: Session, obj, field, value):
  if field == 'status':
    value = value.value

  session.add(
    History(
      order=obj,
      status={
        'type': field,
        'value': value,
      },
    )
  )


@event.listens_for(Order, 'before_update')
def increment_order_version(_mapper, _connection, order: Order):
  order.version = (order.version or 0) + 1

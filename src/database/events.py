from sqlalchemy.orm import Session, with_loader_criteria
from sqlalchemy import event, inspect

from .enum import OrderStatus
from .schema import Order, History, BaseItalcoEntity


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


@event.listens_for(Session, 'do_orm_execute')
def add_company_filter(execute_state):
  # Lettura: ogni SELECT che tocca un'entità con tenant viene ristretta alla company
  # attiva. include_aliases copre join ed eager load, non solo l'entità radice.
  if not execute_state.is_select:
    return

  company_id = execute_state.session.info.get('company_id')
  if not company_id:
    return

  execute_state.statement = execute_state.statement.options(
    with_loader_criteria(BaseItalcoEntity, lambda cls: cls.company_id == company_id, include_aliases=True)
  )


@event.listens_for(Session, 'before_flush')
def set_company_on_insert(session: Session, flush_context, instances):
  # Scrittura: metà simmetrica del filtro. Senza questo timbro ogni insert
  # dovrebbe passare company_id a mano e la prima dimenticanza sarebbe una riga
  # orfana in produzione. Registrato dopo track_order_history così copre anche
  # le History che quel listener aggiunge alla sessione.
  company_id = session.info.get('company_id')
  for obj in session.new:
    if not isinstance(obj, BaseItalcoEntity) or obj.company_id is not None:
      continue

    if company_id:
      obj.company_id = company_id
    elif not obj.__table__.c.company_id.nullable:
      raise RuntimeError(f'Nessuna company attiva: impossibile salvare {type(obj).__name__}')

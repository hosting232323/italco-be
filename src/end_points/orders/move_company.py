"""Passaggio di un ordine a un'altra company.

Un ordine è collegato a entità che vivono dentro la company: cliente (via
ServiceUser), servizi e punti di ritiro. Cambiare solo Order.company_id lascia
quindi un ordine che punta a righe di un'altra attività. Qui l'ordine viene
ricollegato alle entità equivalenti della company di destinazione:

- il cliente si riconosce dalla Ragione Sociale (CustomerUserInfo.company_name);
- il servizio dal nome (e dal tipo) fra quelli abilitati a quel cliente;
- il punto di ritiro da nome e indirizzo, fra quelli di quel cliente.

Niente viene creato in automatico: se manca un equivalente l'ordine non si
sposta e l'esito dice cosa manca. Ordini già in un borderò, con RAEE o con
veicoli assegnati non si spostano, perché quelle entità sono della company.
"""

from database_api import Session, current_scope, scope
from database_api.operations import get_by_id

from ...database.enum import OrderStatus, UserRole
from ...database.schema import (
  Company,
  CollectionPoint,
  CustomerUserInfo,
  History,
  Order,
  Photo,
  Product,
  RaeProduct,
  ScheduleItemOrder,
  Service,
  ServiceUser,
  User,
)
from ...order_integrity import assert_order_service_types, lock_order_service_integrity

# Oltre queste soglie l'ordine ha già una storia operativa (borderò, consegna) che
# appartiene alla company d'origine.
MOVABLE_STATUSES = (OrderStatus.ACQUIRED, OrderStatus.BOOKED)


def _normalize(value: str | None) -> str:
  return ' '.join((value or '').split()).casefold()


def _customer_candidates(target_company_id: int, company_name: str, session) -> list[tuple[User, CustomerUserInfo]]:
  rows = (
    session.query(User, CustomerUserInfo)
    .join(CustomerUserInfo, CustomerUserInfo.user_id == User.id)
    .filter(User.company_id == target_company_id, User.role == UserRole.CUSTOMER)
    .order_by(User.nickname)
    .all()
  )
  return [(user, info) for user, info in rows if _normalize(info.company_name) == _normalize(company_name)]


def plan_order_move(order_id: int, source_company_id: int, target_company_id: int, target_user_id: int | None, session):
  """Calcola il collegamento senza scrivere nulla.

  Va chiamata fuori scope (company_id=None): legge entità di due company.
  Restituisce (piano, mosse): il piano è il dettaglio mostrato all'admin,
  le mosse sono ciò che serve a move_order per applicarlo. Se piano['errors']
  non è vuoto lo spostamento non è possibile.
  """
  errors: list[str] = []
  plan = {
    'order_id': order_id,
    'target_company_id': target_company_id,
    'source_user': None,
    'target_user': None,
    'target_users': [],
    'services': [],
    'collection_points': [],
    'errors': errors,
  }

  order: Order | None = get_by_id(Order, order_id, session=session)
  if not order or order.company_id != source_company_id:
    errors.append('Ordine non trovato')
    return plan, None

  target_company = get_by_id(Company, target_company_id, session=session) if target_company_id else None
  if not target_company:
    errors.append('Company di destinazione non trovata')
    return plan, None
  plan['target_company'] = {'id': target_company.id, 'name': target_company.name}
  if target_company.id == order.company_id:
    errors.append("L'ordine appartiene già a questa company")
    return plan, None

  if order.status not in MOVABLE_STATUSES:
    errors.append('Si può spostare solo un ordine in stato Acquisito o Prenotato')
  if session.query(ScheduleItemOrder.id).filter(ScheduleItemOrder.order_id == order.id).first():
    errors.append("L'ordine è in un borderò: rimuovilo dal borderò prima di spostarlo")
  if session.query(RaeProduct.id).filter(RaeProduct.order_id == order.id).first():
    errors.append("L'ordine ha prodotti RAEE collegati: non può essere spostato")

  products = session.query(Product).filter(Product.order_id == order.id).order_by(Product.id).all()
  if any(product.transport_id or product.release_transport_id for product in products):
    errors.append("I prodotti dell'ordine hanno un veicolo assegnato: non può essere spostato")
  if not products:
    errors.append("L'ordine non ha prodotti")
    return plan, None

  service_rows = {
    service_user.id: (service_user, service)
    for service_user, service in session.query(ServiceUser, Service)
    .join(Service, Service.id == ServiceUser.service_id)
    .filter(ServiceUser.id.in_({product.service_user_id for product in products}))
    .all()
  }
  source_user_ids = {service_user.user_id for service_user, _ in service_rows.values()}
  if len(source_user_ids) != 1:
    errors.append("I prodotti dell'ordine appartengono a clienti diversi")
    return plan, None

  source_user: User = get_by_id(User, source_user_ids.pop(), session=session)
  source_info = session.query(CustomerUserInfo).filter(CustomerUserInfo.user_id == source_user.id).first()
  plan['source_user'] = {
    'id': source_user.id,
    'nickname': source_user.nickname,
    'company_name': source_info.company_name if source_info else None,
  }

  target_user = None
  if target_user_id:
    target_user = get_by_id(User, target_user_id, session=session)
    if not target_user or target_user.company_id != target_company_id or target_user.role != UserRole.CUSTOMER:
      errors.append('Il punto vendita scelto non appartiene alla company di destinazione')
      target_user = None
  elif not source_info or not _normalize(source_info.company_name):
    errors.append(f'Il cliente {source_user.nickname} non ha una Ragione Sociale con cui cercare il punto vendita')
  else:
    candidates = _customer_candidates(target_company_id, source_info.company_name, session)
    plan['target_users'] = [
      {'id': user.id, 'nickname': user.nickname, 'company_name': info.company_name} for user, info in candidates
    ]
    if not candidates:
      errors.append(f'Nessun punto vendita con Ragione Sociale "{source_info.company_name}" in {target_company.name}')
    elif len(candidates) > 1:
      errors.append('Più punti vendita con la stessa Ragione Sociale: scegli quello di destinazione')
    else:
      target_user = candidates[0][0]
  if target_user:
    plan['target_user'] = {'id': target_user.id, 'nickname': target_user.nickname}

  if not target_user:
    return plan, None

  target_service_users = {
    (_normalize(service.name), service.type): service_user
    for service_user, service in session.query(ServiceUser, Service)
    .join(Service, Service.id == ServiceUser.service_id)
    .filter(ServiceUser.user_id == target_user.id)
    .all()
  }
  service_moves = {}
  for service_user, service in service_rows.values():
    target_service_user = target_service_users.get((_normalize(service.name), service.type))
    plan['services'].append(
      {
        'name': service.name,
        'type': service.type.value,
        'target_service_user_id': target_service_user.id if target_service_user else None,
      }
    )
    if target_service_user:
      service_moves[service_user.id] = target_service_user.id
    else:
      errors.append(f'Servizio "{service.name}" non abilitato per {target_user.nickname}')

  target_points = session.query(CollectionPoint).filter(CollectionPoint.user_id == target_user.id).all()
  points_by_key = {(_normalize(point.name), _normalize(point.address)): point for point in target_points}
  point_moves = {}
  source_point_ids = {
    point_id
    for product in products
    for point_id in (product.collection_point_id, product.release_collection_point_id)
    if point_id
  }
  for point in session.query(CollectionPoint).filter(CollectionPoint.id.in_(source_point_ids)).all():
    target_point = points_by_key.get((_normalize(point.name), _normalize(point.address)))
    plan['collection_points'].append(
      {
        'name': point.name,
        'address': point.address,
        'target_collection_point_id': target_point.id if target_point else None,
      }
    )
    if target_point:
      point_moves[point.id] = target_point.id
    else:
      errors.append(f'Punto di ritiro "{point.name}" ({point.address}) assente per {target_user.nickname}')

  return plan, {'order': order, 'products': products, 'services': service_moves, 'points': point_moves}


def _active_company_id() -> int | None:
  return current_scope().get('company_id')


def list_move_targets() -> dict:
  """Company in cui si può spostare un ordine: tutte tranne quella attiva, solo id e nome."""
  # Letta prima di uscire dallo scope: dentro, la company attiva non c'è più.
  active_company_id = _active_company_id()
  with scope(company_id=None), Session() as session:
    companies = session.query(Company).filter(Company.id != active_company_id).order_by(Company.name).all()
    return {'status': 'ok', 'companies': [{'id': company.id, 'name': company.name} for company in companies]}


def preview_order_move(order_id: int, target_company_id: int, target_user_id: int | None = None) -> dict:
  source_company_id = _active_company_id()
  with scope(company_id=None), Session() as session:
    plan, _ = plan_order_move(order_id, source_company_id, target_company_id, target_user_id, session)
  return {'status': 'ok', 'plan': plan}


def move_order(order_id: int, target_company_id: int, target_user_id: int | None = None) -> dict:
  source_company_id = _active_company_id()
  with scope(company_id=None), Session() as session:
    lock_order_service_integrity(session)
    plan, moves = plan_order_move(order_id, source_company_id, target_company_id, target_user_id, session)
    if plan['errors'] or not moves:
      return {
        'status': 'ko',
        'message': plan['errors'][0] if plan['errors'] else 'Spostamento non possibile',
        'plan': plan,
      }

    order: Order = moves['order']
    for product in moves['products']:
      product.company_id = target_company_id
      product.service_user_id = moves['services'][product.service_user_id]
      if product.collection_point_id:
        product.collection_point_id = moves['points'][product.collection_point_id]
      if product.release_collection_point_id:
        product.release_collection_point_id = moves['points'][product.release_collection_point_id]
    for model in (History, Photo):
      for row in session.query(model).filter(model.order_id == order.id).all():
        row.company_id = target_company_id
    order.company_id = target_company_id
    assert_order_service_types(order, session)
    session.commit()
  return {'status': 'ok', 'message': 'Ordine spostato', 'plan': plan}

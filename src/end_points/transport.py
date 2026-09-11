from flask import Blueprint, request
from sqlalchemy import desc

from database_api import Session
from ..database.enum import UserRole
from . import flask_session_authentication
from ..database.schema import Transport, DeliveryUserInfo, User
from database_api.operations import create, delete, get_by_id, update


transport_bp = Blueprint('transport_bp', __name__)


@transport_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_transport(_):
  payload = dict(request.json)
  user_ids = payload.pop('user_ids', None)
  payload.pop('delivery_users', None)
  transport = create(Transport, payload)
  if user_ids is not None:
    sync_transport_users(transport.id, user_ids)
  return {'status': 'ok', 'transport': serialize_transport(get_by_id(Transport, transport.id))}


@transport_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_transport(_, id):
  # Gli utenti restano, tornano solo senza veicolo: stacca prima la FK.
  sync_transport_users(int(id), [])
  delete(get_by_id(Transport, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@transport_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.OPERATOR, UserRole.ADMIN])
def get_transports(_):
  users_by_transport = delivery_users_by_transport()
  return {
    'status': 'ok',
    'transports': [serialize_transport(transport, users_by_transport) for transport in query_transports()],
  }


@transport_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_transport(_, id):
  payload = dict(request.json)
  user_ids = payload.pop('user_ids', None)
  payload.pop('delivery_users', None)
  transport: Transport = get_by_id(Transport, int(id))
  update(transport, payload)
  if user_ids is not None:
    sync_transport_users(transport.id, user_ids)
  return {'status': 'ok', 'transport': serialize_transport(get_by_id(Transport, transport.id))}


def query_transports() -> list[Transport]:
  with Session() as session:
    return session.query(Transport).order_by(desc(Transport.created_at)).all()


def delivery_users_by_transport() -> dict[int, list[dict]]:
  """Utenti delivery assegnati, raggruppati per veicolo, in una query sola."""
  grouped: dict[int, list[dict]] = {}
  with Session() as session:
    rows = (
      session.query(DeliveryUserInfo.transport_id, User.id, User.nickname)
      .join(User, User.id == DeliveryUserInfo.user_id)
      .filter(DeliveryUserInfo.transport_id.isnot(None))
      .all()
    )
  for transport_id, user_id, nickname in rows:
    grouped.setdefault(transport_id, []).append({'id': user_id, 'nickname': nickname})
  return grouped


def serialize_transport(transport: Transport, users_by_transport: dict[int, list[dict]] = None) -> dict:
  if users_by_transport is None:
    users_by_transport = delivery_users_by_transport()
  data = transport.to_dict()
  delivery_users = users_by_transport.get(transport.id, [])
  data['delivery_users'] = delivery_users
  data['user_ids'] = [user['id'] for user in delivery_users]
  return data


def sync_transport_users(transport_id: int, user_ids: list[int]) -> None:
  """Allinea i delivery_user_info al veicolo: un utente un solo veicolo.

  Chi sparisce dalla lista torna senza veicolo (transport_id = NULL); chi
  entra viene spostato qui anche se stava su un altro veicolo. Se l'utente
  non ha ancora una riga info, la si crea.
  """
  target = {int(user_id) for user_id in (user_ids or [])}
  with Session() as session:
    assigned = session.query(DeliveryUserInfo).filter(DeliveryUserInfo.transport_id == transport_id).all()
    for info in assigned:
      if info.user_id not in target:
        info.transport_id = None

    already = {info.user_id for info in assigned}
    for user_id in target - already:
      info = session.query(DeliveryUserInfo).filter(DeliveryUserInfo.user_id == user_id).first()
      if info:
        info.transport_id = transport_id
      else:
        session.add(DeliveryUserInfo(user_id=user_id, transport_id=transport_id))

    session.commit()

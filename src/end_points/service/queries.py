from database_api import Session
from ...database.enum import UserRole
from ...database.schema import Service, ServiceUser, User, Order, Product


def query_services(user: User = None) -> list[tuple[Service, ServiceUser, User]]:
  with Session() as session:
    query = (
      session.query(Service, ServiceUser, User)
      .outerjoin(ServiceUser, ServiceUser.service_id == Service.id)
      .outerjoin(User, User.id == ServiceUser.user_id)
    )
    if user.role == UserRole.CUSTOMER:
      query = query.filter(ServiceUser.user_id == user.id)
    return query.all()


def query_service_user(service_id: int, user_id: int = None) -> list[ServiceUser] | ServiceUser:
  with Session() as session:
    query = session.query(ServiceUser).filter(ServiceUser.service_id == service_id)
    if user_id:
      query = query.filter(ServiceUser.user_id == user_id)
    return query.all() if not user_id else query.first()


def format_query_result(tupla: tuple[Service, ServiceUser, User], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[0].id:
      if tupla[1] and tupla[2]:
        element['users'].append(format_service_user(tupla[1], tupla[2]))
      return list

  output = tupla[0].to_dict()
  output['users'] = []
  if tupla[1] and tupla[2]:
    output['users'].append(format_service_user(tupla[1], tupla[2]))
  list.append(output)
  return list


def format_service_user(service_user: ServiceUser, user: User) -> dict:
  output = service_user.to_dict()
  output['nickname'] = user.nickname
  return output


def query_max_order(services_id) -> list[Service]:
  with Session() as session:
    services_with_max_order = (
      session.query(Service).filter(Service.id.in_(services_id), Service.max_services.isnot(None)).all()
    )
    return services_with_max_order


def query_orders_in_range(services_id, start_date, end_date):
  with Session() as session:
    return (
      session.query(Order)
      .join(Product, Order.id == Product.order_id)
      .join(ServiceUser, ServiceUser.id == Product.service_user_id)
      .join(Service, Service.id == ServiceUser.service_id)
      .filter(Service.id.in_(services_id), Order.dpc >= start_date, Order.dpc <= end_date)
      .all()
    )


def get_service_users(user_id: int) -> list[ServiceUser]:
  with Session() as session:
    return session.query(ServiceUser).filter(ServiceUser.user_id == user_id).all()

import pytest

from src.database.enum import UserRole
from src.database.schema import CustomerGroup, CustomerUserInfo, DeliveryUserInfo
from src.end_points.users.queries import (
  count_user_dependencies,
  format_user_with_info,
  get_user_and_collection_point_by_code,
  get_user_info,
  query_users,
)

from database_api.operations import create

from tests.unit.factories import (
  create_collection_point,
  create_customer_info,
  create_delivery_info,
  create_order,
  create_product,
  create_service,
  create_service_user,
  create_user,
)


def test_query_users_admin_sees_everyone(db):
  admin = create_user(UserRole.ADMIN)
  create_user(UserRole.CUSTOMER)
  create_user(UserRole.DELIVERY)
  create_user(UserRole.OPERATOR)

  assert len(query_users(admin)) == 4


def test_query_users_delivery_sees_only_customers(db):
  delivery = create_user(UserRole.DELIVERY)
  create_user(UserRole.CUSTOMER)
  create_user(UserRole.OPERATOR)

  results = query_users(delivery)

  assert [user.role for user in results] == [UserRole.CUSTOMER]


def test_query_users_operator_sees_customers_and_deliveries(db):
  operator = create_user(UserRole.OPERATOR)
  create_user(UserRole.CUSTOMER)
  create_user(UserRole.DELIVERY)
  create_user(UserRole.ADMIN)

  results = query_users(operator)

  assert {user.role for user in results} == {UserRole.CUSTOMER, UserRole.DELIVERY}


def test_query_users_with_role_filter(db):
  admin = create_user(UserRole.ADMIN)
  create_user(UserRole.CUSTOMER)
  create_user(UserRole.DELIVERY)

  results = query_users(admin, UserRole.CUSTOMER)

  assert [user.role for user in results] == [UserRole.CUSTOMER]


def test_count_user_dependencies_counts_all_relations(db):
  customer = create_user(UserRole.CUSTOMER)
  service_user = create_service_user(customer, create_service())
  create_collection_point(customer)
  create(CustomerGroup, {'name': 'gruppo'})
  order = create_order()
  create_product(order, service_user)

  counts = count_user_dependencies(customer.id)

  assert counts == {
    'serviceUsers': 1,
    'customerRules': 0,
    'collectionPoints': 1,
    'blockedOrders': 1,
  }


def test_format_user_with_info_adds_delivery_info_for_admin(db):
  delivery = create_user(UserRole.DELIVERY)
  create_delivery_info(delivery, cap='70020')

  formatted = format_user_with_info(delivery, UserRole.ADMIN)

  assert formatted['delivery_user_info']['cap'] == '70020'


def test_format_user_with_info_exposes_assigned_transport(db):
  from tests.unit.factories import create_transport

  delivery = create_user(UserRole.DELIVERY)
  transport = create_transport()
  create_delivery_info(delivery, cap='70020', transport_id=transport.id)

  formatted = format_user_with_info(delivery, UserRole.ADMIN)

  assert formatted['delivery_user_info']['transport_id'] == transport.id


def test_format_user_with_info_adds_customer_info_for_operator(db):
  customer = create_user(UserRole.CUSTOMER)
  create_customer_info(customer, city='Bari')

  formatted = format_user_with_info(customer, UserRole.OPERATOR)

  assert formatted['customer_user_info']['city'] == 'Bari'


def test_format_user_with_info_treats_super_admin_as_admin(db):
  # Il super admin che opera in una company deve vedere i dati completi e le
  # info collegate, come un admin: la tabella Punti Vendita ne dipende.
  customer = create_user(UserRole.CUSTOMER)
  create_customer_info(customer, city='Bari', import_code='PV-042')
  delivery = create_user(UserRole.DELIVERY)
  create_delivery_info(delivery, cap='70020')

  formatted_customer = format_user_with_info(customer, UserRole.SUPER_ADMIN)
  formatted_delivery = format_user_with_info(delivery, UserRole.SUPER_ADMIN)

  # dict completo (non il ridotto id/nickname/role dei viewer non-admin)
  assert 'company_id' in formatted_customer
  assert 'password' not in formatted_customer
  assert formatted_customer['customer_user_info']['city'] == 'Bari'
  assert formatted_customer['customer_user_info']['import_code'] == 'PV-042'
  assert formatted_delivery['delivery_user_info']['cap'] == '70020'


def test_format_user_with_info_empty_dict_when_no_info(db):
  delivery = create_user(UserRole.DELIVERY)

  formatted = format_user_with_info(delivery, UserRole.ADMIN)

  assert formatted['delivery_user_info'] == {}


def test_format_user_with_info_no_extra_keys_for_delivery_viewer(db):
  customer = create_user(UserRole.CUSTOMER)

  formatted = format_user_with_info(customer, UserRole.DELIVERY)

  assert 'customer_user_info' not in formatted
  assert 'delivery_user_info' not in formatted


def test_get_user_info_rejects_models_without_user_id(db):
  with pytest.raises(AttributeError, match='user_id'):
    get_user_info(1, CustomerGroup)


def test_get_user_info_returns_matching_record(db):
  delivery = create_user(UserRole.DELIVERY)
  create_delivery_info(delivery, cap='70121')

  info = get_user_info(delivery.id, DeliveryUserInfo)

  assert info.cap == '70121'
  assert get_user_info(delivery.id, CustomerUserInfo) is None


def test_get_user_and_collection_point_by_code(db):
  customer = create_user(UserRole.CUSTOMER)
  create_customer_info(customer, import_code='PV-001')
  collection_point = create_collection_point(customer)

  result = get_user_and_collection_point_by_code('PV-001')

  assert result[0].id == customer.id
  assert result[1].id == collection_point.id


def test_get_user_and_collection_point_by_code_unknown(db):
  assert get_user_and_collection_point_by_code('PV-MISSING') is None

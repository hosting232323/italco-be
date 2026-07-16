from datetime import date, datetime, timedelta

from src.database.enum import RaeStatus, UserRole
from src.end_points.rae.queries import (
  get_disposal_for_export,
  get_disposal_rae_products,
  get_product_and_group,
  get_rae_products_by_order,
  query_count_rae_products,
  query_rae_products,
)

from tests.unit.factories import (
  create_carrier,
  create_collection_center,
  create_disposal,
  create_order,
  create_product,
  create_rae_product,
  create_rae_product_group,
  create_user,
  customer_with_service,
)


def test_query_rae_products_joins_related_entities(db):
  customer, _, _, _ = customer_with_service()
  order = create_order()
  group = create_rae_product_group()
  rae_product = create_rae_product(order, customer, group)

  results = query_rae_products([])

  assert len(results) == 1
  row = results[0]
  assert row[0].id == rae_product.id
  assert row[1].id == group.id
  assert row[2].id == customer.id
  assert row[3].id == order.id
  assert row[4] is None  # nessun borderò
  assert row[5] is None  # nessun documento DTR


def test_query_rae_products_filters_by_status_and_dates(db):
  customer = create_user(UserRole.CUSTOMER)
  emitted = create_rae_product(
    create_order(), customer, status=RaeStatus.EMITTED, dtr_date=date.today(), emission_date=datetime.now()
  )
  create_rae_product(create_order(), customer, status=RaeStatus.GENERATED)

  by_status = query_rae_products([{'model': 'RaeProduct', 'field': 'status', 'value': 'Emitted'}])
  by_range = query_rae_products(
    [
      {
        'model': 'RaeProduct',
        'field': 'dtr_date',
        'value': [
          (date.today() - timedelta(days=1)).strftime('%Y-%m-%d'),
          (date.today() + timedelta(days=1)).strftime('%Y-%m-%d'),
        ],
      }
    ]
  )
  by_emission_day = query_rae_products(
    [{'model': 'RaeProduct', 'field': 'emission_date', 'value': date.today().strftime('%Y-%m-%d')}]
  )
  by_id_list = query_rae_products([{'model': 'RaeProduct', 'field': 'id', 'value': [emitted.id]}])

  for results in (by_status, by_range, by_emission_day, by_id_list):
    assert [row[0].id for row in results] == [emitted.id]


def test_query_count_rae_products_ignores_generated_and_other_users(db):
  customer = create_user(UserRole.CUSTOMER)
  other = create_user(UserRole.CUSTOMER)
  create_rae_product(create_order(), customer, status=RaeStatus.EMITTED, emission_date=datetime.now())
  create_rae_product(create_order(), customer, status=RaeStatus.GENERATED)
  create_rae_product(create_order(), other, status=RaeStatus.EMITTED, emission_date=datetime.now())

  assert query_count_rae_products(customer.id) == 1


def test_get_product_and_group_merges_group_fields(db):
  customer = create_user(UserRole.CUSTOMER)
  group = create_rae_product_group(group_code='R2', cer_code=160214)
  rae_product = create_rae_product(create_order(), customer, group)

  result = get_product_and_group(rae_product.id)

  assert result['id'] == rae_product.id
  assert result['group_code'] == 'R2'
  assert result['cer_code'] == 160214
  assert result['name'] == group.name


def test_get_rae_products_by_order_requires_product_link(db):
  customer, _, service_user, _ = customer_with_service()
  order = create_order()
  rae_product = create_rae_product(order, customer)

  assert get_rae_products_by_order(order) == []

  create_product(order, service_user, rae_product_id=rae_product.id)

  assert [rp.id for rp in get_rae_products_by_order(order)] == [rae_product.id]


def test_get_disposal_rae_products(db):
  customer = create_user(UserRole.CUSTOMER)
  disposal = create_disposal()
  rae_product = create_rae_product(create_order(), customer, disposal_id=disposal.id)
  create_rae_product(create_order(), customer)  # senza smaltimento

  results = get_disposal_rae_products(disposal.id)

  assert [row[0].id for row in results] == [rae_product.id]


def test_get_disposal_for_export(db):
  carrier = create_carrier(company_name='Vettore')
  center = create_collection_center(company_name='Centro')
  disposal = create_disposal(carrier, center, code='SM-9')

  result = get_disposal_for_export(disposal.id)

  assert result['code'] == 'SM-9'
  assert result['carrier']['company_name'] == 'Vettore'
  assert result['collection_center']['company_name'] == 'Centro'
  assert get_disposal_for_export(disposal.id + 999) is None

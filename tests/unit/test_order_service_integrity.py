from datetime import date
from io import BytesIO

import pandas as pd
import pytest
from database_api import Session
from database_api.operations import create
from sqlalchemy.orm import Session as RawSession
import database_api

from src.database.enum import OrderType, OrderStatus, EuronicsStatus
from src.database.schema import (
  Order,
  Product,
  Photo,
  History,
  ScheduleItemOrder,
  Service,
  ServiceUser,
  RaeProduct,
  ScheduleItem,
)
from src.order_integrity import split_order_by_service_type, InvalidOrderProductsError, assert_order_service_types
from src.checks import check_order_service_types, get_checks, format_order_service_types
from src.end_points.importation.excel import handle_excel_conflict, order_import_by_excel
from src.end_points.orders.crud import update_order
from src.end_points.orders.queries import get_order_by_external_id, get_order_by_external_id_and_customer
from src.end_points.orders.api import is_available_order
from scripts.repair_order_service_types import build_plan, apply_plan
from tests.unit.factories import (
  create_order,
  customer_with_service,
  create_service,
  create_service_user,
  create_product,
  create_rae_product,
  create_schedule,
  link_order_to_schedule,
  create_user,
  auth_header,
  create_company,
)


def mixed_order(types=(OrderType.DELIVERY, OrderType.WITHDRAW), **extra):
  customer, _, su, point = customer_with_service(types[0])
  order = create_order(**extra)
  products = [create_product(order, su, name='Frigo', collection_point_id=point.id)]
  for kind in types[1:]:
    other = create_service_user(customer, create_service(kind))
    products.append(create_product(order, other, name='Frigo', collection_point_id=point.id))
  return order, customer, products, point


def payload(products, point, external_id='EXCEL-TYPES'):
  return {
    'Rif. Com': external_id,
    'Destinatario': 'Mario',
    'Indirizzo Dest.': 'Via Roma 1',
    'Localita': 'Bari',
    'Provincia': 'BA',
    'CAP': '70100',
    'Booking': date.today().isoformat(),
    'DRC': date.today().isoformat(),
    'Piano': '',
    'Note MW + Note': '',
    'products': {'Frigo': {'services': [p.service_user_id for p in products], 'collection_point': {'id': point.id}}},
  }


@pytest.mark.parametrize('kind', [OrderType.WITHDRAW, OrderType.CHECK, OrderType.REPLACEMENT])
def test_homogeneous_repair_only_changes_type_and_is_idempotent(kind):
  order, _, products, _ = mixed_order((kind, kind))
  with Session() as session:
    targets = split_order_by_service_type(session.get(Order, order.id), session)
    assert [target.id for target in targets] == [order.id]
    assert targets[0].type == kind
    session.commit()
  with Session() as session:
    assert build_plan(session)['entries'] == []
    assert len(split_order_by_service_type(session.get(Order, order.id), session)) == 1
    assert session.query(Product).count() == len(products)


def test_four_types_keep_product_ids_money_evidence_schedules_and_rae():
  order, customer, products, _ = mixed_order(
    tuple(OrderType),
    status=OrderStatus.DELIVERED,
    mark=120,
    signature=b'signed',
    completion_date=date.today(),
    motivation='Consegnato',
    external_id='EXT-1',
    external_link='https://example.test/orders/EXT-1',
    external_status=EuronicsStatus.NEW,
  )
  schedule = create_schedule()
  item = link_order_to_schedule(order, schedule, completed=True)
  photo = create(Photo, {'order_id': order.id, 'link': 'evidence.jpg'})
  rae = create_rae_product(order, customer)
  with Session() as session:
    session.get(Product, products[1].id).rae_product_id = rae.id
    session.commit()
  with Session() as session:
    previous_histories = session.query(History).filter_by(order_id=order.id).count()
    targets = split_order_by_service_type(session.get(Order, order.id), session)
    target_ids = {target.type: target.id for target in targets}
    assert len(targets) == 4
    session.commit()
  with Session() as session:
    root = session.get(Order, order.id)
    assert root.mark == 120 and root.signature == b'signed' and root.motivation == 'Consegnato'
    assert root.external_id == 'EXT-1'
    assert root.external_link == 'https://example.test/orders/EXT-1'
    assert root.external_status == EuronicsStatus.NEW
    assert session.get(Photo, photo.id).order_id == order.id
    assert session.query(History).filter_by(order_id=order.id).count() == previous_histories
    assert {row.id for row in session.query(Product)} == {p.id for p in products}
    for target in session.query(Order):
      assert_order_service_types(target, session)
      assert target.status == OrderStatus.DELIVERED and target.completion_date == date.today()
      link = session.query(ScheduleItemOrder).filter_by(order_id=target.id).one()
      stop = session.get(ScheduleItem, link.schedule_item_id)
      assert stop.schedule_id == schedule.id and stop.completed
      assert stop.start_time_slot == item.start_time_slot
      assert (stop.id == item.id) == (target.id == order.id)
      if target.id != order.id:
        assert f'Separato da ordine {order.id}.' in target.operator_note
        assert 'Rif. Cliente originale: EXT-1' in target.operator_note
        assert target.external_id is None and target.external_link is None and target.external_status is None
        assert target.mark is None and target.signature is None
        assert not is_available_order(target)
    assert session.get(RaeProduct, rae.id).order_id == target_ids[list(OrderType)[1]]
    assert build_plan(session)['entries'] == []
  assert get_order_by_external_id('EXT-1').id == order.id
  assert get_order_by_external_id_and_customer('EXT-1', customer.id).id == order.id


def test_shared_rae_is_reported_and_never_duplicated():
  order, customer, products, _ = mixed_order()
  rae = create_rae_product(order, customer)
  with Session() as session:
    for p in products:
      session.get(Product, p.id).rae_product_id = rae.id
    session.commit()
  with Session() as session:
    plan = build_plan(session)
    assert 'RAEE' in plan['entries'][0]['blocker']
    with pytest.raises(ValueError, match='bloccati'):
      apply_plan(session, plan)
    with pytest.raises(InvalidOrderProductsError, match='RAEE'):
      split_order_by_service_type(session.get(Order, order.id), session)
  with Session() as session:
    assert session.query(Order).count() == 1
    assert session.query(RaeProduct).count() == 1


def test_plan_apply_unscoped_preserves_company_and_rejects_replay():
  order, _, _, _ = mixed_order()
  with RawSession(database_api.engine) as session:
    plan = build_plan(session)
    result = apply_plan(session, plan)
    session.commit()
    assert len(result[0]['orders']) == 2
    assert build_plan(session)['entries'] == []
    assert all(row.company_id == order.company_id for row in session.query(History))
    with pytest.raises(ValueError, match='obsoleto'):
      apply_plan(session, plan)


def test_stale_plan_rolls_back_all_orders():
  order, _, _, _ = mixed_order()
  with Session() as session:
    plan = build_plan(session)
  with Session() as session:
    session.get(Order, order.id).operator_note = 'Changed after review'
    session.commit()
  with Session() as session:
    with pytest.raises(ValueError, match='obsoleto'):
      apply_plan(session, plan)
  with Session() as session:
    assert session.query(Order).count() == 1
    assert session.get(Order, order.id).operator_note == 'Changed after review'


def test_split_failure_rolls_back_every_partition(monkeypatch):
  order, _, products, _ = mixed_order(tuple(OrderType))
  import src.order_integrity as module

  real_create = module.create
  calls = 0

  def fail(model, data, **kwargs):
    nonlocal calls
    if model is Order:
      calls += 1
      if calls == 2:
        raise RuntimeError('second child failed')
    return real_create(model, data, **kwargs)

  monkeypatch.setattr(module, 'create', fail)
  with pytest.raises(RuntimeError, match='second child'):
    with Session() as session:
      split_order_by_service_type(session.get(Order, order.id), session)
      session.commit()
  with Session() as session:
    assert session.query(Order).count() == 1
    assert {p.order_id for p in session.query(Product)} == {order.id}
    assert session.query(Product).count() == len(products)


def test_daily_check_has_reproducible_ids_and_company_scope():
  order, _, products, _ = mixed_order()
  with Session() as session:
    rows = check_order_service_types(session)
    assert len(rows) == 1
    assert rows[0]['order_id'] == order.id and rows[0]['product_id'] == products[1].id
    assert str(products[1].service_user_id) in format_order_service_types(rows[0])
    assert any(check['query_fn'] is check_order_service_types for check in get_checks())
    session.info['company_id'] = create_company().id
    assert check_order_service_types(session) == []


def test_conflict_import_partitions_and_rejects_wrong_customer():
  existing, customer, products, point = mixed_order(tuple(OrderType))
  result = handle_excel_conflict([payload(products, point)], customer_id=customer.id)
  assert result['imported_orders_count'] == 4 and result['failed_orders'] == []
  with Session() as session:
    imported = session.query(Order).filter(Order.id != existing.id).all()
    assert sum(order.external_id == 'EXCEL-TYPES' for order in imported) == 1
    assert {order.type for order in imported} == set(OrderType)
    for order in imported:
      assert_order_service_types(order, session)
  result = handle_excel_conflict([payload(products, point, 'WRONG')], customer_id=999999)
  assert result['imported_orders_count'] == 0 and result['failed_orders']


def test_automatic_excel_partitions_real_workbook():
  existing, customer, products, point = mixed_order()
  data = payload(products, point)
  base = {key: value for key, value in data.items() if key != 'products'}
  rows = [{**base, 'Cod.  Serv': 'ARTICLE', 'Descr. Serv': 'Frigo', 'LDP': point.name}]
  with Session() as session:
    for index, product in enumerate(products):
      su = session.get(ServiceUser, product.service_user_id)
      su.code = f'SERVICE-{index}'
      rows.append({**base, 'Cod.  Serv': su.code, 'Descr. Serv': 'Servizio', 'LDP': point.name})
    session.commit()
  workbook = BytesIO()
  pd.DataFrame(rows).to_excel(workbook, index=False)
  workbook.seek(0)
  result = order_import_by_excel(workbook, customer.id)
  assert result['conflicted_orders'] == [] and result['imported_orders_count'] == 2
  with Session() as session:
    imported = session.query(Order).filter(Order.id != existing.id).all()
    assert len(imported) == 2
    assert sum(order.external_id == 'EXCEL-TYPES' for order in imported) == 1
    for order in imported:
      assert_order_service_types(order, session)


def test_type_only_edit_is_rejected_even_without_products():
  order, _, _, _ = mixed_order((OrderType.DELIVERY,))
  operator = create_user()
  with pytest.raises(InvalidOrderProductsError):
    with Session() as session:
      update_order(operator, session.get(Order, order.id), {'type': OrderType.CHECK.value}, session)
      session.commit()
  with Session() as session:
    assert session.get(Order, order.id).type == OrderType.DELIVERY


def test_catalog_edits_cannot_invalidate_existing_orders(client):
  _, _, products, _ = mixed_order((OrderType.DELIVERY,))
  with Session() as session:
    su = session.get(ServiceUser, products[0].service_user_id)
    service_id = su.service_id
    service_user_id = su.id
  header = auth_header(create_user())
  response = client.put(
    f'/service/{service_id}', json={'name': 'Changed', 'type': OrderType.CHECK.value}, headers=header
  )
  assert response.json['status'] == 'ko'
  replacement = create_service(OrderType.CHECK)
  response = client.put(f'/service/customer/{service_user_id}', json={'service_id': replacement.id}, headers=header)
  assert response.json['status'] == 'ko'
  with Session() as session:
    assert session.get(Service, service_id).type == OrderType.DELIVERY
    assert session.get(ServiceUser, service_user_id).service_id == service_id


def test_pdf_import_splits_mixed_service_types(monkeypatch):
  import src.end_points.importation.pdf as module
  from tests.unit.end_points.importation.test_pdf import _FakePdf, _FakePage, SAMPLE_TEXT

  customer, _, su, point = customer_with_service()
  other = create_service_user(customer, create_service(OrderType.CHECK), code='CHECK')
  with Session() as session:
    session.get(ServiceUser, su.id).code = 'DELIVERY'
    session.commit()
  table = [
    ['Articolo', 'Modello', 'Tipologia - Descrizione', 'Quantità - Peso Jg', 'Servizio'],
    ['A1', 'M', 'Frigo', '1', 'DELIVERY'],
    ['A1', 'M', 'Frigo', '1', 'CHECK'],
  ]
  monkeypatch.setattr(module.pdfplumber, 'open', lambda _: _FakePdf([_FakePage(SAMPLE_TEXT, [table])]))
  result = module.order_import_by_pdf({'file': BytesIO(b'pdf')}, customer.id)
  assert result['imported_orders_count'] == 2
  with Session() as session:
    assert {order.type for order in session.query(Order)} == {OrderType.DELIVERY, OrderType.CHECK}
    assert {p.service_user_id for p in session.query(Product)} == {su.id, other.id}
    assert check_order_service_types(session) == []


def test_euronics_mixed_types_and_reimport_use_original(monkeypatch):
  import src.end_points.importation.api as module
  from tests.unit.end_points.importation.test_api import _euronics_order, _customer_with_pv

  customer, _ = _customer_with_pv()
  create_service_user(customer, create_service(), code='DELIVERY')
  create_service_user(customer, create_service(OrderType.WITHDRAW), code='WITHDRAW')
  imported = _euronics_order(
    dettaglio=[
      {'cod_articolo': 'ARTICLE', 'descrizione': 'Frigo'},
      {'cod_articolo': 'DELIVERY', 'descrizione': 'Consegna'},
      {'cod_articolo': 'WITHDRAW', 'descrizione': 'Ritiro'},
    ]
  )
  monkeypatch.setattr(module, 'EURONICS_API_PASSWORD', 'test')
  monkeypatch.setattr(module, 'call_list_euronics_api', lambda: [imported])
  module.save_orders_by_euronics()
  module.save_orders_by_euronics()
  with Session() as session:
    assert session.query(Order).count() == 2
    assert {order.type for order in session.query(Order)} == {OrderType.DELIVERY, OrderType.WITHDRAW}
    assert check_order_service_types(session) == []


def test_seed_does_not_create_type_mismatches(seeded_db):
  with Session() as session:
    assert check_order_service_types(session) == []


def test_split_schedule_stops_complete_independently():
  from tests.unit.factories import create_schedule_item

  order, _, _, _ = mixed_order(status=OrderStatus.BOOKING)
  schedule = create_schedule()
  original_stop = link_order_to_schedule(order, schedule, index=0)
  later = create_schedule_item(schedule, index=1)
  with Session() as session:
    targets = split_order_by_service_type(session.get(Order, order.id), session)
    child_id = next(target.id for target in targets if target.id != order.id)
    session.commit()
  operator = create_user()
  with Session() as session:
    update_order(operator, session.get(Order, order.id), {'status': OrderStatus.DELIVERED.value}, session)
    session.commit()
  with Session() as session:
    child_stop = session.query(ScheduleItemOrder).filter_by(order_id=child_id).one().schedule_item_id
    assert session.get(ScheduleItem, original_stop.id).completed
    assert not session.get(ScheduleItem, child_stop).completed
    assert session.get(ScheduleItem, child_stop).index == 1
    assert session.get(ScheduleItem, later.id).index == 2
    assert session.get(Order, child_id).status == OrderStatus.BOOKING


def test_cli_dry_run_apply_and_new_dry_run(tmp_path, monkeypatch):
  import json
  from scripts.repair_order_service_types import main

  mixed_order()
  plan_path = tmp_path / 'plan.json'
  result_path = tmp_path / 'result.json'
  monkeypatch.setattr('sys.argv', ['repair', '--output', str(plan_path)])
  main()
  with Session() as session:
    assert session.query(Order).count() == 1
  assert len(json.loads(plan_path.read_text())['entries']) == 1
  monkeypatch.setattr('sys.argv', ['repair', '--apply', str(plan_path), '--output', str(result_path)])
  main()
  assert len(json.loads(result_path.read_text())['applied'][0]['orders']) == 2
  empty_path = tmp_path / 'empty.json'
  monkeypatch.setattr('sys.argv', ['repair', '--output', str(empty_path)])
  main()
  assert json.loads(empty_path.read_text())['entries'] == []


def test_clone_of_split_child_keeps_external_ownership():
  from src.end_points.orders.crud import create_order as create_order_command

  order, customer, _, _ = mixed_order(external_id='CLONE-EXT')
  with Session() as session:
    children = split_order_by_service_type(session.get(Order, order.id), session)
    child = next(item for item in children if item.id != order.id)
    session.commit()
    service_id = (
      session.query(ServiceUser.service_id)
      .join(Product, Product.service_user_id == ServiceUser.id)
      .filter(Product.order_id == child.id)
      .scalar()
    )
  response = create_order_command(
    create_user(),
    {
      'type': child.type.value,
      'addressee': 'Cliente',
      'address': 'Via Roma',
      'cap': '70100',
      'dpc': date.today(),
      'drc': date.today(),
      'user_id': customer.id,
      'cloned_order_id': child.id,
      'external_id': child.external_id,
      'operator_note': child.operator_note,
      'products': {'Frigo': {'services': [{'id': service_id}]}},
    },
  )
  assert response['status'] == 'ok'
  assert response['order'].get('external_id') is None
  assert f'Separato da ordine {order.id}.' in response['order']['operator_note']
  assert get_order_by_external_id('CLONE-EXT').id == order.id


def test_repair_rejects_plans_with_previous_external_reference_policy():
  with Session() as session:
    with pytest.raises(ValueError, match='Formato piano non supportato'):
      apply_plan(session, {'format_version': 1, 'entries': []})

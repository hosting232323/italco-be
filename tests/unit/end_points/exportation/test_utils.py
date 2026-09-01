import os

from api.storage import get_full_path

from src import STATIC_FOLDER
from src.database.enum import OrderStatus
from src.end_points.exportation.utils import (
  LOGO_SUBFOLDER,
  export_excel,
  export_pdf,
  get_company_logo,
  get_signature,
  get_signature_slots,
  _ares_logo,
)

from tests.unit.factories import create_company, create_order


def test_get_signature_slots_delivered_without_anomaly(db):
  order = create_order(signature=b'\x89PNG-fake', status=OrderStatus.DELIVERED, anomaly=False)
  delivery_sig, anomaly_sig = get_signature_slots(order)
  assert delivery_sig is not None
  assert delivery_sig.startswith('data:image/png;base64,')
  assert anomaly_sig is None


def test_get_signature_slots_delivered_with_anomaly(db):
  order = create_order(signature=b'\x89PNG-fake', status=OrderStatus.DELIVERED, anomaly=True)
  delivery_sig, anomaly_sig = get_signature_slots(order)
  assert delivery_sig is None
  assert anomaly_sig is not None
  assert anomaly_sig.startswith('data:image/png;base64,')


def test_get_signature_slots_other_status(db):
  order = create_order(signature=b'\x89PNG-fake', status=OrderStatus.NOT_DELIVERED, anomaly=True)
  delivery_sig, anomaly_sig = get_signature_slots(order)
  assert delivery_sig is None
  assert anomaly_sig is None


def test_get_signature_slots_without_signature(db):
  order = create_order(status=OrderStatus.DELIVERED, anomaly=False)
  delivery_sig, anomaly_sig = get_signature_slots(order)
  assert delivery_sig is None
  assert anomaly_sig is None


def test_get_signature_encodes_base64_data_uri(db):
  order = create_order(signature=b'\x89PNG-fake')

  signature = get_signature(order)

  assert signature.startswith('data:image/png;base64,')


def test_get_signature_none_without_signature(db):
  assert get_signature(create_order()) is None


def test_get_company_logo_falls_back_to_ares_without_company_or_logo(db):
  assert get_company_logo(None) == _ares_logo()
  assert get_company_logo(create_company()) == _ares_logo()


def test_get_company_logo_falls_back_to_ares_when_file_missing(db):
  company = create_company()
  company.logo = 'http://x/company/logo/999.png'
  assert get_company_logo(company) == _ares_logo()


def test_get_company_logo_embeds_the_stored_file(db):
  company = create_company()
  company.logo = 'http://x/company/logo/logo-test.png'
  folder = get_full_path(STATIC_FOLDER, LOGO_SUBFOLDER)
  os.makedirs(folder, exist_ok=True)
  with open(os.path.join(folder, 'logo-test.png'), 'wb') as logo_file:
    logo_file.write(b'\x89PNG\r\n\x1a\nfake')

  data_uri = get_company_logo(company)

  assert data_uri.startswith('data:image/png;base64,')


def test_export_pdf_sets_headers(app):
  with app.test_request_context():
    response = export_pdf(b'%PDF-1.4')

  assert response.headers['Content-Type'] == 'application/pdf'
  assert response.headers['Content-Disposition'] == 'inline; filename=report.pdf'
  assert response.get_data() == b'%PDF-1.4'


def test_export_excel_sets_headers(app):
  with app.test_request_context():
    response = export_excel(b'PK\x03\x04')

  assert response.headers['Content-Type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  assert response.headers['Content-Disposition'] == 'attachment; filename=report.xlsx'

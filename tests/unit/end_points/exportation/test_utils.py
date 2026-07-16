from src.end_points.exportation.utils import export_excel, export_pdf, get_signature

from tests.unit.factories import create_order


def test_get_signature_encodes_base64_data_uri(db):
  order = create_order(signature=b'\x89PNG-fake')

  signature = get_signature(order)

  assert signature.startswith('data:image/png;base64,')


def test_get_signature_none_without_signature(db):
  assert get_signature(create_order()) is None


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

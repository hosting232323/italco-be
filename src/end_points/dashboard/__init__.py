from flask import Blueprint, request

from ...database.schema import User
from ...database.enum import UserRole
from .. import flask_session_authentication
from .queries import get_dashboard_analytics


dashboard_bp = Blueprint('dashboard_bp', __name__)


@dashboard_bp.route('analytics', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def analytics(_: User):
  body = request.json or {}
  return {
    'status': 'ok',
    'analytics': get_dashboard_analytics(body.get('start'), body.get('end')),
  }

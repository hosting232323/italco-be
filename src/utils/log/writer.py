import json
from datetime import datetime

from ..date import ROME_TZ
from .paths import LOG_DIR
from ...database.schema import User
from .serialization import cap_request, cap_field, log_default
from api.telegram import extract_request_data


def write_log(user: User, response=None):
  request_info = extract_request_data(False)
  request_info.pop('headers', None)

  now = datetime.now(ROME_TZ)
  month_dir = LOG_DIR / now.strftime('%Y-%m')
  month_dir.mkdir(parents=True, exist_ok=True)
  log_file = month_dir / f'{now.strftime("%Y-%m-%d")}.jsonl'
  line = json.dumps(
    {
      'ts': now.isoformat(),
      'user_id': user.id,
      'nickname': user.nickname,
      'request': cap_request(request_info),
      'response': cap_field(response),
    },
    ensure_ascii=False,
    default=log_default,
  )

  with open(log_file, 'a', encoding='utf-8') as file:
    file.write(line)
    file.write('\n')

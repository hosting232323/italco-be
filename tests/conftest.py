import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_ENV_FILE = PROJECT_ROOT / '.env.test'

if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

if not TEST_ENV_FILE.is_file():
  raise RuntimeError(f'Missing pytest env file: {TEST_ENV_FILE}')

load_dotenv(TEST_ENV_FILE, override=True)

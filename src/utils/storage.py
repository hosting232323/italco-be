import logging

from api.storage import delete_file, upload_file
from database_api import Session


logger = logging.getLogger(__name__)


class SessionWithStorage:
  """Coordina una sessione database con la compensazione dei file caricati."""

  def __init__(self):
    self._session_context = None
    self._session = None
    self._files: list[dict] = []
    self._committed = False

  def __enter__(self):
    self._files = []
    self._committed = False
    self._session_context = Session()
    self._session = self._session_context.__enter__()
    return self

  def __exit__(self, exception_type, exception, traceback):
    try:
      return self._session_context.__exit__(exception_type, exception, traceback)
    finally:
      if not self._committed:
        self._rollback_storage()
      self._session = None
      self._session_context = None

  def __getattr__(self, name):
    if self._session is None:
      raise AttributeError(name)
    return getattr(self._session, name)

  def upload(self, content, filename: str, folder: str, *, server=None, subfolder=None, ignore_dev=None) -> str:
    file_data = {
      'filename': filename,
      'folder': folder,
      'server': server,
      'subfolder': subfolder,
      'ignore_dev': ignore_dev,
    }
    self._files.append(file_data)
    return upload_file(content, filename, folder, server=server, subfolder=subfolder, ignore_dev=ignore_dev)

  def commit(self):
    try:
      self._session.commit()
    except Exception:
      self._session.rollback()
      self._rollback_storage()
      raise
    self._files.clear()
    self._committed = True

  def _rollback_storage(self):
    for file_data in reversed(self._files):
      try:
        delete_file(**file_data)
      except FileNotFoundError:
        pass
      except Exception:
        logger.exception('Impossibile eliminare il file dopo il rollback: %s', file_data['filename'])
    self._files.clear()

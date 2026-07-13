import logging

from api.storage import delete_file, upload_file


logger = logging.getLogger(__name__)


class StorageTransaction:
  """Compensa sullo storage gli errori avvenuti prima del commit applicativo."""

  def __init__(self):
    self._files: list[dict] = []

  def __enter__(self):
    return self

  def __exit__(self, exception_type, exception, traceback):
    if exception_type is not None:
      self.rollback()
    return False

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

  def rollback(self):
    for file_data in reversed(self._files):
      try:
        delete_file(**file_data)
      except FileNotFoundError:
        pass
      except Exception:
        logger.exception('Impossibile eliminare il file dopo il rollback: %s', file_data['filename'])
    self._files.clear()

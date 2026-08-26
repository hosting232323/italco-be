import os
import base64

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


# Chiave/IV usati storicamente dal frontend (VITE_SECRET_KEY / VITE_IV) e dal
# seed per cifrare le password con AES-CBC. Servono solo a riconoscere le
# password legacy al primo login: dopo la verifica la password viene
# ri-hashata con scrypt e questo percorso non serve piu' per quell'utente.
# OBBLIGATORI finche' esistono utenti non ancora migrati.
LEGACY_PASSWORD_SECRET_KEY = os.environ['LEGACY_PASSWORD_SECRET_KEY']
LEGACY_PASSWORD_IV = os.environ['LEGACY_PASSWORD_IV']


def legacy_encrypt(password: str) -> str:
  key_bytes = LEGACY_PASSWORD_SECRET_KEY.encode('utf-8')
  iv_bytes = LEGACY_PASSWORD_IV.encode('utf-8')

  padder = padding.PKCS7(128).padder()
  padded = padder.update(password.encode('utf-8')) + padder.finalize()

  cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes))
  encryptor = cipher.encryptor()
  ciphertext = encryptor.update(padded) + encryptor.finalize()
  return base64.b64encode(iv_bytes + ciphertext).decode('utf-8')

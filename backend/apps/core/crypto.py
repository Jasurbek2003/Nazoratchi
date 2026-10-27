"""Maxfiy maydonlarni shifrlash: AES-256-GCM, har yozuv uchun yangi nonce, `aad` = obyekt id (TZ 14.6).

`aad` shifrlangan qiymatni boshqa qatorga ko'chirib qo'yishdan himoya qiladi: bir kanalning
shifrlangan sozlamasi boshqa kanalda ochilmaydi.
"""

import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

NONCE_LEN = 12


class DecryptionError(Exception):
    """Kalit noto'g'ri, ma'lumot buzilgan yoki `aad` mos emas."""


def encrypt_json(value: Any, aad: bytes) -> bytes:
    nonce = os.urandom(NONCE_LEN)
    plain = json.dumps(value, separators=(",", ":")).encode()
    return nonce + AESGCM(settings.NAZORATCHI_MASTER_KEY).encrypt(nonce, plain, aad)


def decrypt_json(blob: bytes | memoryview, aad: bytes) -> Any:
    data = bytes(blob)
    if len(data) <= NONCE_LEN:
        raise DecryptionError("shifrlangan qiymat qisqa")
    try:
        plain = AESGCM(settings.NAZORATCHI_MASTER_KEY).decrypt(
            data[:NONCE_LEN], data[NONCE_LEN:], aad
        )
    except InvalidTag as exc:
        raise DecryptionError("shifrni ochib bo'lmadi (kalit yoki aad mos emas)") from exc
    return json.loads(plain)

"""Yagona "leader" (TZ 16.6, T-C-14): bir nechta evaluator/prober nusxasi ishlasa, faqat bittasi ishlaydi.

Postgres session darajasidagi advisory lock, alohida ulanishda ushlab turiladi: jarayon o'lsa yoki ulanish
uzilsa qulf o'zi bo'shaydi, boshqa nusxa keyingi davrda leader bo'ladi.
"""

import contextlib
import logging
from typing import Any

import psycopg
from django.db import connection

logger = logging.getLogger(__name__)

# Ixtiyoriy, barqaror 64-bit kalitlar (nom bo'yicha).
KEYS = {"evaluator": 0x4E5A5201, "prober": 0x4E5A5202}


class Leader:
    def __init__(self, name: str) -> None:
        self.key = KEYS[name]
        self.name = name
        self._conn: psycopg.Connection[Any] | None = None

    def _open(self) -> psycopg.Connection[Any]:
        s = connection.settings_dict
        return psycopg.connect(
            dbname=s["NAME"],
            user=s["USER"],
            password=s["PASSWORD"],
            host=s["HOST"],
            port=s["PORT"] or None,
            autocommit=True,
            connect_timeout=5,
        )

    def ensure(self) -> bool:
        """Leader bo'lsak (yoki bo'la olsak) True. Baza yo'q bo'lsa False (qulf ushlab turilmaydi)."""
        try:
            if self._conn is not None and not self._conn.closed:
                self._conn.execute("SELECT 1")  # ulanish tirikligini tekshirish
                return True
            self._conn = None
            conn = self._open()
            row = conn.execute("SELECT pg_try_advisory_lock(%s)", [self.key]).fetchone()
            if row and row[0]:
                self._conn = conn
                logger.info("%s: leader bo'ldi", self.name)
                return True
            conn.close()
            return False
        except psycopg.Error:
            logger.warning("%s: leader tekshiruvi xato", self.name, exc_info=True)
            self.release()
            return False

    def release(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(psycopg.Error):
                self._conn.close()
            self._conn = None

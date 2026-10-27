"""Buyruq qatori kirish nuqtasi: xizmat, --check-config, --test-telegram."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from collections.abc import Mapping

from nazoratchi_watchdog import __version__
from nazoratchi_watchdog.config import Config, ConfigError, load_config
from nazoratchi_watchdog.logs import register_secret, setup_logging
from nazoratchi_watchdog.monitor import Monitor
from nazoratchi_watchdog.server import WatchdogServer
from nazoratchi_watchdog.state import StateStore
from nazoratchi_watchdog.telegram import TelegramNotifier

log = logging.getLogger("nazoratchi_watchdog.app")


def _notifier(cfg: Config) -> TelegramNotifier:
    return TelegramNotifier(cfg.telegram_api, cfg.bot_token, cfg.chat_id)


def serve(cfg: Config, stop: threading.Event | None = None) -> int:
    stop = stop or threading.Event()
    monitor = Monitor(
        timeout_s=cfg.timeout_s,
        remind_s=cfg.remind_s,
        store=StateStore(cfg.state_file),
        notifier=_notifier(cfg),
    )
    server = WatchdogServer((cfg.host, cfg.port), monitor, cfg.watchdog_id)
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
    http_thread = threading.Thread(target=server.serve_forever, name="http", daemon=True)
    mon_thread = threading.Thread(target=monitor.run, args=(stop,), name="monitor", daemon=True)
    http_thread.start()
    mon_thread.start()
    log.info(
        "Watchdog ishga tushdi: %s:%d, kutish %d s, eslatma %d s, holat %s (%s)",
        cfg.host,
        cfg.port,
        cfg.timeout_s,
        cfg.remind_s,
        cfg.state_file,
        "tiklandi" if monitor.restored else "yangi",
    )
    stop.wait()
    log.info("To'xtatilmoqda")
    server.shutdown()
    server.server_close()
    mon_thread.join(timeout=5)
    log.info("To'xtadi")
    return 0


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nazoratchi_watchdog", description="Nazoratchi core tirikligini tashqaridan tekshirish"
    )
    parser.add_argument("--check-config", action="store_true", help="sozlamani tekshirib chiqish")
    parser.add_argument(
        "--test-telegram", action="store_true", help="Telegram'ga sinov xabarini yuborish"
    )
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    setup_logging()
    try:
        cfg = load_config(os.environ if env is None else env)
    except ConfigError as exc:
        print("Sozlama xatosi:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    register_secret(cfg.bot_token)
    register_secret(cfg.watchdog_id)

    if args.check_config:
        print(
            f"Sozlama to'g'ri: {cfg.host}:{cfg.port}, kutish {cfg.timeout_s} s, "
            f"eslatma {cfg.remind_s} s, holat fayli {cfg.state_file}, "
            f"Telegram {cfg.telegram_api}, chat {cfg.chat_id}, token ***, id ***."
        )
        return 0
    if args.test_telegram:
        ok = _notifier(cfg).send(
            "🧪 <b>Nazoratchi watchdog</b>: sinov xabari. Telegram ulanishi ishlayapti."
        )
        print("Sinov xabari yuborildi." if ok else "Sinov xabari YUBORILMADI (loglarga qarang).")
        return 0 if ok else 1
    return serve(cfg)

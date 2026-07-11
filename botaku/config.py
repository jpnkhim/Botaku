"""
botaku.config - Konfigurasi Bot (env, constants, platform)
Modular replacement for bagian KONFIGURASI di telekuq_fixed.py
"""
from __future__ import annotations
import os
import sys
import platform
from pathlib import Path

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')
except ImportError:
    pass

# === Timeout Telegram ===
TELEGRAM_OP_TIMEOUT = 30
TELEGRAM_CONNECT_TIMEOUT = 8
TELEGRAM_DISCONNECT_TIMEOUT = 8

# Status akun yang harus di-skip
SKIP_STATUSES = ('terblokir', 'expired', 'dibatasi', 'flood_wait', 'timeout')

# === Cross-platform ===
def setup_asyncio_windows():
    if sys.platform == 'win32':
        if sys.version_info >= (3, 8):
            try:
                import asyncio
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except AttributeError:
                pass

setup_asyncio_windows()

PLATFORM = platform.system().lower()
IS_WINDOWS = PLATFORM == 'windows'
IS_LINUX = PLATFORM == 'linux'
IS_TERMUX = os.path.exists('/data/data/com.termux')

BASE_DIR = Path(__file__).parent.parent.absolute()

# === Bot Token ===
BOT_TOKEN = os.getenv("TELEKU_BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

ADMIN_USER_IDS_STR = os.getenv("ADMIN_USER_IDS", "").strip()
ADMIN_USER_IDS = set(int(uid.strip()) for uid in ADMIN_USER_IDS_STR.split(",") if uid.strip().isdigit())

# === Mongo ===
MONGO_URL = os.getenv("TELEKU_MONGO_URL", os.getenv("MONGO_URL", "")).strip()

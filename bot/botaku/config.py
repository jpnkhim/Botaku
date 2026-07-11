"""
botaku.config - Konfigurasi Bot (env, constants, platform)
Modular replacement for bagian KONFIGURASI di telekuq_fixed.py
"""
from __future__ import annotations
import os
import re
import sys
import asyncio
import platform
import random
import uuid as _uuid
import io
import json
from datetime import datetime, timedelta
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


# === Additional constants from original file (auto-extracted) ===

# FIXED: Async DB helpers - pymongo is SYNC and blocks event loop, so wrap with to_thread
async def db_find_one(coll, *args, **kwargs):
    if coll is None:
        return None
    return await asyncio.to_thread(coll.find_one, *args, **kwargs)

async def db_find(coll, *args, **kwargs):
    if coll is None:
        return []
    return await asyncio.to_thread(lambda: list(coll.find(*args, **kwargs)))

async def db_count(coll, filter_dict=None):
    if coll is None:
        return 0
    if filter_dict is None:
        filter_dict = {}
    return await asyncio.to_thread(coll.count_documents, filter_dict)

async def db_update_one(coll, *a, **kw):
    if coll is None:
        return None
    return await asyncio.to_thread(coll.update_one, *a, **kw)

async def db_insert_one(coll, *a, **kw):
    if coll is None:
        raise RuntimeError("DB not initialized")
    return await asyncio.to_thread(coll.insert_one, *a, **kw)

async def db_delete_one(coll, *a, **kw):
    if coll is None:
        return None
    return await asyncio.to_thread(coll.delete_one, *a, **kw)

# FIXED: Config validation (security)

MAX_BULK_JOIN_TARGETS = 50


_INVITE_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?t(?:elegram)?\.me/(?:joinchat/|\+)([A-Za-z0-9_\-]+)/?$",
    re.IGNORECASE,
)

_PUBLIC_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?t(?:elegram)?\.me/([A-Za-z0-9_]+)(?:/.*)?$",
    re.IGNORECASE,
)

_USERNAME_RE = re.compile(r"^@?([A-Za-z][A-Za-z0-9_]{3,31})$")

_RESERVED_PATHS = {
    "joinchat", "addstickers", "share", "proxy", "socks", "iv", "s", "c",
    "setlanguage", "bg", "emoji", "confirmphone", "addlist", "addtheme",
}



AUTO_STEP_TYPES = ("send_message", "click_button", "delay", "wait_reply", "send_txt_line", "send_txt_random")

# Registry automation yang sedang berjalan.
# Key: automation_id (string), Value: {
#   "name": str, "owner_user_id": int, "tasks": [asyncio.Task],
#   "cancel_event": asyncio.Event, "started_at": str,
#   "target": str, "accounts_count": int, "loop_mode": str,
# }
running_automations: dict = {}



SCHEDULE_POLL_INTERVAL = 30  # detik — interval scheduler memeriksa jadwal

SCH_VALID_MODES = ("daily", "interval")



MAIN_MENU_BUTTONS = [
    ["📨 Kirim Pesan", "👤 Kelola Akun"],
    ["👥 Gabung Grup", "📦 Import & Export"],
    ["🤖 Automation", "🛠️ Tools & Pengaturan"],
    ["❓ Bantuan"],
]


SUBMENU_KIRIM = [
    ["⚡ Kirim Cepat", "📤 Kirim Pesan"],
    ["📄 Kirim File TXT"],
    ["🔐 Ambil Pesan OTP", "🔁 Ulangi Aksi Terakhir"],
    ["🔙 Kembali"],
]


SUBMENU_AKUN = [
    ["➕ Tambah Akun Login", "➕ Tambah Akun Manual"],
    ["📋 Lihat Semua Akun", "ℹ️ Info Akun"],
    ["📊 Status Akun", "🧪 Test Akun"],
    ["🗑️ Hapus Akun", "🔄 Reset Status"],
    ["🏷️ Kelola Tag", "🔎 Cari Akun"],
    ["🔙 Kembali"],
]


SUBMENU_EXPORT = [
    ["📥 Export JSON", "🧾 Export Ringkasan"],
    ["⬆️ Import JSON"],
    ["🔙 Kembali"],
]


SUBMENU_SETTINGS = [
    ["⚙️ Pengaturan", "🔍 Test Database"],
    ["🔘 Ambil ID Button"],
    ["🔙 Kembali"],
]


SUBMENU_AUTOMATION = [
    ["➕ Buat Automation", "📋 Daftar Automation"],
    ["▶️ Jalankan Automation", "⏹️ Stop Automation"],
    ["🗑️ Hapus Automation", "📅 Jadwal"],
    ["🔙 Kembali"],
]


SUBMENU_SCHEDULE = [
    ["➕ Buat Jadwal", "📋 Daftar Jadwal"],
    ["🔀 Toggle ON/OFF", "🗑️ Hapus Jadwal"],
    ["🔙 Kembali"],
]


SCH_MODE_BUTTONS = [
    ["📅 Harian (HH:MM)", "⏱️ Interval (detik)"],
    ["🔙 Kembali ke Menu Utama"],
]


AUTO_STEP_MENU_BUTTONS = [
    ["✉️ Step: Kirim Pesan", "🔘 Step: Klik Tombol"],
    ["⏱️ Step: Delay", "⏳ Step: Tunggu Balasan"],
    ["📄 Step: Kirim TXT per-Akun", "🎲 Step: Kirim TXT Random"],
    ["✏️ Kelola Step", "💾 Simpan Automation"],
    ["🔙 Kembali ke Menu Utama"],
]


AUTO_LOOP_BUTTONS = [
    ["1️⃣ Sekali", "🔢 N Kali"],
    ["♾️ Tanpa Batas (Infinite)"],
    ["🔙 Kembali ke Menu Utama"],
]


AUTO_RUN_AKUN_SCOPE_BUTTONS = [
    ["📋 Semua Akun"],
    ["🔢 Jumlah Tertentu", "🏷️ Berdasarkan Tag"],
    ["🔙 Kembali ke Menu Utama"],
]


CANCEL_BUTTON = [["🔙 Kembali ke Menu Utama"]]


AKUN_SCOPE_BUTTONS = [
    ["📋 Semua Akun"],
    ["🔢 Jumlah Tertentu", "🏷️ Berdasarkan Tag"],
    ["🔙 Kembali ke Menu Utama"],
]


CANCEL_REPEAT_BUTTONS = [["❌ Batalkan Proses"]]

# State untuk ConversationHandler bot Telegram
(
    STATE_MAIN_MENU,
    STATE_TAMBAH_API_ID,
    STATE_TAMBAH_API_HASH,
    STATE_TAMBAH_SESSION,
    STATE_TAMBAH_LOGIN_API_ID,
    STATE_TAMBAH_LOGIN_API_HASH,
    STATE_TAMBAH_LOGIN_PHONE,
    STATE_TAMBAH_LOGIN_CODE,
    STATE_TAMBAH_LOGIN_PASSWORD,
    STATE_HAPUS_AKUN,
    STATE_KIRIM_TARGET,
    STATE_KIRIM_PILIH_AKUN,
    STATE_KIRIM_PESAN,
    STATE_KIRIM_CONFIRM,
    STATE_GABUNG_GROUP,
    STATE_GABUNG_SCOPE,
    STATE_GABUNG_TAG,
    STATE_GABUNG_CONFIRM,
    STATE_OTP_PILIH_AKUN,
    STATE_OTP_CHAT_ID,
    STATE_OTP_JUMLAH,
    STATE_OTP_CONFIRM,
    STATE_INFO_AKUN_PILIH,
    STATE_EXPORT_CONFIRM,
    STATE_TEST_AKUN_PILIH,
    STATE_SEARCH_QUERY,
    STATE_TAG_PILIH,
    STATE_TAG_INPUT,
    STATE_IMPORT_JSON_WAIT,
    STATE_SETTINGS_MENU,
    STATE_SETTINGS_VALUE,
    STATE_KIRIM_CEPAT_TARGET,
    STATE_KIRIM_CEPAT_PESAN,
    STATE_KIRIM_CEPAT_SCOPE,
    STATE_KIRIM_CEPAT_CONFIRM,
    STATE_RESET_STATUS_PILIH,
    STATE_RESET_STATUS_CONFIRM,
    STATE_KIRIM_FILE_TARGET,
    STATE_KIRIM_FILE_UPLOAD,
    STATE_KIRIM_FILE_SCOPE,
    STATE_KIRIM_FILE_CONFIRM,
    STATE_KIRIM_FILE_SELESAI,
    STATE_KIRIM_FILE_SENDING,
    STATE_REPEAT_RUNNING,
    STATE_BTNID_PILIH_AKUN,
    STATE_BTNID_TARGET,
    STATE_BTNID_JUMLAH,
    # ===== STATE AUTOMATION =====
    STATE_AUTO_NAME,
    STATE_AUTO_STEP_MENU,
    STATE_AUTO_STEP_SEND_TEXT,
    STATE_AUTO_STEP_DELAY_SEC,
    STATE_AUTO_STEP_CLICK_ID,
    STATE_AUTO_STEP_WAIT_TIMEOUT,
    STATE_AUTO_STEP_SEND_TXT,
    STATE_AUTO_STEP_SEND_TXT_RANDOM,
    STATE_AUTO_STEP_EDIT,
    STATE_AUTO_DELETE_PILIH,
    STATE_AUTO_RUN_PILIH,
    STATE_AUTO_RUN_TARGET,
    STATE_AUTO_RUN_PILIH_AKUN,
    STATE_AUTO_RUN_LOOP_MODE,
    STATE_AUTO_RUN_LOOP_N,
    STATE_AUTO_RUN_LOOP_DELAY,
    STATE_AUTO_RUN_CONFIRM,
    STATE_AUTO_STOP_PILIH,
    # ===== STATE JADWAL =====
    STATE_SCH_PILIH_AUTO,
    STATE_SCH_MODE,
    STATE_SCH_TIME_VALUE,
    STATE_SCH_JITTER,
    STATE_SCH_TARGET,
    STATE_SCH_AKUN_SCOPE,
    STATE_SCH_AKUN_VALUE,
    STATE_SCH_CONFIRM,
    STATE_SCH_TOGGLE_PILIH,
    STATE_SCH_DELETE_PILIH,
) = range(75)



CONFIRM_BUTTONS = [["✅ Ya, lanjutkan"], ["🔙 Kembali ke Menu Utama"]]


SETTINGS_MENU_BUTTONS = [
    ["1️⃣ Default OTP", "2️⃣ Delay Kirim Pesan"],
    ["3️⃣ Delay Join Grup", "4️⃣ Interval Progres"],
    ["5️⃣ Batch Paralel"],
    ["6️⃣ Auto: Batch Paralel", "7️⃣ Auto: Delay antar Akun"],
    ["🔙 Kembali ke Menu Utama"],
]


RESET_STATUS_BUTTONS = [
    ["1️⃣ Reset Semua"],
    ["2️⃣ Timeout & Flood", "3️⃣ Dibatasi"],
    ["4️⃣ Expired", "5️⃣ Terblokir"],
    ["6️⃣ Nomor Tertentu"],
    ["🔙 Kembali ke Menu Utama"],
]



DEFAULT_SETTINGS = {
    "otp_default": 5,
    "kirim_delay": 2,
    "join_delay": 3,
    "progress_step": 5,
    "parallel_batch": 3,
    "auto_parallel_batch": 0,   # 0 = semua akun serentak (unlimited)
    "auto_account_delay": 0,    # detik delay antar akun saat start automation
}



CANCEL_SENDING_BUTTONS = [["❌ Batalkan Pengiriman"]]



SELESAI_BUTTONS = [["🔀 Acak & Kirim Ulang"], ["🔙 Kembali ke Menu Utama"]]




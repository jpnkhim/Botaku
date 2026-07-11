"""
main.py - Entry point modular TeleKu Bot untuk Koyeb Web Service
- Health check server (anti Address already in use)
- Singleton lock (anti Conflict)
- Bot polling dengan fallback handlers (anti inline button mati)
"""
from __future__ import annotations
import os
import sys
import asyncio
import threading
import http.server
import socketserver
import logging
import socket

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("telekubot")

# Import config & database
from botaku.config import BOT_TOKEN, MONGO_URL, ADMIN_USER_IDS, BASE_DIR
from botaku.database import init_database

def check_port_in_use(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False

def start_health_check_server():
    port = int(os.getenv("PORT", "8000"))
    if check_port_in_use(port):
        logger.info(f"ℹ️ Port {port} sudah dipakai, skip health server (ok for Koyeb)")
        return

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"TeleKu Modular Bot Healthy - Koyeb")
        def log_message(self, *args):
            pass

    def _run():
        try:
            socketserver.TCPServer.allow_reuse_address = True
            with socketserver.TCPServer(("", port), Handler) as httpd:
                logger.info(f"🚀 Health server running on {port}")
                httpd.serve_forever()
        except OSError as e:
            if e.errno == 98:
                logger.info(f"Port {port} already in use, skip")
            else:
                logger.warning(f"Health server fail: {e}")

    threading.Thread(target=_run, daemon=True).start()

# Singleton lock
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

def acquire_singleton_lock():
    if not HAS_FCNTL:
        return None
    try:
        lock_file = open("/tmp/teleku_bot.lock", "w")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        logger.info("✅ Singleton lock acquired")
        return lock_file
    except (IOError, OSError):
        logger.error("❌ Another bot instance running (lock exists), exit to prevent Conflict")
        sys.exit(1)

def main():
    print("="*70)
    print("🚀 TeleKu Modular Bot - Koyeb Web Service")
    print("="*70)
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"PORT: {os.getenv('PORT','8000')}")
    print(f"ADMIN_USER_IDS: {ADMIN_USER_IDS}")
    print("="*70)

    start_health_check_server()
    global _singleton_lock
    _singleton_lock = acquire_singleton_lock()

    # Init DB
    client, db, collection = init_database()
    if client is None:
        logger.error("DB init failed, exit")
        sys.exit(1)

    # Build & run bot
    from botaku.bot import build_application
    app = build_application()
    logger.info("✅ Bot Telegram berjalan (modular version)")
    app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"], poll_interval=1.0)

if __name__ == "__main__":
    main()

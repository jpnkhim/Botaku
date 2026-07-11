from __future__ import annotations
import asyncio
import random
import uuid as _uuid
import io
import json
import logging
from datetime import datetime, timedelta
from .config import *
from .keyboards import *
from .states import *
from .ux import render_banner, ICON, shorten_text
from .telegram_client import get_telegram_client, safe_connect_and_check, safe_disconnect, safe_telegram_operation
from .database import collection, automation_collection, schedule_collection, log_collection
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger("telekubot")


def _now_iso():
    return datetime.now().isoformat()


def update_account_status(nomor_telepon: str, status: str, alasan: str = ""):
    """Update status akun di database. Dipanggil setelah error dari Telegram."""
    if collection is None or not nomor_telepon:
        return
    try:
        collection.update_one(
            {"nomor_telepon": nomor_telepon},
            {"$set": {
                "status": status,
                "status_alasan": (alasan or "")[:300],
                "status_updated_at": datetime.now().isoformat(),
            }},
        )
    except Exception as e:
        logger.warning(f"update_account_status gagal: {e}")


async def validasi_akun_telegram(api_id, api_hash, string_sesi):
    """Validasi 1 akun Telegram → return (sukses, user_data_dict, error_message)."""
    client = None
    try:
        client = get_telegram_client(
            string_sesi, api_id, api_hash,
            connection_retries=1, retry_delay=1,
            timeout=TELEGRAM_CONNECT_TIMEOUT,
        )
        ok, err = await safe_connect_and_check(client, timeout=TELEGRAM_CONNECT_TIMEOUT)
        if not ok:
            return False, None, err
        me = await safe_telegram_operation(client.get_me(), timeout=TELEGRAM_OP_TIMEOUT)
        user_data = {
            "nomor_telepon": me.phone or "",
            "firstname": me.first_name or "",
            "lastname": me.last_name or "",
            "username": me.username or "",
            "user_id": me.id,
            "first_name": me.first_name or "",
            "last_name": me.last_name or "",
        }
        return True, user_data, None
    except asyncio.TimeoutError:
        return False, None, "Timeout saat validasi akun"
    except Exception as e:
        return False, None, str(e)
    finally:
        await safe_disconnect(client)


def simpan_data(api_id, api_hash, nomor_telepon, string_sesi, name, user_data,
                interactive: bool = False, force_overwrite: bool = True):
    """Simpan / update akun ke database. Return True jika sukses."""
    if collection is None:
        logger.error("simpan_data: collection None")
        return False
    doc = {
        "api_id": str(api_id),
        "api_hash": str(api_hash),
        "nomor_telepon": str(nomor_telepon),
        "string_sesi": str(string_sesi),
        "name": name or user_data.get("firstname", "") + " " + user_data.get("lastname", ""),
        "firstname": user_data.get("firstname") or user_data.get("first_name", ""),
        "lastname": user_data.get("lastname") or user_data.get("last_name", ""),
        "username": user_data.get("username", ""),
        "user_id": user_data.get("user_id", ""),
        "status": "aktif",
        "status_alasan": "",
        "status_updated_at": datetime.now().isoformat(),
        "created_at": datetime.now().isoformat(),
        "validated": True,
        "tags": [],
    }
    try:
        existing = collection.find_one({"nomor_telepon": doc["nomor_telepon"]})
        if existing and not force_overwrite:
            return False
        if existing:
            # Preserve tags/status kalau sudah ada
            doc["tags"] = existing.get("tags", []) or []
            doc["created_at"] = existing.get("created_at", doc["created_at"])
            collection.update_one(
                {"nomor_telepon": doc["nomor_telepon"]},
                {"$set": doc},
            )
        else:
            collection.insert_one(doc)
        return True
    except Exception as e:
        logger.error(f"simpan_data gagal: {e}")
        return False


async def validasi_target_user(api_id, api_hash, string_sesi, target_username):
    """Validasi apakah username target valid dan bisa dihubungi"""
    client = None
    try:
        client = get_telegram_client(
            string_sesi, api_id, api_hash,
            connection_retries=1,
            retry_delay=1,
            timeout=TELEGRAM_CONNECT_TIMEOUT,
        )
        ok, err = await safe_connect_and_check(client, timeout=TELEGRAM_CONNECT_TIMEOUT)
        if not ok:
            return False, f"Gagal connect untuk validasi: {err}"
        
        await safe_telegram_operation(client.get_entity(target_username), timeout=TELEGRAM_OP_TIMEOUT)
        return True, None
    except asyncio.TimeoutError:
        return False, "Timeout saat menghubungi Telegram (akun mungkin bermasalah)"
    except Exception as e:
        return False, f"Username tidak ditemukan atau tidak valid: {str(e)}"
    finally:
        await safe_disconnect(client)


async def ambil_inline_buttons_text(api_id, api_hash, string_sesi, target_entity, jumlah_pesan=10):
    """
    Mengambil pesan terbaru dari chat/user/bot dan menampilkan
    semua inline button beserta informasi lengkapnya.
    Return: list of dicts, masing-masing berisi info pesan + buttons
    """
    klien = None
    try:
        klien = get_telegram_client(
            string_sesi, api_id, api_hash,
            connection_retries=1,
            retry_delay=1,
            timeout=TELEGRAM_CONNECT_TIMEOUT,
        )
        ok, connect_err = await safe_connect_and_check(klien, timeout=TELEGRAM_CONNECT_TIMEOUT)
        if not ok:
            return None, f"❌ Gagal connect: {connect_err}"

        entity = await safe_telegram_operation(klien.get_entity(target_entity), timeout=TELEGRAM_OP_TIMEOUT)
        messages = await safe_telegram_operation(klien.get_messages(entity, limit=jumlah_pesan), timeout=TELEGRAM_OP_TIMEOUT)

        if not messages:
            return None, "⚠️ Tidak ada pesan ditemukan."

        results = []
        for message in messages:
            if not message.buttons:
                continue
            msg_info = {
                "msg_id": message.id,
                "date": str(message.date),
                "text": (message.text or "<non-teks/media>")[:100],
                "rows": [],
            }
            for row_idx, row in enumerate(message.buttons):
                for col_idx, btn in enumerate(row):
                    btn_info = {
                        "row": row_idx + 1,
                        "col": col_idx + 1,
                        "text": btn.text or "",
                        "callback_data": None,
                        "url": None,
                    }
                    if hasattr(btn, "data") and btn.data:
                        try:
                            btn_info["callback_data"] = btn.data.decode("utf-8") if isinstance(btn.data, bytes) else str(btn.data)
                        except Exception:
                            btn_info["callback_data"] = str(btn.data)
                    if hasattr(btn, "url") and btn.url:
                        btn_info["url"] = btn.url
                    msg_info["rows"].append(btn_info)
            if msg_info["rows"]:
                results.append(msg_info)

        if not results:
            return None, "⚠️ Tidak ditemukan pesan yang memiliki inline button."

        return results, None

    except asyncio.TimeoutError:
        return None, "❌ Timeout saat mengambil pesan (akun mungkin bermasalah)"
    except (ConnectionError, OSError) as e:
        return None, f"❌ Connection error: {e}"
    except Exception as e:
        return None, f"❌ Error saat mengambil data button: {e}"
    finally:
        await safe_disconnect(klien)


def format_run_stats_summary(stats_list: list) -> str:
    """Format statistik hasil eksekusi automation per-akun jadi teks ringkasan."""
    if not stats_list:
        return ""
    total = len(stats_list)
    completed = [s for s in stats_list if not s.get("dropped_reason")]
    dropped = [s for s in stats_list if s.get("dropped_reason")]
    status_changed = [s for s in stats_list if s.get("status_change")]

    lines = []
    lines.append("📊 *Ringkasan Eksekusi:*")
    lines.append(f"• Total akun: *{total}*")
    lines.append(f"• ✅ Selesai normal: *{len(completed)}*")
    lines.append(f"• 🛑 Dropped/bermasalah: *{len(dropped)}*")

    # Breakdown dropped reasons
    if dropped:
        reason_counts: dict = {}
        for s in dropped:
            reason = (s.get("dropped_reason") or "").split(":")[0]
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        lines.append("\n*Alasan drop:*")
        for reason, cnt in sorted(reason_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  • `{reason}`: {cnt} akun")

    # Status changes (akun yang di-mark bermasalah di DB)
    if status_changed:
        lines.append(f"\n⚠️ *Status akun di-update di DB: {len(status_changed)} akun*")
        status_counts: dict = {}
        for s in status_changed:
            st = s.get("status_change", "?")
            status_counts[st] = status_counts.get(st, 0) + 1
        for st, cnt in status_counts.items():
            lines.append(f"  • `{st}`: {cnt} akun")

    # Detail per akun (max 20 baris)
    lines.append("\n*Detail per akun:*")
    for s in stats_list[:20]:
        nomor = s.get("nomor", "?")
        if s.get("dropped_reason"):
            icon = "🛑"
            reason = shorten_text(s.get("dropped_reason", ""), 40)
            extra = f" — {reason}"
        else:
            icon = "✅"
            extra = ""
        loops = s.get("loops_done", 0)
        succ = s.get("steps_success", 0)
        fail = s.get("steps_failed", 0)
        lines.append(f"{icon} `{nomor}` — {loops} loop, {succ}/{succ+fail} step{extra}")
    if len(stats_list) > 20:
        lines.append(f"_...dan {len(stats_list) - 20} akun lain_")
    return "\n".join(lines)


def _make_keyboard(buttons):
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in buttons],
        resize_keyboard=True,
    )


def format_seconds(total_seconds: int):
    if total_seconds < 60:
        return f"{total_seconds} detik"
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    if seconds == 0:
        return f"{minutes} menit"
    return f"{minutes} menit {seconds} detik"


def estimate_time(count: int, delay: int):
    if count <= 0:
        return "0 detik"
    return format_seconds(count * delay)


def set_last_action(context: "ContextTypes.DEFAULT_TYPE", action: str, data: dict):
    context.user_data["last_action"] = {"action": action, "data": data}


def get_last_action(context: "ContextTypes.DEFAULT_TYPE"):
    return context.user_data.get("last_action")


def log_action(action: str, detail: dict | None = None):
    if log_collection is None:
        return
    payload = {
        "action": action,
        "detail": detail or {},
        "created_at": datetime.now().isoformat(),
    }
    try:
        log_collection.insert_one(payload)
    except Exception:
        pass


def _build_progress_text(processed, total, sukses, gagal, last_detail, label_extra=""):
    """Membangun teks progress realtime yang selalu diperbarui."""
    persen = int((processed / total) * 100) if total > 0 else 0
    # Progress bar visual (20 karakter)
    filled = int(persen / 5)
    bar = "█" * filled + "░" * (20 - filled)

    text = (
        f"📈 *PROGRES KIRIM FILE TXT{label_extra}*\n\n"
        f"[{bar}] {persen}%\n"
        f"📊 {processed}/{total} pesan diproses\n\n"
        f"✅ Berhasil: {sukses}\n"
        f"❌ Gagal: {gagal}\n"
    )
    if last_detail:
        text += f"\n📌 Terakhir:\n{last_detail}"
    return text


def get_selesai_keyboard():
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in SELESAI_BUTTONS],
        resize_keyboard=True,
    )



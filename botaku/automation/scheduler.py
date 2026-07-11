from __future__ import annotations
from ..keyboards import *
from ..database import *
from ..telegram_client import *
from ..ux import *
from ..states import *
from ..config import *
import asyncio
from datetime import datetime
from ..database import schedule_collection, db_find, db_update_one
def schedule_create_index():
    try:
        if schedule_collection is not None:
            schedule_collection.create_index([("id", ASCENDING)], unique=True)
            schedule_collection.create_index([("owner_user_id", ASCENDING)])
    except Exception:
        pass

def _parse_hhmm(s):
    """Parse 'HH:MM' -> (hour, minute) atau None."""
    try:
        if not isinstance(s, str):
            return None
        parts = s.strip().split(":")
        if len(parts) != 2:
            return None
        h, m = int(parts[0]), int(parts[1])
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except Exception:
        pass
    return None

def _compute_next_run(schedule_type: str, schedule_value, base_dt=None, jitter_minutes: int = 0) -> datetime:
    """Hitung kapan jadwal berikutnya jalan, relatif ke base_dt (default: now).
    jitter_minutes > 0 → tambah offset acak ±jitter_minutes menit (hanya untuk mode daily)."""
    now = base_dt or datetime.now()
    if schedule_type == "daily":
        hm = _parse_hhmm(schedule_value) if isinstance(schedule_value, str) else schedule_value
        if hm is None:
            return now + timedelta(days=1)
        h, m = hm
        candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        if jitter_minutes and jitter_minutes > 0:
            offset_sec = random.randint(-jitter_minutes * 60, jitter_minutes * 60)
            candidate = candidate + timedelta(seconds=offset_sec)
            # Jika randomize membuat jadwal berada di masa lalu (karena jitter negatif),
            # tambah 1 hari agar jadwal tidak langsung langsung trigger.
            if candidate <= now:
                candidate += timedelta(days=1)
        return candidate
    if schedule_type == "interval":
        sec = int(schedule_value)
        return now + timedelta(seconds=sec)
    return now + timedelta(days=1)

def schedule_save(owner_user_id: int, automation_id: str, automation_name: str,
                  schedule_type: str, schedule_value,
                  target: str, akun_scope: str, akun_value: str,
                  jitter_minutes: int = 0):
    """Simpan jadwal baru. Return (sukses, id_atau_error).
    jitter_minutes: offset acak ±X menit (hanya berlaku untuk mode daily)."""
    if schedule_collection is None:
        return False, "Database tidak tersedia"
    if schedule_type not in SCH_VALID_MODES:
        return False, f"Mode jadwal tidak valid: {schedule_type}"
    if schedule_type == "daily" and _parse_hhmm(schedule_value) is None:
        return False, "Format jam tidak valid (gunakan HH:MM)"
    if schedule_type == "interval":
        try:
            iv = int(schedule_value)
            if iv < 5 or iv > 86400 * 30:
                return False, "Interval harus 5 detik s/d 30 hari"
        except Exception:
            return False, "Interval harus angka (detik)"
    try:
        jitter_minutes = int(jitter_minutes) if jitter_minutes else 0
    except Exception:
        jitter_minutes = 0
    if jitter_minutes < 0 or jitter_minutes > 720:
        return False, "Jitter harus 0-720 menit (max 12 jam)"
    sch_id = _uuid.uuid4().hex[:12]
    next_run = _compute_next_run(schedule_type, schedule_value, jitter_minutes=jitter_minutes)
    doc = {
        "id": sch_id,
        "owner_user_id": owner_user_id,
        "automation_id": automation_id,
        "automation_name": automation_name,
        "schedule_type": schedule_type,
        "schedule_value": str(schedule_value) if schedule_type == "daily" else int(schedule_value),
        "jitter_minutes": jitter_minutes,
        "target": target,
        "akun_scope": akun_scope,
        "akun_value": akun_value or "",
        "enabled": True,
        "last_run_at": None,
        "next_run_at": next_run.isoformat(),
        "created_at": _now_iso(),
    }
    try:
        schedule_collection.insert_one(doc)
        return True, sch_id
    except Exception as e:
        return False, f"Error simpan: {e}"

def schedule_list(owner_user_id: int):
    if schedule_collection is None:
        return []
    try:
        return list(schedule_collection.find(
            {"owner_user_id": owner_user_id}, {"_id": 0}
        ).sort("created_at", 1))
    except Exception:
        return []

def schedule_toggle(owner_user_id: int, sch_id: str):
    """Toggle enabled. Return (sukses, new_enabled_value)."""
    if schedule_collection is None:
        return False, False
    try:
        doc = schedule_collection.find_one(
            {"owner_user_id": owner_user_id, "id": sch_id}, {"_id": 0}
        )
        if not doc:
            return False, False
        new_val = not doc.get("enabled", True)
        update = {"enabled": new_val}
        if new_val:
            nr = _compute_next_run(
                doc["schedule_type"], doc["schedule_value"],
                jitter_minutes=int(doc.get("jitter_minutes", 0) or 0),
            )
            update["next_run_at"] = nr.isoformat()
        schedule_collection.update_one(
            {"owner_user_id": owner_user_id, "id": sch_id},
            {"$set": update},
        )
        return True, new_val
    except Exception:
        return False, False

def schedule_delete(owner_user_id: int, sch_id: str) -> bool:
    if schedule_collection is None:
        return False
    try:
        res = schedule_collection.delete_one(
            {"owner_user_id": owner_user_id, "id": sch_id}
        )
        return res.deleted_count > 0
    except Exception:
        return False

async def _trigger_schedule(sch: dict, bot_ref):
    """Trigger 1x run untuk jadwal (dipanggil dari scheduler_loop)."""
    owner_user_id = sch["owner_user_id"]
    sch_id = sch["id"]
    auto = automation_get(owner_user_id, sch["automation_id"])
    if auto is None:
        try:
            schedule_collection.update_one(
                {"id": sch_id},
                {"$set": {"enabled": False, "last_error": "automation tidak ditemukan"}},
            )
        except Exception:
            pass
        return

    akun_list = _resolve_akun_for_schedule(sch.get("akun_scope", "all"), sch.get("akun_value", ""))
    if not akun_list:
        try:
            schedule_collection.update_one(
                {"id": sch_id},
                {"$set": {"last_error": "tidak ada akun aktif saat trigger",
                          "last_run_at": _now_iso()}},
            )
        except Exception:
            pass
        if bot_ref is not None:
            try:
                await bot_ref.send_message(
                    chat_id=owner_user_id,
                    text=f"⚠️ Jadwal *{sch.get('automation_name', '')}* dibatalkan — tidak ada akun aktif.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        # Advance next_run supaya tidak retry terus
        try:
            nr = _compute_next_run(
                sch["schedule_type"], sch["schedule_value"],
                jitter_minutes=int(sch.get("jitter_minutes", 0) or 0),
            )
            schedule_collection.update_one({"id": sch_id}, {"$set": {"next_run_at": nr.isoformat()}})
        except Exception:
            pass
        return

    async def _on_complete(info):
        logs = info.get("log_lines", [])
        stats_list = info.get("stats_list", [])
        stats_text = format_run_stats_summary(stats_list)
        summary = (
            f"🏁 *JADWAL SELESAI*\n\n"
            f"📋 {info.get('name')}\n"
            f"🆔 Jadwal: `{sch_id}`\n"
            f"👥 Akun: {info.get('accounts_count')}\n\n"
            f"{stats_text}\n\n"
            f"*Log ({len(logs)} entri):*\n" + join_lines_truncate(logs[-40:], 1800)
        )
        if bot_ref is not None:
            try:
                await bot_ref.send_message(chat_id=owner_user_id, text=summary, parse_mode="Markdown")
            except Exception:
                try:
                    await bot_ref.send_message(chat_id=owner_user_id, text=summary)
                except Exception:
                    pass

    try:
        # Ambil setting automation dari user (owner) via PTB Application bot_data fallback ke default
        _auto_batch = 0
        _auto_adelay = 0
        try:
            _app = globals().get("_bot_app") or globals().get("application")
            if _app is not None and hasattr(_app, "user_data"):
                _u = _app.user_data.get(owner_user_id, {}) if isinstance(_app.user_data, dict) else {}
                _s = (_u or {}).get("settings", {}) if isinstance(_u, dict) else {}
                _auto_batch = int(_s.get("auto_parallel_batch", 0) or 0)
                _auto_adelay = int(_s.get("auto_account_delay", 0) or 0)
        except Exception:
            _auto_batch, _auto_adelay = 0, 0
        run_id, _logs, _ce = start_automation_run(
            automation=auto,
            akun_list=akun_list,
            target=sch["target"],
            loop_count=1,
            loop_delay=0,
            owner_user_id=owner_user_id,
            completion_callback=_on_complete,
            parallel_batch=_auto_batch,
            account_delay=_auto_adelay,
        )
        now = datetime.now()
        next_run = _compute_next_run(
            sch["schedule_type"], sch["schedule_value"],
            base_dt=now, jitter_minutes=int(sch.get("jitter_minutes", 0) or 0),
        )
        schedule_collection.update_one(
            {"id": sch_id},
            {"$set": {"last_run_at": now.isoformat(),
                      "next_run_at": next_run.isoformat(),
                      "last_run_id": run_id}},
        )
        log_action("schedule_trigger", {
            "schedule_id": sch_id, "automation_id": sch["automation_id"],
            "accounts": len(akun_list), "run_id": run_id,
        })
        if bot_ref is not None:
            try:
                await bot_ref.send_message(
                    chat_id=owner_user_id,
                    text=(
                        f"▶️ *JADWAL DIPICU*\n\n"
                        f"📋 {auto.get('name')}\n"
                        f"🎯 @{sch.get('target')}\n"
                        f"👥 {len(akun_list)} akun\n"
                        f"🆔 Run: `{run_id}`\n"
                        f"⏭️ Jadwal berikutnya: `{next_run.strftime('%Y-%m-%d %H:%M:%S')}`"
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass
    except Exception as e:
        try:
            schedule_collection.update_one(
                {"id": sch_id},
                {"$set": {"last_error": str(e)[:300]}},
            )
        except Exception:
            pass

async def scheduler_loop(bot_ref):
    """Background task: cek semua jadwal setiap SCHEDULE_POLL_INTERVAL detik."""
    await asyncio.sleep(3)
    while True:
        try:
            if schedule_collection is not None:
                now_iso = datetime.now().isoformat()
                try:
                    due = await db_find(schedule_collection, {                        "enabled": True,
                        "next_run_at": {"$lte": now_iso},
                    }, {"_id": 0})
                except Exception:
                    due = []
                for sch in due:
                    try:
                        await _trigger_schedule(sch, bot_ref)
                    except Exception as e:
                        log_action("schedule_trigger_error", {"id": sch.get("id"), "error": str(e)[:200]})
        except Exception as e:
            log_action("scheduler_loop_error", {"error": str(e)[:200]})
        await asyncio.sleep(SCHEDULE_POLL_INTERVAL)

def get_submenu_schedule_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ Buat Jadwal", callback_data="sub_sch_create"),
         InlineKeyboardButton("📋 Daftar Jadwal", callback_data="sub_sch_list")],
        [InlineKeyboardButton("🔀 Toggle ON/OFF", callback_data="sub_sch_toggle"),
         InlineKeyboardButton("🗑️ Hapus Jadwal", callback_data="sub_sch_delete")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="sub_back_automation")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_submenu_schedule_keyboard():
    return _make_keyboard(SUBMENU_SCHEDULE)

def get_sch_mode_keyboard():
    return _make_keyboard(SCH_MODE_BUTTONS)

def _stats_schedule_count(user_id):
    try:
        return schedule_collection.count_documents({"owner_user_id": user_id, "enabled": True}) if schedule_collection is not None else 0
    except Exception:
        return 0

async def _sch_ask_target(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    await update.message.reply_text(
        "🎯 Masukkan *target chat* (username bot/grup/user, contoh: `@bot_username`):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_SCH_TARGET

async def _show_sch_confirm(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    data = context.user_data.get("sch_new") or {}
    st = data.get("schedule_type")
    sv = data.get("schedule_value")
    jm = int(data.get("jitter_minutes", 0) or 0)
    if st == "daily":
        jitter_txt = f" 🎲 ±{jm} menit" if jm > 0 else ""
        mode = f"📅 Harian pukul `{sv}`{jitter_txt}"
    else:
        mode = f"⏱️ Interval {sv}s"
    scope = data.get("akun_scope", "all")
    scope_val = data.get("akun_value", "")
    scope_label = {"all": "semua akun aktif", "count": f"{scope_val} akun",
                   "tag": f"tag:{scope_val}"}.get(scope, scope)
    lines = [
        "📅 *KONFIRMASI JADWAL BARU*\n",
        f"📋 Automation: *{data.get('automation_name', '')}*",
        f"🗓️ Mode: {mode}",
        f"🎯 Target: `@{data.get('target', '')}`",
        f"👥 Akun: {scope_label}",
        "🔁 Loop per trigger: *1x*",
        "",
        "Tekan *✅ Ya, lanjutkan* untuk simpan, atau 🔙 untuk batal.",
    ]
    await update.message.reply_text(
        "\n".join(lines), reply_markup=get_confirm_keyboard(), parse_mode="Markdown"
    )
    return STATE_SCH_CONFIRM

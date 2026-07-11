from __future__ import annotations
from ..keyboards import *
from ..database import *
from ..telegram_client import *
from ..ux import *
from ..states import *
from ..config import *
from ..config import ADMIN_USER_IDS, BOT_TOKEN, MONGO_URL
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from ..database import schedule_collection, db_count, db_find
from .common import *
def format_schedule_preview(sch: dict) -> str:
    st = sch.get("schedule_type")
    sv = sch.get("schedule_value")
    jm = int(sch.get("jitter_minutes", 0) or 0)
    jitter_suffix = f" 🎲±{jm}m" if jm > 0 else ""
    if st == "daily":
        mode = f"📅 Harian pukul `{sv}`{jitter_suffix}"
    elif st == "interval":
        mode = f"⏱️ Interval {sv}s"
    else:
        mode = f"{st} {sv}"
    enabled = "🟢 ON" if sch.get("enabled", True) else "🔴 OFF"
    last = sch.get("last_run_at") or "-"
    nxt = sch.get("next_run_at") or "-"
    scope = sch.get("akun_scope", "all")
    scope_val = sch.get("akun_value", "")
    scope_label = {"all": "semua", "count": f"{scope_val} akun", "tag": f"tag:{scope_val}"}.get(scope, scope)
    return (
        f"{enabled} *{sch.get('automation_name', '')}*\n"
        f"   {mode}\n"
        f"   🎯 @{sch.get('target', '')} • 👥 {scope_label}\n"
        f"   ⏭️ next: `{nxt[:19] if nxt != '-' else '-'}`\n"
        f"   🕐 last: `{last[:19] if last != '-' else '-'}`\n"
        f"   🆔 `{sch.get('id', '')}`"
    )

async def q_bot_sch_mode(update, context): return await bot_inline_opt_bridge(update, context, bot_sch_mode)

async def q_bot_sch_confirm(update, context): return await bot_inline_opt_bridge(update, context, bot_sch_confirm)

async def q_bot_sch_toggle_pilih(update, context): return await bot_inline_opt_bridge(update, context, bot_sch_toggle_pilih)

async def q_bot_sch_delete_pilih(update, context): return await bot_inline_opt_bridge(update, context, bot_sch_delete_pilih)

async def bot_sch_mulai_buat(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Mulai buat jadwal: pilih automation dulu."""
    user_id = update.effective_user.id
    items = automation_list(user_id)
    if not items:
        await bot_send_main_menu(update, context, "📋 Belum ada automation. Buat dulu lewat *🤖 Automation → ➕ Buat Automation*.")
        return STATE_MAIN_MENU
    context.user_data["sch_new"] = {}
    context.user_data["sch_auto_list"] = items
    lines = ["📅 *BUAT JADWAL BARU*\n", "Pilih automation yang akan dijadwalkan (balas *nomor urut*):\n"]
    for i, a in enumerate(items, 1):
        lines.append(f"{i}. {a.get('name', '')} — {len(a.get('steps', []))} step")
    await update.message.reply_text(
        "\n".join(lines), reply_markup=get_cancel_keyboard(), parse_mode="Markdown"
    )
    return STATE_SCH_PILIH_AUTO

async def bot_sch_pilih_auto(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        context.user_data.pop("sch_new", None)
        return await handle_cancel(update, context)
    items = context.user_data.get("sch_auto_list", [])
    if not pesan.isdigit():
        await update.message.reply_text("❌ Masukkan nomor urut yang valid:", reply_markup=get_cancel_keyboard())
        return STATE_SCH_PILIH_AUTO
    idx = int(pesan) - 1
    if idx < 0 or idx >= len(items):
        await update.message.reply_text("❌ Nomor di luar range.", reply_markup=get_cancel_keyboard())
        return STATE_SCH_PILIH_AUTO
    auto = items[idx]
    context.user_data["sch_new"]["automation_id"] = auto["id"]
    context.user_data["sch_new"]["automation_name"] = auto["name"]
    await update.message.reply_text(
        f"✅ Automation dipilih: *{auto['name']}*\n\nPilih *mode jadwal*:",
        reply_markup=get_sch_mode_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_SCH_MODE

async def bot_sch_mode(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        context.user_data.pop("sch_new", None)
        return await handle_cancel(update, context)
    if pesan.startswith("📅"):
        context.user_data["sch_new"]["schedule_type"] = "daily"
        await update.message.reply_text(
            "🕐 Masukkan *jam* dalam format `HH:MM` (24 jam)\n\n"
            "Contoh: `08:30` (setiap hari jam 08:30)\n"
            "Contoh: `23:00` (setiap hari jam 11 malam)",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_SCH_TIME_VALUE
    if pesan.startswith("⏱️"):
        context.user_data["sch_new"]["schedule_type"] = "interval"
        await update.message.reply_text(
            "⏱️ Masukkan *interval dalam detik* (minimal 5, maksimal 2.592.000 / 30 hari)\n\n"
            "Contoh: `60` (tiap 1 menit)\n"
            "Contoh: `3600` (tiap 1 jam)\n"
            "Contoh: `86400` (tiap 24 jam)",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_SCH_TIME_VALUE
    await update.message.reply_text("❓ Pilih salah satu mode.", reply_markup=get_sch_mode_keyboard())
    return STATE_SCH_MODE

async def bot_sch_time_value(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        context.user_data.pop("sch_new", None)
        return await handle_cancel(update, context)
    st = context.user_data["sch_new"].get("schedule_type")
    if st == "daily":
        if _parse_hhmm(pesan) is None:
            await update.message.reply_text(
                "❌ Format jam salah. Gunakan `HH:MM` (contoh: `08:30`):",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown",
            )
            return STATE_SCH_TIME_VALUE
        context.user_data["sch_new"]["schedule_value"] = pesan
        # Lanjut tanya jitter (khusus mode daily)
        await update.message.reply_text(
            "🎲 *Randomize Time (Jitter)*\n\n"
            "Tambahkan offset acak ± X menit supaya jadwal tidak terlalu kaku "
            "(mengurangi deteksi pola otomatis oleh bot target).\n\n"
            "Masukkan angka menit (0 = nonaktif, max 720):\n"
            "• `0` — tanpa jitter (jam persis)\n"
            "• `5` — acak dalam rentang ±5 menit\n"
            "• `30` — acak dalam rentang ±30 menit",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_SCH_JITTER
    else:
        # interval mode
        if not pesan.isdigit():
            await update.message.reply_text("❌ Harus angka detik. Coba lagi:",
                                            reply_markup=get_cancel_keyboard())
            return STATE_SCH_TIME_VALUE
        iv = int(pesan)
        if iv < 5 or iv > 86400 * 30:
            await update.message.reply_text(
                "❌ Interval harus 5 detik s/d 30 hari (2.592.000 detik):",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_SCH_TIME_VALUE
        context.user_data["sch_new"]["schedule_value"] = iv
        context.user_data["sch_new"]["jitter_minutes"] = 0
        return await _sch_ask_target(update, context)

async def bot_sch_jitter(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        context.user_data.pop("sch_new", None)
        return await handle_cancel(update, context)
    if not pesan.isdigit():
        await update.message.reply_text(
            "❌ Harus angka menit (0-720). Coba lagi:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_SCH_JITTER
    jm = int(pesan)
    if jm < 0 or jm > 720:
        await update.message.reply_text(
            "❌ Jitter harus 0-720 menit (max 12 jam). Coba lagi:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_SCH_JITTER
    context.user_data["sch_new"]["jitter_minutes"] = jm
    if jm > 0:
        await update.message.reply_text(
            f"✅ Jitter diatur: ±{jm} menit",
        )
    return await _sch_ask_target(update, context)

async def bot_sch_target(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        context.user_data.pop("sch_new", None)
        return await handle_cancel(update, context)
    if not pesan:
        await update.message.reply_text("❌ Target tidak boleh kosong.", reply_markup=get_cancel_keyboard())
        return STATE_SCH_TARGET
    context.user_data["sch_new"]["target"] = pesan.lstrip("@")
    try:
        akun_count = await db_count(collection, {})
    except Exception:
        akun_count = 0
    if akun_count == 0:
        await bot_send_main_menu(update, context, "⚠️ Tidak ada akun tersimpan. Tambah akun dulu.")
        context.user_data.pop("sch_new", None)
        return STATE_MAIN_MENU
    context.user_data["sch_new"]["_akun_count"] = akun_count
    await update.message.reply_text(
        f"👥 Pilih *akun* yang akan menjalankan saat jadwal aktif (total: {akun_count} akun):",
        reply_markup=get_auto_run_akun_scope_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_SCH_AKUN_SCOPE

async def bot_sch_confirm(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip().lower()
    if pesan.startswith("🔙"):
        context.user_data.pop("sch_new", None)
        return await handle_cancel(update, context)
    if not (pesan.startswith("✅") or "ya, lanjutkan" in pesan or pesan in ("ya", "y", "yes", "oke", "ok")):
        await update.message.reply_text(
            "❓ Tekan *✅ Ya, lanjutkan* untuk simpan atau 🔙 untuk batal.",
            reply_markup=get_confirm_keyboard(), parse_mode="Markdown",
        )
        return STATE_SCH_CONFIRM
    data = context.user_data.get("sch_new") or {}
    user_id = update.effective_user.id
    ok, result = schedule_save(
        owner_user_id=user_id,
        automation_id=data["automation_id"],
        automation_name=data["automation_name"],
        schedule_type=data["schedule_type"],
        schedule_value=data["schedule_value"],
        target=data["target"],
        akun_scope=data["akun_scope"],
        akun_value=data.get("akun_value", ""),
        jitter_minutes=int(data.get("jitter_minutes", 0) or 0),
    )
    context.user_data.pop("sch_new", None)
    context.user_data.pop("sch_auto_list", None)
    if ok:
        # Tampilkan preview
        sch_doc = await db_find_one(schedule_collection, {"id": result}, {"_id": 0}) if schedule_collection is not None else None
        preview = format_schedule_preview(sch_doc) if sch_doc else f"Jadwal `{result}` tersimpan."
        await bot_send_main_menu(
            update, context,
            f"✅ Jadwal berhasil disimpan!\n\n{preview}"
            + build_next_steps(["Lihat Daftar Jadwal", "Buat jadwal lain", "Kembali ke menu"]),
        )
    else:
        await bot_send_main_menu(update, context, f"❌ Gagal simpan jadwal: {result}")
    return STATE_MAIN_MENU

async def bot_sch_daftar(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    user_id = update.effective_user.id
    items = schedule_list(user_id)
    if not items:
        await bot_send_main_menu(update, context, "📋 Belum ada jadwal yang tersimpan.")
        return STATE_MAIN_MENU
    lines = [f"📋 *DAFTAR JADWAL* (Total: {len(items)})\n"]
    for i, sch in enumerate(items, 1):
        lines.append(f"{i}. {format_schedule_preview(sch)}\n")
    await bot_send_main_menu(update, context, join_lines_truncate(lines))
    return STATE_MAIN_MENU

async def bot_sch_toggle_menu(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    user_id = update.effective_user.id
    items = schedule_list(user_id)
    if not items:
        await bot_send_main_menu(update, context, "📋 Belum ada jadwal untuk di-toggle.")
        return STATE_MAIN_MENU
    context.user_data["sch_toggle_list"] = items
    lines = ["🔀 *TOGGLE ON/OFF JADWAL*\n", "Balas *nomor urut* untuk membalik status ON↔OFF:\n"]
    for i, sch in enumerate(items, 1):
        status = "🟢 ON" if sch.get("enabled", True) else "🔴 OFF"
        st = sch.get("schedule_type")
        sv = sch.get("schedule_value")
        mode = f"pukul {sv}" if st == "daily" else f"{sv}s"
        lines.append(f"{i}. {status} — *{sch.get('automation_name', '')}* — {mode}")
    await update.message.reply_text("\n".join(lines), reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    return STATE_SCH_TOGGLE_PILIH

async def bot_sch_toggle_pilih(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    items = context.user_data.get("sch_toggle_list", [])
    if not pesan.isdigit():
        await update.message.reply_text("❌ Masukkan nomor urut.", reply_markup=get_cancel_keyboard())
        return STATE_SCH_TOGGLE_PILIH
    idx = int(pesan) - 1
    if idx < 0 or idx >= len(items):
        await update.message.reply_text("❌ Nomor di luar range.", reply_markup=get_cancel_keyboard())
        return STATE_SCH_TOGGLE_PILIH
    sch = items[idx]
    user_id = update.effective_user.id
    ok, new_val = schedule_toggle(user_id, sch["id"])
    if ok:
        status = "🟢 ON" if new_val else "🔴 OFF"
        await bot_send_main_menu(update, context,
                                 f"✅ Jadwal *{sch.get('automation_name', '')}* sekarang {status}.")
    else:
        await bot_send_main_menu(update, context, "❌ Gagal toggle jadwal.")
    return STATE_MAIN_MENU

async def bot_sch_delete_menu(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    user_id = update.effective_user.id
    items = schedule_list(user_id)
    if not items:
        await bot_send_main_menu(update, context, "📋 Belum ada jadwal untuk dihapus.")
        return STATE_MAIN_MENU
    context.user_data["sch_delete_list"] = items
    lines = ["🗑️ *HAPUS JADWAL*\n", "Balas *nomor urut* yang ingin dihapus:\n"]
    for i, sch in enumerate(items, 1):
        status = "🟢" if sch.get("enabled", True) else "🔴"
        st = sch.get("schedule_type")
        sv = sch.get("schedule_value")
        mode = f"pukul {sv}" if st == "daily" else f"{sv}s"
        lines.append(f"{i}. {status} *{sch.get('automation_name', '')}* — {mode}")
    await update.message.reply_text("\n".join(lines), reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
    return STATE_SCH_DELETE_PILIH

async def bot_sch_delete_pilih(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    items = context.user_data.get("sch_delete_list", [])
    if not pesan.isdigit():
        await update.message.reply_text("❌ Masukkan nomor urut.", reply_markup=get_cancel_keyboard())
        return STATE_SCH_DELETE_PILIH
    idx = int(pesan) - 1
    if idx < 0 or idx >= len(items):
        await update.message.reply_text("❌ Nomor di luar range.", reply_markup=get_cancel_keyboard())
        return STATE_SCH_DELETE_PILIH
    sch = items[idx]
    ok = schedule_delete(update.effective_user.id, sch["id"])
    if ok:
        await bot_send_main_menu(update, context,
                                 f"✅ Jadwal *{sch.get('automation_name', '')}* berhasil dihapus.")
    else:
        await bot_send_main_menu(update, context, "❌ Gagal hapus jadwal.")
    return STATE_MAIN_MENU

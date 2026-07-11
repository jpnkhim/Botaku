from __future__ import annotations
from ..keyboards import *
from ..database import *
from ..telegram_client import *
from ..ux import *
from ..states import *
import asyncio
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from ..database import collection, db_count, db_find
from ..config import ADMIN_USER_IDS
from .common import is_admin, get_cancel_keyboard, get_confirm_keyboard, get_paginated_accounts_keyboard, safe_edit_query_message
from ..ux import ICON
async def ambil_pesan_terbaru_text(api_id, api_hash, string_sesi, group_id, jumlah_pesan=5):
    """
    Versi khusus untuk bot Telegram.
    Mengembalikan teks berisi daftar pesan terbaru agar bisa dikirim ke chat.
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
            return f"❌ Gagal connect: {connect_err}"
        
        entity = await safe_telegram_operation(klien.get_entity(group_id), timeout=TELEGRAM_OP_TIMEOUT)
        messages = await safe_telegram_operation(klien.get_messages(entity, limit=jumlah_pesan), timeout=TELEGRAM_OP_TIMEOUT)

        if not messages:
            return "⚠️ Tidak ada pesan ditemukan."

        lines = [f"📨 Pesan Terbaru (Total: {len(messages)})"]
        for idx, message in enumerate(messages, 1):
            isi = message.text if message.text else "<non-teks / media>"
            lines.append(f"{idx}. {message.date} — {isi}")

        return "\n".join(lines)
    except asyncio.TimeoutError:
        return "❌ Timeout saat mengambil pesan (akun mungkin bermasalah)"
    except (ConnectionError, OSError) as e:
        return f"❌ Connection error: {e}"
    except Exception as e:
        return f"❌ Error saat mengambil pesan: {e}"
    finally:
        await safe_disconnect(klien)

async def bot_otp_pilih_akun(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    
    # Check untuk cancel
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    
    akun_list = context.user_data.get("otp_akun_list") or []
    text = pesan

    if not akun_list:
        await bot_send_main_menu(
            update,
            context,
            "⚠️ Data akun tidak tersedia. Silakan ulangi dari menu OTP.",
        )
        return STATE_MAIN_MENU

    try:
        idx = int(text) - 1
    except ValueError:
        await update.message.reply_text(
            "❌ Input harus berupa angka.\nMasukkan *nomor urut akun* lagi:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_OTP_PILIH_AKUN

    if idx < 0 or idx >= len(akun_list):
        await update.message.reply_text(
            "❌ Nomor di luar jangkauan.\nMasukkan nomor yang benar:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_OTP_PILIH_AKUN

    akun = akun_list[idx]
    context.user_data["otp_selected_akun"] = akun

    await update.message.reply_text(
        "📱 Masukkan *Chat ID* atau *Username* sumber pesan.\n"
        "Kosongkan untuk default `777000` (OTP Telegram resmi).",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_OTP_CHAT_ID

async def bot_otp_chat_id(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    
    # Check untuk cancel
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    
    group_input = pesan
    last_group_id = context.user_data.get("last_otp_group_id")

    if not group_input:
        group_id = last_group_id if last_group_id is not None else 777000
    else:
        if group_input.isdigit() or (group_input.startswith("-") and group_input[1:].isdigit()):
            group_id = int(group_input)
        else:
            if group_input.startswith("@"):
                group_input = group_input[1:]
            group_id = group_input

    context.user_data["otp_group_id"] = group_id

    await update.message.reply_text(
        "📊 Berapa *jumlah pesan* yang ingin diambil? (1-20, default sesuai pengaturan):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_OTP_JUMLAH

async def bot_otp_jumlah(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    
    # Check untuk cancel
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    
    jumlah_input = pesan
    settings = get_user_settings(context)

    if not jumlah_input:
        jumlah_pesan = settings["otp_default"]
    else:
        try:
            jumlah_pesan = int(jumlah_input)
        except ValueError:
            await update.message.reply_text(
                "❌ Input harus berupa angka.\nMasukkan jumlah pesan lagi:",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown",
            )
            return STATE_OTP_JUMLAH

        if jumlah_pesan < 1 or jumlah_pesan > 20:
            await update.message.reply_text(
                "⚠️ Jumlah pesan harus antara 1-20. Masukkan lagi:",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown",
            )
            return STATE_OTP_JUMLAH

    akun = context.user_data.get("otp_selected_akun")
    group_id = context.user_data.get("otp_group_id")

    if not akun or group_id is None:
        await bot_send_main_menu(
            update,
            context,
            "⚠️ Data tidak lengkap. Silakan ulangi dari menu OTP.",
        )
        return STATE_MAIN_MENU

    context.user_data["otp_jumlah"] = jumlah_pesan
    await update.message.reply_text(
        f"📦 *RINGKASAN OTP*\n\n"
        f"📱 Akun: {akun.get('nomor_telepon', 'N/A')}\n"
        f"💬 Chat/Grup: {group_id}\n"
        f"📊 Jumlah pesan: {jumlah_pesan}\n\n"
        f"Konfirmasi untuk melanjutkan.",
        reply_markup=get_confirm_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_OTP_CONFIRM

async def bot_otp_confirm(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    akun = context.user_data.get("otp_selected_akun")
    group_id = context.user_data.get("otp_group_id")
    jumlah_pesan = context.user_data.get("otp_jumlah")

    if not akun or group_id is None or jumlah_pesan is None:
        await bot_send_main_menu(update, context, "⚠️ Data tidak lengkap. Silakan ulangi.")
        return STATE_MAIN_MENU

    await update.message.reply_text("⏳ Mengambil pesan... Mohon tunggu sebentar.")

    text_hasil = await ambil_pesan_terbaru_text(
        akun["api_id"],
        akun["api_hash"],
        akun["string_sesi"],
        group_id,
        jumlah_pesan,
    )

    if len(text_hasil) > 4000:
        text_hasil = text_hasil[:4000] + "\n\n(⚠️ Dipotong karena terlalu panjang)"

    context.user_data["last_otp_group_id"] = group_id
    set_last_action(
        context,
        "otp",
        {"akun": akun, "group_id": group_id, "jumlah_pesan": jumlah_pesan},
    )
    log_action(
        "ambil_otp",
        {
            "nomor_telepon": akun.get("nomor_telepon"),
            "group_id": group_id,
            "jumlah_pesan": jumlah_pesan,
        },
    )

    await bot_send_main_menu(update, context, text_hasil + build_next_steps(["Ambil OTP lagi", "Kembali ke menu"]))
    return STATE_MAIN_MENU

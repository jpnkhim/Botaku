from __future__ import annotations
from ..keyboards import *
from ..database import *
from ..telegram_client import *
from ..ux import *
from ..states import *
from ..config import *
from ..config import ADMIN_USER_IDS, BOT_TOKEN, MONGO_URL
from telegram import Update
from telegram.ext import ContextTypes
from .common import *
def get_submenu_settings_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("⚙️ Pengaturan", callback_data="sub_settings_opt"),
         InlineKeyboardButton("🔍 Test Database", callback_data="sub_settings_testdb")],
        [InlineKeyboardButton("🔘 Ambil ID Button", callback_data="sub_settings_btnid")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="sub_back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_submenu_settings_keyboard():
    return _make_keyboard(SUBMENU_SETTINGS)

def get_settings_menu_keyboard():
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in SETTINGS_MENU_BUTTONS],
        resize_keyboard=True,
    )

def get_user_settings(context: "ContextTypes.DEFAULT_TYPE"):
    settings = context.user_data.get("settings") or {}
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)
    return merged

def set_user_settings(context: "ContextTypes.DEFAULT_TYPE", key: str, value):
    settings = context.user_data.get("settings") or {}
    settings[key] = value
    context.user_data["settings"] = settings

async def bot_settings_menu(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    settings = get_user_settings(context)
    auto_batch = settings.get("auto_parallel_batch", 0)
    auto_batch_label = "SEMUA serentak" if auto_batch == 0 else f"{auto_batch} akun/batch"
    text = (
        "⚙️ *PENGATURAN*\n\n"
        f"1️⃣ Default jumlah OTP: {settings['otp_default']}\n"
        f"2️⃣ Delay kirim pesan (detik): {settings['kirim_delay']}\n"
        f"3️⃣ Delay join grup (detik): {settings['join_delay']}\n"
        f"4️⃣ Interval progres (akun): {settings['progress_step']}\n"
        f"5️⃣ Batch paralel (akun/batch): {settings['parallel_batch']}\n"
        f"6️⃣ Automation — batch paralel: {auto_batch_label}\n"
        f"7️⃣ Automation — delay antar akun: {settings.get('auto_account_delay', 0)} detik\n\n"
        "Pilih pengaturan yang ingin diubah menggunakan tombol di bawah."
    )
    await update.message.reply_text(
        text,
        reply_markup=get_settings_menu_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_SETTINGS_MENU

async def bot_settings_choice(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    # Map tombol → nomor pilihan
    pilihan = None
    for n in ("1", "2", "3", "4", "5", "6", "7"):
        if pesan.startswith(n):
            pilihan = n
            break

    if pilihan is None:
        await update.message.reply_text(
            "❌ Pilihan tidak valid. Gunakan tombol di bawah:",
            reply_markup=get_settings_menu_keyboard(),
        )
        return STATE_SETTINGS_MENU

    context.user_data["settings_choice"] = pilihan
    hint = ""
    if pilihan == "6":
        hint = "\n\n_Masukkan `0` untuk SEMUA akun serentak, atau angka 1-50 untuk batch paralel._"
    elif pilihan == "7":
        hint = "\n\n_Masukkan `0` untuk tidak ada delay, atau angka 1-300 detik._"
    await update.message.reply_text(
        f"Masukkan nilai baru:{hint}",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_SETTINGS_VALUE

async def bot_settings_value(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    pilihan = context.user_data.get("settings_choice")
    if pilihan not in {"1", "2", "3", "4", "5", "6", "7"}:
        await bot_send_main_menu(update, context, "⚠️ Pengaturan tidak valid. Silakan ulangi.")
        return STATE_MAIN_MENU

    if not pesan.isdigit():
        await update.message.reply_text(
            "❌ Input harus berupa angka. Masukkan nilai lagi:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_SETTINGS_VALUE

    value = int(pesan)
    if pilihan == "1":
        if value < 1 or value > 20:
            await update.message.reply_text(
                "⚠️ Nilai harus antara 1-20. Masukkan lagi:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_SETTINGS_VALUE
        set_user_settings(context, "otp_default", value)
    elif pilihan == "2":
        if value < 0 or value > 30:
            await update.message.reply_text(
                "⚠️ Nilai harus antara 0-30. Masukkan lagi:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_SETTINGS_VALUE
        set_user_settings(context, "kirim_delay", value)
    elif pilihan == "3":
        if value < 0 or value > 60:
            await update.message.reply_text(
                "⚠️ Nilai harus antara 0-60. Masukkan lagi:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_SETTINGS_VALUE
        set_user_settings(context, "join_delay", value)
    elif pilihan == "4":
        if value < 1 or value > 50:
            await update.message.reply_text(
                "⚠️ Nilai harus antara 1-50. Masukkan lagi:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_SETTINGS_VALUE
        set_user_settings(context, "progress_step", value)
    elif pilihan == "5":
        if value < 1 or value > 20:
            await update.message.reply_text(
                "⚠️ Nilai harus antara 1-20. Masukkan lagi:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_SETTINGS_VALUE
        set_user_settings(context, "parallel_batch", value)
    elif pilihan == "6":
        if value < 0 or value > 50:
            await update.message.reply_text(
                "⚠️ Nilai harus 0 (semua serentak) atau 1-50. Masukkan lagi:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_SETTINGS_VALUE
        set_user_settings(context, "auto_parallel_batch", value)
    elif pilihan == "7":
        if value < 0 or value > 300:
            await update.message.reply_text(
                "⚠️ Nilai harus 0-300 detik. Masukkan lagi:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_SETTINGS_VALUE
        set_user_settings(context, "auto_account_delay", value)

    context.user_data.pop("settings_choice", None)
    await bot_send_main_menu(
        update,
        context,
        "✅ Pengaturan berhasil diperbarui." + build_next_steps(["Cek pengaturan lain", "Kembali ke menu"]),
    )
    return STATE_MAIN_MENU

async def bot_btnid_target(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler input target untuk Ambil ID Button."""
    pesan = (update.message.text or "").strip()

    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    if not pesan:
        await update.message.reply_text(
            "❌ Target tidak boleh kosong. Masukkan username atau chat ID:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_BTNID_TARGET

    # Parse target
    if pesan.isdigit() or (pesan.startswith("-") and pesan[1:].isdigit()):
        target = int(pesan)
    else:
        target = pesan.lstrip("@")

    context.user_data["btnid_target"] = target

    await update.message.reply_text(
        "📊 Berapa *jumlah pesan* yang ingin dipindai? (1-50, default: 10)\n\n"
        "Semakin banyak pesan, semakin besar kemungkinan menemukan inline button.",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_BTNID_JUMLAH

async def bot_btnid_jumlah(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler input jumlah pesan dan eksekusi pengambilan button ID."""
    pesan = (update.message.text or "").strip()

    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    # Default 10 jika kosong
    if not pesan:
        jumlah = 10
    else:
        try:
            jumlah = int(pesan)
        except ValueError:
            await update.message.reply_text(
                "❌ Input harus berupa angka. Masukkan jumlah pesan (1-50):",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown",
            )
            return STATE_BTNID_JUMLAH

        if jumlah < 1 or jumlah > 50:
            await update.message.reply_text(
                "⚠️ Jumlah harus antara 1-50. Masukkan lagi:",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown",
            )
            return STATE_BTNID_JUMLAH

    akun = context.user_data.get("btnid_selected_akun")
    target = context.user_data.get("btnid_target")

    if not akun or target is None:
        await bot_send_main_menu(update, context, "⚠️ Data tidak lengkap. Silakan ulangi.")
        return STATE_MAIN_MENU

    await update.message.reply_text("⏳ Memindai pesan untuk inline button... Mohon tunggu.")

    results, error = await ambil_inline_buttons_text(
        akun["api_id"],
        akun["api_hash"],
        akun["string_sesi"],
        target,
        jumlah,
    )

    if error:
        await bot_send_main_menu(update, context, error)
        return STATE_MAIN_MENU

    # Format hasil — kirim per pesan agar masing-masing info bisa di-copy
    chat_id = update.effective_chat.id

    header = (
        f"🔘 *HASIL SCAN INLINE BUTTON*\n\n"
        f"🎯 Target: `{target}`\n"
        f"📊 Pesan dipindai: {jumlah}\n"
        f"📋 Pesan dengan button: {len(results)}\n"
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=header,
        parse_mode="Markdown",
    )

    for msg_info in results:
        msg_text_preview = shorten_text(msg_info["text"], 80)

        # Header pesan
        pesan_header = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📨 *Pesan ID:* `{msg_info['msg_id']}`\n"
            f"📅 *Tanggal:* `{msg_info['date']}`\n"
            f"💬 *Preview:* {msg_text_preview}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=pesan_header,
            parse_mode="Markdown",
        )

        # Kirim setiap button sebagai pesan terpisah agar mudah di-copy
        for btn in msg_info["rows"]:
            # Header: info posisi + teks tombol (pakai Markdown)
            header_parts = [f"🔲 *Button [{btn['row']},{btn['col']}]*"]
            header_parts.append(f"📝 Teks: `{btn['text']}`")
            if btn["url"]:
                header_parts.append(f"🔗 URL: {btn['url']}")
            if not btn["callback_data"]:
                header_parts.append("🆔 Callback Data: _(tidak ada — tombol URL)_")

            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="\n".join(header_parts),
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
            except Exception:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="\n".join(header_parts),
                    disable_web_page_preview=True,
                )

            # Kirim callback_data sebagai pesan TERPISAH tanpa parse_mode
            # agar user bisa copy string persis apa adanya, termasuk
            # karakter spesial seperti `_`, `*`, `[`, `/`, backtick, dll
            # dan whitespace (leading/trailing space).
            if btn["callback_data"]:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=btn["callback_data"],
                    disable_web_page_preview=True,
                )

    log_action("ambil_button_id", {
        "akun": akun.get("nomor_telepon", "N/A"),
        "target": str(target),
        "jumlah_pesan": jumlah,
        "buttons_found": sum(len(m["rows"]) for m in results),
    })

    await bot_send_main_menu(
        update,
        context,
        f"✅ Selesai! Ditemukan *{sum(len(m['rows']) for m in results)}* button "
        f"dari *{len(results)}* pesan."
        + build_next_steps(["Scan chat lain", "Kembali ke menu"]),
    )
    return STATE_MAIN_MENU

"""
botaku.handlers.common - common helpers: is_admin, keyboards, safe_edit
"""
from __future__ import annotations
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from ..config import ADMIN_USER_IDS

logger = logging.getLogger("telekubot")

def is_admin(user_id: int) -> bool:
    if not ADMIN_USER_IDS:
        logger.warning(f"ADMIN_USER_IDS belum di-set, user {user_id} jadi admin otomatis")
        ADMIN_USER_IDS.add(user_id)
        return True
    return user_id in ADMIN_USER_IDS

def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not is_admin(user.id):
            await update.message.reply_text(
                "⛔️ Akses ditolak. Hanya admin yang dapat menggunakan bot ini.",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        return await func(update, context, *args, **kwargs)
    return wrapper

# === Keyboards ===
def get_main_menu_keyboard():
    keyboard = [
        ["📨 Kirim Pesan", "👤 Kelola Akun"],
        ["👥 Gabung Grup", "📦 Import & Export"],
        ["🤖 Automation", "🛠️ Tools & Pengaturan"],
        ["❓ Bantuan"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_categories_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("📨 Kirim Pesan", callback_data="cat_kirim"),
         InlineKeyboardButton("👤 Kelola Akun", callback_data="cat_akun")],
        [InlineKeyboardButton("👥 Gabung Grup", callback_data="cat_join"),
         InlineKeyboardButton("📦 Import & Export", callback_data="cat_export")],
        [InlineKeyboardButton("🤖 Automation", callback_data="cat_automation"),
         InlineKeyboardButton("🛠️ Tools & Pengaturan", callback_data="cat_settings")],
        [InlineKeyboardButton("❓ Bantuan", callback_data="cat_help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_submenu_kirim_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("⚡ Kirim Cepat", callback_data="sub_kirim_cepat"),
         InlineKeyboardButton("📤 Kirim Pesan", callback_data="sub_kirim_pesan")],
        [InlineKeyboardButton("📄 Kirim File TXT", callback_data="sub_kirim_file")],
        [InlineKeyboardButton("🔐 Ambil Pesan OTP", callback_data="sub_kirim_otp"),
         InlineKeyboardButton("🔁 Ulangi Aksi Terakhir", callback_data="sub_kirim_repeat")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="sub_back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard():
    return ReplyKeyboardMarkup([["🔙 Kembali"]], resize_keyboard=True)

def get_confirm_keyboard():
    return ReplyKeyboardMarkup([["✅ Ya", "❌ Tidak"], ["🔙 Kembali"]], resize_keyboard=True)

async def safe_edit_query_message(query, text: str, reply_markup=None, parse_mode="Markdown"):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.warning(f"edit_message with Markdown failed: {e}, fallback")
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)
        except Exception as e2:
            logger.error(f"edit fallback failed: {e2}")
            try:
                await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=None)
            except Exception:
                pass

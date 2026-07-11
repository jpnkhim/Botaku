from __future__ import annotations
from ..database import *
from ..telegram_client import *
from ..ux import *
from ..states import *
import logging
import asyncio
import io
import json
import random
import uuid as _uuid
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from ..config import ADMIN_USER_IDS
from ..keyboards import *
from .. import other as _other_module
from ..other import *  # membawa simpan_data, log_action, validasi_target_user, dsb
from ..automation.engine import *  # membawa automation_*, format_step_summary, build_next_steps, format_automation_preview, start_automation_run, stop_automation_run, list_running_automations, get_automation_list_keyboard
from ..automation.scheduler import *  # membawa schedule_*, _parse_hhmm, _sch_ask_target, _show_sch_confirm
logger = logging.getLogger('telekubot')
def is_admin(user_id: int) -> bool:
    """Check apakah user_id adalah admin. Jika ADMIN_USER_IDS kosong, izinkan user pertama."""
    # FIXED: global tidak diperlukan untuk mutasi set
    if not ADMIN_USER_IDS:
        print(f"⚠️ ADMIN_USER_IDS belum di-set. Menjadikan user {user_id} sebagai admin sesi ini secara otomatis.")
        ADMIN_USER_IDS.add(user_id)
        return True
    return user_id in ADMIN_USER_IDS

def admin_only(func):
    """Decorator untuk memastikan hanya admin yang bisa mengakses handler."""
    async def wrapper(update: "Update", context: "ContextTypes.DEFAULT_TYPE", *args, **kwargs):
        user = update.effective_user
        if not is_admin(user.id):
            await update.message.reply_text(
                "⛔️ Akses ditolak. Hanya admin yang dapat menggunakan bot ini.",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        return await func(update, context, *args, **kwargs)
    return wrapper

def get_categories_inline_keyboard():
    """Membuat keyboard inline untuk kategori menu utama."""
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

async def bot_inline_opt_bridge(update: "Update", context: "ContextTypes.DEFAULT_TYPE", next_handler):
    """Jembatan untuk mensimulasikan klik tombol inline sebagai input teks."""
    query = update.callback_query
    await query.answer()
    data = query.data
    text = data.split(":", 1)[1]
    
    # Mock update.message
    mock_message = query.message
    mock_message.text = text
    mock_message.from_user = query.from_user
    update.message = mock_message
    
    return await next_handler(update, context)

def get_main_menu_keyboard():
    """Membuat keyboard utama untuk bot Telegram."""
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in MAIN_MENU_BUTTONS],
        resize_keyboard=True,
    )

def get_cancel_keyboard():
    """Membuat keyboard dengan tombol cancel."""
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in CANCEL_BUTTON],
        resize_keyboard=True,
    )

def get_confirm_keyboard():
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in CONFIRM_BUTTONS],
        resize_keyboard=True,
    )

def shorten_text(value: str, max_len: int = 80):
    text = str(value or "").strip()
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return text[:max_len]
    return text[: max_len - 1] + "…"

async def bot_send_main_menu(update: "Update", context: "ContextTypes.DEFAULT_TYPE", text: str | None = None):
    """Helper kirim teks + keyboard utama atau sub-menu terakhir dengan inline keyboard interaktif."""
    chat_id = update.effective_chat.id
    content = text or "Silakan pilih menu di bawah ini:"
    if len(content) > 3900:
        content = content[:3900] + "\n\n(⚠️ Dipotong karena terlalu panjang)"

    # Pilih keyboard berdasarkan sub-menu terakhir
    last_sub = context.user_data.get("last_submenu")
    is_inline = False
    
    if last_sub == "kirim":
        kb = get_submenu_kirim_inline_keyboard()
        is_inline = True
    elif last_sub == "akun":
        kb = get_submenu_akun_inline_keyboard()
        is_inline = True
    elif last_sub == "export":
        kb = get_submenu_export_inline_keyboard()
        is_inline = True
    elif last_sub == "settings":
        kb = get_submenu_settings_inline_keyboard()
        is_inline = True
    elif last_sub == "automation":
        kb = get_submenu_automation_inline_keyboard()
        is_inline = True
    elif last_sub == "schedule":
        kb = get_submenu_schedule_inline_keyboard()
        is_inline = True
    else:
        kb = get_categories_inline_keyboard()
        is_inline = True

    last_menu_message_id = context.user_data.get("menu_message_id")
    if last_menu_message_id and is_inline:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=last_menu_message_id,
                text=content,
                reply_markup=kb,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            return
        except Exception:
            pass

    try:
        if last_sub is None:
            # Send inline categories only (no physical menu keyboard)
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=content,
                reply_markup=get_categories_inline_keyboard(),
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            context.user_data["menu_message_id"] = msg.message_id
        else:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=content,
                reply_markup=kb,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            context.user_data["menu_message_id"] = msg.message_id
    except Exception:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        context.user_data["menu_message_id"] = msg.message_id

async def handle_cancel(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler untuk tombol batal — kembali ke sub-menu terakhir atau menu utama."""
    last_sub = context.user_data.get("last_submenu")
    if last_sub:
        label_map = {
            "kirim": "Kirim Pesan",
            "akun": "Kelola Akun",
            "export": "Import & Export",
            "settings": "Tools & Pengaturan",
            "automation": "Automation",
            "schedule": "Jadwal Automation",
        }
        label = label_map.get(last_sub, "menu")
        await bot_send_main_menu(update, context, f"🔙 Kembali ke menu {label}.")
    else:
        await bot_send_main_menu(update, context, "🔙 Kembali ke menu utama.")
    return STATE_MAIN_MENU

def get_cancel_sending_keyboard():
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in CANCEL_SENDING_BUTTONS],
        resize_keyboard=True,
    )


async def safe_edit_query_message(query, text: str, reply_markup=None, parse_mode="Markdown"):
    """FIXED: Helper aman untuk edit_message_text callback query - fallback tanpa markdown jika gagal"""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.warning(f"edit_message_text dengan Markdown gagal: {e}, fallback tanpa parse_mode")
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)
        except Exception as e2:
            logger.error(f"edit_message_text fallback juga gagal: {e2}")
            # Last resort: coba kirim pesan baru
            try:
                await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=None)
            except Exception:
                pass


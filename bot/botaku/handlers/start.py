"""
botaku.handlers.start - /start & /help
"""
from __future__ import annotations
from ..keyboards import *
from ..database import *
from ..telegram_client import *
from ..ux import *
from ..states import *
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from ..config import ADMIN_USER_IDS
from ..ux import render_banner, ICON
from ..database import collection, automation_collection, schedule_collection, db_count
from .common import is_admin, get_categories_inline_keyboard

STATE_MAIN_MENU = 0

def _stats_akun_count():
    try:
        return collection.count_documents({}) if collection is not None else 0
    except Exception:
        return 0

def _stats_automation_count(user_id):
    try:
        return automation_collection.count_documents({"owner_user_id": user_id}) if automation_collection is not None else 0
    except Exception:
        return 0

def _stats_schedule_count(user_id):
    try:
        return schedule_collection.count_documents({"owner_user_id": user_id, "enabled": True}) if schedule_collection is not None else 0
    except Exception:
        return 0

async def bot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not is_admin(user.id):
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"⛔️ *Akses Ditolak*\n\nUser ID Anda: `{user.id}`\nHubungi administrator.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    msg = await context.bot.send_message(
        chat_id=chat.id,
        text=(
            f"{render_banner()}\n\n"
            f"👋 Selamat datang, *{user.first_name or 'Admin'}*!\n"
            f"{ICON['fire']} _Ready to automate._\n\n"
            f"  {ICON['users']} Akun: *{_stats_akun_count()}*\n"
            f"  {ICON['bot']} Automation: *{_stats_automation_count(user.id)}*\n\n"
            f"_Silakan pilih kategori di bawah ini._"
        ),
        reply_markup=get_categories_inline_keyboard(),
        parse_mode="Markdown",
    )
    # Hilangkan physical reply keyboard (jika pernah aktif dari versi lama)
    try:
        rm = await context.bot.send_message(
            chat_id=chat.id,
            text="⌨️ Menu interaktif diaktifkan.",
            reply_markup=ReplyKeyboardRemove(),
        )
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=rm.message_id)
        except Exception:
            pass
    except Exception:
        pass
    context.user_data["menu_message_id"] = msg.message_id
    return STATE_MAIN_MENU

async def bot_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Bantuan TeleKu Bot*\n\n"
        "Gunakan /start untuk menu utama.\n"
        "Semua tombol inline sudah di-fix untuk Koyeb.",
        parse_mode="Markdown"
    )
    return STATE_MAIN_MENU

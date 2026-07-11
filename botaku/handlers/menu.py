"""
botaku.handlers.menu - category & submenu callbacks
Fix untuk inline button tidak merespon
"""
from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from ..database import collection, db_count
from .common import is_admin, get_categories_inline_keyboard, get_submenu_kirim_inline_keyboard, safe_edit_query_message, get_cancel_keyboard

logger = logging.getLogger("telekubot")

STATE_MAIN_MENU = 0
STATE_KIRIM_TARGET = 6
STATE_KIRIM_CEPAT_TARGET = 7

async def bot_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"query.answer() gagal cat: {e}")
    data = query.data
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await safe_edit_query_message(query, "⛔️ Akses ditolak.")
        return STATE_MAIN_MENU

    if data == "cat_kirim":
        context.user_data["last_submenu"] = "kirim"
        await safe_edit_query_message(
            query,
            "📨 *MENU KIRIM PESAN*\n\nPilih fitur pengiriman:",
            reply_markup=get_submenu_kirim_inline_keyboard()
        )
        return STATE_MAIN_MENU
    # ... other categories simplified
    await safe_edit_query_message(query, f"Kategori {data} - coming soon", reply_markup=get_categories_inline_keyboard())
    return STATE_MAIN_MENU

async def bot_submenu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"query.answer() gagal sub: {e}")
    data = query.data
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await safe_edit_query_message(query, "⛔️ Akses ditolak.")
        return STATE_MAIN_MENU

    if data == "sub_back_main":
        await safe_edit_query_message(
            query,
            "✅ *KEMBALI KE MENU UTAMA*",
            reply_markup=get_categories_inline_keyboard()
        )
        return STATE_MAIN_MENU

    elif data == "sub_kirim_pesan":
        try:
            count = await db_count(collection, {})
        except Exception as e:
            logger.error(f"db_count error di sub_kirim_pesan: {e}")
            count = 0
        if count == 0:
            await safe_edit_query_message(query, "⚠️ Tidak ada akun. Tambahkan akun dahulu.")
            return STATE_MAIN_MENU
        await safe_edit_query_message(
            query,
            "📤 *KIRIM PESAN*\n\n🎯 Masukkan *username bot/user* tujuan (contoh: `@username`):",
            reply_markup=get_cancel_keyboard()
        )
        return STATE_KIRIM_TARGET

    elif data == "sub_kirim_cepat":
        await safe_edit_query_message(
            query,
            "⚡ *KIRIM CEPAT*\n\n🎯 Masukkan *username bot/user* tujuan:",
            reply_markup=get_cancel_keyboard()
        )
        return STATE_KIRIM_CEPAT_TARGET

    # ... other submenu handlers can be added modularly
    await safe_edit_query_message(query, f"Fitur {data} belum diimplementasi di versi modular - lihat telekuq_fixed.py")
    return STATE_MAIN_MENU

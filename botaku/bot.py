"""
botaku.bot - Build Telegram Application (modular)
Memisahkan ConversationHandler agar mudah fix inline button
"""
from __future__ import annotations
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters

from .config import BOT_TOKEN
from .handlers.start import bot_start, bot_help
from .handlers.menu import bot_category_callback, bot_submenu_callback
from .handlers.common import is_admin

logger = logging.getLogger("telekubot")

# States
STATE_MAIN_MENU = 0
STATE_KIRIM_TARGET = 6
STATE_KIRIM_CEPAT_TARGET = 7

async def bot_menu_router(update: Update, context):
    # Simple router for text menu
    text = (update.message.text or "").strip()
    if text == "📨 Kirim Pesan":
        from .handlers.common import get_submenu_kirim_inline_keyboard
        await update.message.reply_text("📨 *MENU KIRIM PESAN*", reply_markup=get_submenu_kirim_inline_keyboard(), parse_mode="Markdown")
        return STATE_MAIN_MENU
    await update.message.reply_text("Gunakan /start untuk menu")
    return STATE_MAIN_MENU

async def debug_all_updates(update, context):
    try:
        user = update.effective_user
        txt = update.message.text if update.message else (update.callback_query.data if update.callback_query else "no text")
        logger.info(f"DEBUG UPDATE: user={user.id if user else 'N/A'} text={str(txt)[:100]}")
    except Exception:
        pass

async def global_error_handler(update, context):
    err = context.error
    if "Conflict" in str(err):
        logger.warning(f"Conflict detected: {err} - sleep 10s")
        import asyncio
        await asyncio.sleep(10)
    else:
        logger.error(f"Error: {err}")

async def _post_init(app):
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook cleaned")
    except Exception as e:
        logger.warning(f"delete_webhook failed: {e}")

def build_application():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set!")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )

    # Fallback handlers outside ConversationHandler - FIX untuk inline button mati
    app.add_handler(CommandHandler("start", bot_start))
    app.add_handler(CommandHandler("help", bot_help))
    app.add_handler(CallbackQueryHandler(bot_category_callback, pattern=r"^cat_"))
    app.add_handler(CallbackQueryHandler(bot_submenu_callback, pattern=r"^sub_"))
    app.add_handler(MessageHandler(filters.ALL, debug_all_updates), group=0)

    # ConversationHandler modular
    conv = ConversationHandler(
        per_message=True,  # FIX untuk callback tracking
        per_chat=True,
        per_user=True,
        entry_points=[CommandHandler("start", bot_start), CommandHandler("help", bot_help)],
        states={
            STATE_MAIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot_menu_router),
                CallbackQueryHandler(bot_category_callback, pattern=r"^cat_"),
                CallbackQueryHandler(bot_submenu_callback, pattern=r"^sub_"),
            ],
            STATE_KIRIM_TARGET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: u.message.reply_text("Target ok")),
            ],
        },
        fallbacks=[CommandHandler("start", bot_start)],
    )
    app.add_handler(conv)
    app.add_error_handler(global_error_handler)

    return app

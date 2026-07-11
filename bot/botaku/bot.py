
from __future__ import annotations
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters
from telegram import Update
from .config import BOT_TOKEN
from .states import *

# Import all handlers with wildcard to ensure all 100+ funcs are available (easier for final modular)
from .handlers.accounts import *
from .handlers.automation import *
from .handlers.common import *
from .handlers.export import *
from .handlers.join import *
from .handlers.kirim import *
from .handlers.kirim_file import *
from .handlers.menu import *
from .handlers.otp import *
from .handlers.schedule import *
from .handlers.settings import *
from .handlers.start import *

import asyncio
import logging

logger = logging.getLogger("telekubot")


async def _post_init(app):
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook cleaned (final modular)")
    except Exception as e:
        logger.warning(f"delete_webhook failed: {e}")
    try:
        from .automation.scheduler import scheduler_loop
        asyncio.create_task(scheduler_loop(app.bot))
        logger.info("✅ Scheduler started (final modular)")
    except Exception as e:
        logger.warning(f"Scheduler start failed: {e}")

async def global_error_handler(update, context):
    err = context.error
    if "Conflict" in str(err):
        logger.warning(f"Conflict: {err} - sleep 10s")
        await asyncio.sleep(10)
    else:
        logger.error(f"Error: {err}")

def build_application():
    from .config import BOT_TOKEN
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set")
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )

    from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters

    async def debug_all_updates(update, context):
        try:
            user = update.effective_user
            txt = update.message.text if update.message else (update.callback_query.data if update.callback_query else "no text")
            logger.info(f"DEBUG UPDATE: user={user.id if user else 'N/A'} text={str(txt)[:100]}")
        except Exception:
            pass

    app.add_handler(MessageHandler(filters.ALL, debug_all_updates, block=False), group=-1)
    app.add_handler(CommandHandler("start", bot_start))
    app.add_handler(CommandHandler("help", bot_help))
    app.add_handler(CallbackQueryHandler(bot_category_callback, pattern=r"^cat_"))
    app.add_handler(CallbackQueryHandler(bot_submenu_callback, pattern=r"^sub_"))
    app.add_handler(CallbackQueryHandler(bot_accounts_page_callback, pattern=r"^acc_page:"))
    app.add_handler(CallbackQueryHandler(bot_accounts_action_callback, pattern=r"^acc_act:"))
    app.add_handler(CallbackQueryHandler(bot_accounts_search_callback, pattern=r"^acc_search:"))
    app.add_handler(CallbackQueryHandler(bot_accounts_search_cancel_callback, pattern=r"^acc_search_cancel:"))

    conv_handler = ConversationHandler(
                            per_message=False,
                per_chat=True,
                per_user=True,
                entry_points=[CommandHandler("start", bot_start), CommandHandler("help", bot_help)],
                states={
                    STATE_MAIN_MENU: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_menu_router),
                        CallbackQueryHandler(bot_category_callback, pattern=r"^cat_"),
                        CallbackQueryHandler(bot_submenu_callback, pattern=r"^sub_"),
                        CallbackQueryHandler(bot_accounts_page_callback, pattern=r"^acc_page:"),
                        CallbackQueryHandler(bot_accounts_action_callback, pattern=r"^acc_act:"),
                        CallbackQueryHandler(bot_accounts_search_callback, pattern=r"^acc_search:"),
                        CallbackQueryHandler(bot_accounts_search_cancel_callback, pattern=r"^acc_search_cancel:"),
                        CallbackQueryHandler(bot_delete_confirm_callback, pattern=r"^conf_delete:"),
                        CallbackQueryHandler(bot_automation_callback, pattern=r"^aut_"),
                    ],
                    STATE_TAMBAH_API_ID: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_tambah_api_id),
                    ],
                    STATE_TAMBAH_API_HASH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_tambah_api_hash),
                    ],
                    STATE_TAMBAH_SESSION: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_tambah_session),
                    ],
                    STATE_TAMBAH_LOGIN_API_ID: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_login_api_id),
                    ],
                    STATE_TAMBAH_LOGIN_API_HASH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_login_api_hash),
                    ],
                    STATE_TAMBAH_LOGIN_PHONE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_login_phone),
                    ],
                    STATE_TAMBAH_LOGIN_CODE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_login_code),
                    ],
                    STATE_TAMBAH_LOGIN_PASSWORD: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_login_password),
                    ],
                    STATE_HAPUS_AKUN: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_hapus_akun),
                        CallbackQueryHandler(bot_accounts_page_callback, pattern=r"^acc_page:"),
                        CallbackQueryHandler(bot_accounts_action_callback, pattern=r"^acc_act:"),
                        CallbackQueryHandler(bot_delete_confirm_callback, pattern=r"^conf_delete:"),
                        CallbackQueryHandler(bot_category_callback, pattern=r"^cat_"),
                        CallbackQueryHandler(bot_submenu_callback, pattern=r"^sub_"),
                    ],
                    STATE_KIRIM_TARGET: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_kirim_target),
                    ],
                    STATE_KIRIM_PILIH_AKUN: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_kirim_pilih_akun),
                    ],
                    STATE_KIRIM_PESAN: [
                        MessageHandler(filters.TEXT, bot_kirim_pesan),
                    ],
                    STATE_KIRIM_CONFIRM: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_kirim_confirm),
                        CallbackQueryHandler(q_bot_kirim_confirm, pattern=r"^menu_opt:"),
                    ],
                    STATE_KIRIM_CEPAT_TARGET: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_kirim_cepat_target),
                    ],
                    STATE_KIRIM_CEPAT_PESAN: [
                        MessageHandler(filters.TEXT, bot_kirim_cepat_pesan),
                    ],
                    STATE_KIRIM_CEPAT_SCOPE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_kirim_cepat_scope),
                        CallbackQueryHandler(q_bot_kirim_cepat_scope, pattern=r"^menu_opt:"),
                    ],
                    STATE_KIRIM_CEPAT_CONFIRM: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_kirim_cepat_confirm),
                        CallbackQueryHandler(q_bot_kirim_cepat_confirm, pattern=r"^menu_opt:"),
                    ],
                    STATE_GABUNG_GROUP: [
                        MessageHandler(filters.Document.ALL, bot_gabung_grup_document),
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_gabung_grup),
                    ],
                    STATE_GABUNG_SCOPE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_gabung_scope),
                        CallbackQueryHandler(q_bot_gabung_scope, pattern=r"^menu_opt:"),
                    ],
                    STATE_GABUNG_TAG: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_gabung_tag),
                    ],
                    STATE_GABUNG_CONFIRM: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_gabung_confirm),
                        CallbackQueryHandler(q_bot_gabung_confirm, pattern=r"^menu_opt:"),
                    ],
                    STATE_OTP_PILIH_AKUN: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_otp_pilih_akun),
                        CallbackQueryHandler(bot_accounts_page_callback, pattern=r"^acc_page:"),
                        CallbackQueryHandler(bot_accounts_action_callback, pattern=r"^acc_act:"),
                        CallbackQueryHandler(bot_category_callback, pattern=r"^cat_"),
                        CallbackQueryHandler(bot_submenu_callback, pattern=r"^sub_"),
                    ],
                    STATE_OTP_CHAT_ID: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_otp_chat_id),
                    ],
                    STATE_OTP_JUMLAH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_otp_jumlah),
                    ],
                    STATE_OTP_CONFIRM: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_otp_confirm),
                    ],
                    STATE_INFO_AKUN_PILIH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_info_akun_pilih),
                        CallbackQueryHandler(bot_accounts_page_callback, pattern=r"^acc_page:"),
                        CallbackQueryHandler(bot_accounts_action_callback, pattern=r"^acc_act:"),
                        CallbackQueryHandler(bot_category_callback, pattern=r"^cat_"),
                        CallbackQueryHandler(bot_submenu_callback, pattern=r"^sub_"),
                    ],
                    STATE_TEST_AKUN_PILIH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_test_akun_pilih),
                        CallbackQueryHandler(bot_accounts_page_callback, pattern=r"^acc_page:"),
                        CallbackQueryHandler(bot_accounts_action_callback, pattern=r"^acc_act:"),
                        CallbackQueryHandler(bot_category_callback, pattern=r"^cat_"),
                        CallbackQueryHandler(bot_submenu_callback, pattern=r"^sub_"),
                    ],
                    STATE_SEARCH_QUERY: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_search_query),
                    ],
                    STATE_TAG_PILIH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_tag_pilih),
                        CallbackQueryHandler(bot_accounts_page_callback, pattern=r"^acc_page:"),
                        CallbackQueryHandler(bot_accounts_action_callback, pattern=r"^acc_act:"),
                        CallbackQueryHandler(bot_category_callback, pattern=r"^cat_"),
                        CallbackQueryHandler(bot_submenu_callback, pattern=r"^sub_"),
                    ],
                    STATE_TAG_INPUT: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_tag_input),
                    ],
                    STATE_IMPORT_JSON_WAIT: [
                        MessageHandler(filters.Document.ALL, bot_import_json_document),
                        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cancel),
                    ],
                    STATE_SETTINGS_MENU: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_settings_choice),
                    ],
                    STATE_SETTINGS_VALUE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_settings_value),
                    ],
                    STATE_RESET_STATUS_PILIH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_reset_status_pilih),
                        CallbackQueryHandler(q_bot_reset_status_pilih, pattern=r"^menu_opt:"),
                    ],
                    STATE_RESET_STATUS_CONFIRM: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_reset_status_confirm),
                        CallbackQueryHandler(q_bot_reset_status_confirm, pattern=r"^menu_opt:"),
                    ],
                    STATE_KIRIM_FILE_TARGET: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_kirim_file_target),
                    ],
                    STATE_KIRIM_FILE_UPLOAD: [
                        MessageHandler(filters.Document.ALL, bot_kirim_file_upload),
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_kirim_file_upload),
                    ],
                    STATE_KIRIM_FILE_SCOPE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_kirim_file_scope),
                        CallbackQueryHandler(q_bot_kirim_file_scope, pattern=r"^menu_opt:"),
                    ],
                    STATE_KIRIM_FILE_CONFIRM: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_kirim_file_confirm),
                        CallbackQueryHandler(q_bot_kirim_file_confirm, pattern=r"^menu_opt:"),
                    ],
                    STATE_KIRIM_FILE_SELESAI: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_kirim_file_selesai),
                    ],
                    STATE_KIRIM_FILE_SENDING: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_kirim_file_sending),
                    ],
                    STATE_REPEAT_RUNNING: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_repeat_running),
                    ],
                    STATE_BTNID_PILIH_AKUN: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_btnid_pilih_akun),
                        CallbackQueryHandler(bot_accounts_page_callback, pattern=r"^acc_page:"),
                        CallbackQueryHandler(bot_accounts_action_callback, pattern=r"^acc_act:"),
                        CallbackQueryHandler(bot_category_callback, pattern=r"^cat_"),
                        CallbackQueryHandler(bot_submenu_callback, pattern=r"^sub_"),
                    ],
                    STATE_BTNID_TARGET: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_btnid_target),
                    ],
                    STATE_BTNID_JUMLAH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_btnid_jumlah),
                    ],
                    # ===== AUTOMATION STATES =====
                    STATE_AUTO_NAME: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_nama),
                    ],
                    STATE_AUTO_STEP_MENU: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_step_menu),
                        CallbackQueryHandler(q_bot_auto_step_menu, pattern=r"^menu_opt:"),
                    ],
                    STATE_AUTO_STEP_SEND_TEXT: [
                        MessageHandler(filters.TEXT, bot_auto_step_send_text),
                    ],
                    STATE_AUTO_STEP_DELAY_SEC: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_step_delay),
                    ],
                    STATE_AUTO_STEP_CLICK_ID: [
                        MessageHandler(filters.TEXT, bot_auto_step_click_id),
                    ],
                    STATE_AUTO_STEP_WAIT_TIMEOUT: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_step_wait),
                    ],
                    STATE_AUTO_STEP_SEND_TXT: [
                        MessageHandler(
                            filters.Document.ALL | (filters.TEXT & ~filters.COMMAND),
                            bot_auto_step_send_txt,
                        ),
                    ],
                    STATE_AUTO_STEP_SEND_TXT_RANDOM: [
                        MessageHandler(
                            filters.Document.ALL | (filters.TEXT & ~filters.COMMAND),
                            bot_auto_step_send_txt_random,
                        ),
                    ],
                    STATE_AUTO_STEP_EDIT: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_step_edit),
                    ],
                    STATE_AUTO_DELETE_PILIH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_delete_pilih),
                    ],
                    STATE_AUTO_RUN_PILIH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_run_pilih_handler),
                    ],
                    STATE_AUTO_RUN_TARGET: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_run_target),
                    ],
                    STATE_AUTO_RUN_PILIH_AKUN: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_run_pilih_akun),
                    ],
                    STATE_AUTO_RUN_LOOP_MODE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_run_loop_mode),
                        CallbackQueryHandler(q_bot_auto_run_loop_mode, pattern=r"^menu_opt:"),
                    ],
                    STATE_AUTO_RUN_LOOP_N: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_run_loop_n),
                        CallbackQueryHandler(q_bot_auto_run_loop_n, pattern=r"^menu_opt:"),
                    ],
                    STATE_AUTO_RUN_LOOP_DELAY: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_run_loop_delay),
                        CallbackQueryHandler(q_bot_auto_run_loop_delay, pattern=r"^menu_opt:"),
                    ],
                    STATE_AUTO_RUN_CONFIRM: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_run_confirm),
                        CallbackQueryHandler(q_bot_auto_run_confirm, pattern=r"^menu_opt:"),
                    ],
                    STATE_AUTO_STOP_PILIH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_auto_stop_pilih),
                    ],
                    # ===== SCHEDULE STATES =====
                    STATE_SCH_PILIH_AUTO: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_sch_pilih_auto),
                    ],
                    STATE_SCH_MODE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_sch_mode),
                        CallbackQueryHandler(q_bot_sch_mode, pattern=r"^menu_opt:"),
                    ],
                    STATE_SCH_TIME_VALUE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_sch_time_value),
                    ],
                    STATE_SCH_JITTER: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_sch_jitter),
                    ],
                    STATE_SCH_TARGET: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_sch_target),
                    ],
                    STATE_SCH_AKUN_SCOPE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_sch_akun_scope),
                        CallbackQueryHandler(q_bot_sch_akun_scope, pattern=r"^menu_opt:"),
                    ],
                    STATE_SCH_AKUN_VALUE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_sch_akun_value),
                    ],
                    STATE_SCH_CONFIRM: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_sch_confirm),
                        CallbackQueryHandler(q_bot_sch_confirm, pattern=r"^menu_opt:"),
                    ],
                    STATE_SCH_TOGGLE_PILIH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_sch_toggle_pilih),
                        CallbackQueryHandler(q_bot_sch_toggle_pilih, pattern=r"^menu_opt:"),
                    ],
                    STATE_SCH_DELETE_PILIH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_sch_delete_pilih),
                        CallbackQueryHandler(q_bot_sch_delete_pilih, pattern=r"^menu_opt:"),
                    ],
                },
                fallbacks=[CommandHandler("start", bot_start), CommandHandler("help", bot_help)],
            )

    app.add_handler(conv_handler)
    try:
        from .ux import bot_runtime_callback as _rt_cb
        app.add_handler(CallbackQueryHandler(_rt_cb, pattern=r"^rt:"))
    except ImportError:
        pass
    app.add_error_handler(global_error_handler)

    return app

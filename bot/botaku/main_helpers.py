from __future__ import annotations
def validate_config():
    errors = []
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN / TELEKU_BOT_TOKEN tidak di-set di env")
    if not MONGO_URL:
        errors.append("MONGO_URL / TELEKU_MONGO_URL tidak di-set di env (hardcoded credentials removed for security)")
    if errors:
        logger.warning("CONFIG WARNING: " + "; ".join(errors))
    return len(errors)==0

def setup_asyncio_windows():
    """Setup asyncio event loop untuk Windows"""
    if sys.platform == 'win32':
        # Windows memerlukan ProactorEventLoop untuk subprocess support
        if sys.version_info >= (3, 8):
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except AttributeError:
                pass

async def debug_all_updates(update, context):
    try:
        user = update.effective_user
        chat = update.effective_chat
        msg = update.message.text if update.message else str(update.callback_query.data) if update.callback_query else "no text"
        logger.info(f"DEBUG UPDATE: user={user.id if user else 'N/A'} chat={chat.id if chat else 'N/A'} text={msg[:100]}")
    except Exception:
        pass

async def global_error_handler(update, context):
    """Menangani error global, khusus untuk Conflict getUpdates"""
    err = context.error
    err_str = str(err)
    if "Conflict" in err_str or "terminated by other getUpdates" in err_str:
        print(f"⚠️ Conflict terdeteksi (bot jalan di 2 tempat): {err}")
        print("ℹ️ Penyebab umum di Koyeb:")
        print("  1. Koyeb menjalankan 2 instance sekaligus (cek scaling -> set min=1, max=1)")
        print("  2. Bot masih jalan di laptop/PC lokal + di Koyeb bersamaan (matikan yang lokal)")
        print("  3. Ada web_server.py yang menjalankan bot di background, sementara telekuq.py juga menjalankan bot")
        print("  → Bot akan sleep 10 detik lalu retry otomatis (PTB akan retry sendiri)")
        # Jangan raise, biar PTB retry
        await asyncio.sleep(10)
    else:
        print(f"❌ Error tidak terduga: {err}")
        import traceback
        traceback.print_exception(type(err), err, err.__traceback__)

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

def check_port_in_use(port: int) -> bool:
    """FIXED: Cek apakah port sudah dipakai sebelum bind (untuk hindari Errno 98)"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False

def start_health_check_server():
    """Memulai server HTTP ringan di thread daemon untuk meloloskan health check Koyeb/Cloud Port.
    FIXED: Mencegah Address already in use di Koyeb (port 8000 sudah dipakai Flask/gunicorn)
    """
    port = int(os.getenv("PORT", "8000"))
    
    # FIXED: Jika port sudah dipakai (oleh Flask web_server.py), jangan coba lagi
    if check_port_in_use(port):
        print(f"ℹ️ Port {port} sudah dipakai oleh service lain (Flask/web_server), skip health check server (tidak apa-apa, Koyeb health check tetap lolos).")
        return

    class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("🟢 TeleKu System is 100% Healthy and Running on Koyeb!".encode("utf-8"))
            
        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            
        def log_message(self, format, *args):
            pass

    def _run():
        try:
            socketserver.TCPServer.allow_reuse_address = True
            # FIXED: SO_REUSEADDR + retry
            with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
                print(f"🚀 Koyeb Health Check Web Server berjalan di port {port}")
                httpd.serve_forever()
        except OSError as e:
            if e.errno == 98:  # Address already in use
                print(f"ℹ️ Port {port} sudah dipakai, health check server tidak diperlukan (Koyeb sudah punya web server).")
            else:
                print(f"⚠️ Gagal health check server {port}: {e}")
        except Exception as e:
            print(f"⚠️ Gagal health check server {port}: {e}")

    server_thread = threading.Thread(target=_run, daemon=True)
    server_thread.start()
    # FIXED: Beri jeda 0.5 detik untuk cek apakah thread langsung mati karena port conflict
    import time as _time
    _time.sleep(0.5)

def acquire_singleton_lock():
    """Cegah 2 proses bot jalan di container yang sama (file lock /tmp/teleku_bot.lock)"""
    try:
        lock_file_path = "/tmp/teleku_bot.lock"
        lock_file = open(lock_file_path, "w")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_file.write(str(os.getpid()))
            lock_file.flush()
            print(f"✅ Singleton lock acquired: {lock_file_path} (PID {os.getpid()})")
            return lock_file
        except (IOError, OSError):
            print("❌ Bot lain sudah jalan di container ini (lock file exists). Keluar untuk cegah Conflict.")
            print("   Jika ini salah, hapus /tmp/teleku_bot.lock dan restart.")
            sys.exit(1)
    except ImportError:
        # fcntl tidak ada di Windows, skip
        print("ℹ️ fcntl tidak tersedia (Windows), skip singleton lock")
        return None
    except Exception as e:
        print(f"⚠️ Gagal acquire lock (lanjut tanpa lock): {e}")
        return None

def main():
    """
    Entry point utama.
    - Jika BOT_TOKEN tersedia dan library python-telegram-bot terinstall,
      maka akan menjalankan mode bot Telegram.
    - Jika tidak, akan menggunakan mode CLI lama.
    """
    # Start the lightweight HTTP health check server for Koyeb free tier
    start_health_check_server()
    # FIXED: Acquire singleton lock untuk cegah Conflict di Koyeb
    global _singleton_lock_ref
    _singleton_lock_ref = acquire_singleton_lock()  # FIXED: global ref to keep lock alive

    if BOT_TOKEN and ApplicationBuilder is not None and ConversationHandler is not None:
        print("\n" + "=" * 70)
        print(" 🚀 Menjalankan TeleKu dalam mode BOT TELEGRAM")
        print("=" * 70)
        print(" Pastikan bot sudah di-start di Telegram dan tidak dipakai di tempat lain.")
        print("=" * 70)

        application = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .post_init(_bot_post_init)
            .build()
        )
        # Expose secara global agar scheduler (start_automation_run) bisa baca user_data
        globals()["_bot_app"] = application

        # Conversation handler untuk semua menu bot
        conv_handler = ConversationHandler(
            per_message=True,  # FIXED for inline button "Kirim Pesan tidak terjadi apa-apa": per_message=True agar CallbackQuery per pesan ter-track
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

        application.add_handler(MessageHandler(filters.ALL, debug_all_updates), group=0)
        # FIXED: Fallback handlers untuk inline button Kirim Pesan - agar tetap berfungsi meski ConversationHandler state lost
        # Ini menangani kasus "klik tidak terjadi apa-apa" di Koyeb
        # Fallback /start di luar ConversationHandler (jika ConversationHandler gagal track)
        application.add_handler(CommandHandler("start", bot_start))
        application.add_handler(CommandHandler("help", bot_help))
        application.add_handler(CallbackQueryHandler(bot_category_callback, pattern=r"^cat_"))
        application.add_handler(CallbackQueryHandler(bot_submenu_callback, pattern=r"^sub_"))
        application.add_handler(CallbackQueryHandler(bot_accounts_page_callback, pattern=r"^acc_page:"))
        application.add_handler(CallbackQueryHandler(bot_accounts_action_callback, pattern=r"^acc_act:"))
        application.add_handler(CallbackQueryHandler(bot_delete_confirm_callback, pattern=r"^conf_delete:"))
        application.add_handler(CallbackQueryHandler(bot_automation_callback, pattern=r"^aut_"))
        
        application.add_handler(conv_handler)
        # Handler inline button runtime (Pause/Resume/Stop)
        application.add_handler(CallbackQueryHandler(bot_runtime_callback, pattern=r"^rt:"))
        # FIXED: Daftarkan global error handler untuk Conflict
        application.add_error_handler(global_error_handler)

        try:
            print("✅ Bot Telegram berjalan. Tekan CTRL+C untuk menghentikan.")
            # FIXED untuk Koyeb Conflict: drop_pending_updates, allowed_updates, dan poll interval lebih longgar
            application.run_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"],
                poll_interval=1.0,
                close_loop=False,
            )
        except KeyboardInterrupt:
            print("\n\n⚠️  Bot dihentikan oleh user.")
        finally:
            if client is not None:
                client.close()
                print("✅ Koneksi MongoDB ditutup dengan aman.")
    print("\n" + "=" * 70)
    print(" ⛔️ BOT TELEGRAM TIDAK DAPAT DIJALANKAN")
    print("=" * 70)
    if not BOT_TOKEN:
        print(" • TELEKU_BOT_TOKEN belum di-set")
    if ApplicationBuilder is None or ConversationHandler is None:
        print(" • Library python-telegram-bot belum terinstall")
    print("=" * 70)
    if client is not None:
        client.close()
        print("✅ Koneksi MongoDB ditutup dengan aman.")

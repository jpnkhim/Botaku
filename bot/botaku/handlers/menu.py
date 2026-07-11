from __future__ import annotations
from ..keyboards import *
from ..database import *
from ..telegram_client import *
from ..ux import *
from ..states import *
from ..config import *
from ..config import ADMIN_USER_IDS, BOT_TOKEN, MONGO_URL
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from ..database import collection, db_count
from .common import *
logger = logging.getLogger('telekubot')
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

async def bot_category_callback(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"query.answer() gagal di bot_category_callback: {e}")
    data = query.data
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await query.edit_message_text("⛔️ Akses ditolak. Hanya admin yang dapat menggunakan bot ini.")
        return STATE_MAIN_MENU
        
    if data == "cat_kirim":
        context.user_data["last_submenu"] = "kirim"
        await query.edit_message_text(
            "📨 *MENU KIRIM PESAN*\n\nPilih fitur pengiriman:",
            reply_markup=get_submenu_kirim_inline_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "cat_akun":
        context.user_data["last_submenu"] = "akun"
        await query.edit_message_text(
            "👤 *KELOLA AKUN*\n\nPilih aksi:",
            reply_markup=get_submenu_akun_inline_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "cat_join":
        await query.edit_message_text(
            "👥 *GABUNG GRUP / CHANNEL (Bulk Join)*\n\n"
            "Masukkan *target* dengan salah satu cara:\n"
            "• 1 target (username/URL) per baris — bisa *multi-baris*\n"
            "• Atau *upload file .txt* (1 target per baris)\n\n"
            "*Format yang didukung:*\n"
            "• `@username` atau `username` (publik)\n"
            "• `https://t.me/username` (publik)\n"
            "• `https://t.me/+AbCdEf...` (private/invite)\n"
            "• `https://t.me/joinchat/AbCdEf...` (private/invite)\n\n"
            f"*Limit:* maks {MAX_BULK_JOIN_TARGETS} target per eksekusi.\n"
            "Duplikat otomatis di-skip.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_GABUNG_GROUP
    elif data == "cat_export":
        context.user_data["last_submenu"] = "export"
        await query.edit_message_text(
            "📦 *IMPORT & EXPORT*\n\nPilih aksi:",
            reply_markup=get_submenu_export_inline_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "cat_automation":
        context.user_data["last_submenu"] = "automation"
        await query.edit_message_text(
            "🤖 *AUTOMATION SCRIPTS*\n\nPilih aksi:",
            reply_markup=get_submenu_automation_inline_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "cat_settings":
        context.user_data["last_submenu"] = "settings"
        await query.edit_message_text(
            "🛠️ *TOOLS & PENGATURAN*\n\nPilih aksi:",
            reply_markup=get_submenu_settings_inline_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "cat_help":
        help_text = (
            "❓ *BANTUAN TELEKU*\n\n"
            "Bot ini adalah asisten otomatisasi Telegram Anda. Berikut adalah ringkasan fitur:\n\n"
            "1️⃣ *Kirim Pesan*: Kirim pesan masal dengan akun-akun Anda secara cerdas, otomatis, dan tahan ban.\n"
            "2️⃣ *Kelola Akun*: Tambah/baca/test/hapus session login Telegram.\n"
            "3️⃣ *Gabung Grup*: Bergabung ke grup/channel Telegram dalam jumlah banyak secara massal.\n"
            "4️⃣ *Import/Export*: Backup dan restore akun Telegram Anda dalam format JSON.\n"
            "5️⃣ *Automation & Scheduler*: Buat script otomatisasi interaksi (delay, klik button, kirim pesan) lalu jadwalkan run otomatis pada jam tertentu.\n\n"
            "Gunakan tombol di bawah untuk kembali ke Menu Utama."
        )
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="sub_back_main")]]
        await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    return STATE_MAIN_MENU

async def bot_submenu_callback(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"query.answer() gagal di bot_submenu_callback: {e}")
    data = query.data
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await query.edit_message_text("⛔️ Akses ditolak. Hanya admin yang dapat menggunakan bot ini.")
        return STATE_MAIN_MENU
        
    if data == "sub_back_main":
        context.user_data.pop("last_submenu", None)
        await query.edit_message_text(
            f"{ICON['success']} *KEMBALI KE MENU UTAMA*\n\nSilakan pilih kategori menu dari tombol keyboard di bawah atau tombol interaktif:",
            reply_markup=get_categories_inline_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_MAIN_MENU
        
    elif data == "sub_back_contextual":
        last_sub = context.user_data.get("last_submenu")
        if last_sub == "kirim":
            await query.edit_message_text(
                "📨 *MENU KIRIM PESAN*\n\nPilih fitur pengiriman:",
                reply_markup=get_submenu_kirim_inline_keyboard(),
                parse_mode="Markdown"
            )
        elif last_sub == "akun":
            await query.edit_message_text(
                "👤 *KELOLA AKUN*\n\nPilih aksi:",
                reply_markup=get_submenu_akun_inline_keyboard(),
                parse_mode="Markdown"
            )
        elif last_sub == "export":
            await query.edit_message_text(
                "📦 *IMPORT & EXPORT*\n\nPilih aksi:",
                reply_markup=get_submenu_export_inline_keyboard(),
                parse_mode="Markdown"
            )
        elif last_sub == "settings":
            await query.edit_message_text(
                "🛠️ *TOOLS & PENGATURAN*\n\nPilih aksi:",
                reply_markup=get_submenu_settings_inline_keyboard(),
                parse_mode="Markdown"
            )
        elif last_sub == "automation":
            await query.edit_message_text(
                "🤖 *AUTOMATION SCRIPTS*\n\nPilih aksi:",
                reply_markup=get_submenu_automation_inline_keyboard(),
                parse_mode="Markdown"
            )
        elif last_sub == "schedule":
            await query.edit_message_text(
                "📅 *PENGATURAN JADWAL AUTOMATION*\n\nPilih aksi:",
                reply_markup=get_submenu_schedule_inline_keyboard(),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                f"{ICON['success']} *KEMBALI KE MENU UTAMA*\n\nSilakan pilih kategori menu dari tombol interaktif di bawah:",
                reply_markup=get_categories_inline_keyboard(),
                parse_mode="Markdown"
            )
        return STATE_MAIN_MENU
        
    elif data == "sub_back_kirim":
        context.user_data["last_submenu"] = "kirim"
        await query.edit_message_text(
            "📨 *MENU KIRIM PESAN*\n\nPilih fitur pengiriman:",
            reply_markup=get_submenu_kirim_inline_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_MAIN_MENU
        
    elif data == "sub_back_akun":
        context.user_data["last_submenu"] = "akun"
        await query.edit_message_text(
            "👤 *KELOLA AKUN*\n\nPilih aksi:",
            reply_markup=get_submenu_akun_inline_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_MAIN_MENU
        
    elif data == "sub_back_settings":
        context.user_data["last_submenu"] = "settings"
        await query.edit_message_text(
            "🛠️ *TOOLS & PENGATURAN*\n\nPilih aksi:",
            reply_markup=get_submenu_settings_inline_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_MAIN_MENU
        
    elif data == "sub_back_automation":
        context.user_data["last_submenu"] = "automation"
        await query.edit_message_text(
            "🤖 *AUTOMATION SCRIPTS*\n\nPilih aksi:",
            reply_markup=get_submenu_automation_inline_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_MAIN_MENU
        
    elif data == "sub_kirim_cepat":
        try:
            await query.edit_message_text(
                "⚡ *KIRIM CEPAT*\n\n🎯 Masukkan *username bot/user* tujuan (contoh: `@username`):",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown"
            )
        except Exception:
            await query.edit_message_text(
                "⚡ KIRIM CEPAT\n\nMasukkan username tujuan:",
                reply_markup=get_cancel_keyboard(),
                parse_mode=None
            )
        return STATE_KIRIM_CEPAT_TARGET
        
    elif data == "sub_kirim_pesan":
        # FIXED: Inline button Kirim Pesan tidak terjadi apa-apa - gunakan db_count yang safe + fallback tanpa Markdown + log
        try:
            count = await db_count(collection, {})
            # Fallback jika collection None atau db_count gagal
            if count is None:
                count = 0
        except Exception as e:
            logger.error(f"Error count_documents di sub_kirim_pesan: {e}")
            # Fallback: coba to_thread langsung, atau anggap 0
            try:
                count = await asyncio.to_thread(lambda: collection.count_documents({}) if collection else 0)
            except Exception as e2:
                await query.edit_message_text(f"❌ Error saat membaca database: {e2}")
                return STATE_MAIN_MENU
        if count == 0:
            try:
                await query.edit_message_text("⚠️ Tidak ada akun yang tersimpan. Tambahkan akun dahulu.")
            except Exception:
                await query.edit_message_text("⚠️ Tidak ada akun yang tersimpan. Tambahkan akun dahulu.", parse_mode=None)
            return STATE_MAIN_MENU
        try:
            await query.edit_message_text(
                "📤 *KIRIM PESAN*\n\n🎯 Masukkan *username bot/user* tujuan (contoh: `@username`):",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as e:
            # Fallback tanpa markdown kalau gagal parse
            logger.warning(f"Markdown fail di sub_kirim_pesan: {e}, fallback tanpa markdown")
            await query.edit_message_text(
                "📤 KIRIM PESAN\n\nMasukkan username bot/user tujuan (contoh: @username):",
                reply_markup=get_cancel_keyboard(),
                parse_mode=None
            )
        return STATE_KIRIM_TARGET
        
    elif data == "sub_kirim_file":
        try:
            count = await asyncio.to_thread(collection.count_documents, {})
        except Exception as e:
            await query.edit_message_text(f"❌ Error saat membaca database: {e}")
            return STATE_MAIN_MENU
        if count == 0:
            await query.edit_message_text("⚠️ Tidak ada akun yang tersimpan. Tambahkan akun dahulu.")
            return STATE_MAIN_MENU
        await query.edit_message_text(
            "📄 *KIRIM PESAN DARI FILE TXT*\n\n"
            "Fitur ini membagi pesan dari file TXT ke semua akun secara round-robin.\n"
            "Setiap baris = 1 pesan, dibagi rata ke semua akun.\n\n"
            "🎯 Masukkan *username bot/user* tujuan (contoh: `@username`):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_KIRIM_FILE_TARGET
        
    elif data == "sub_kirim_otp":
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await query.edit_message_text(f"❌ Error saat mengambil data akun: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await query.edit_message_text("⚠️ Tidak ada akun yang tersimpan di database.")
            return STATE_MAIN_MENU
        context.user_data["otp_akun_list"] = akun_list
        await query.edit_message_text(
            "🔐 *AMBIL PESAN OTP*\n\nPilih akun dari daftar di bawah:",
            reply_markup=get_paginated_accounts_keyboard(akun_list, "otp", page=0),
            parse_mode="Markdown"
        )
        return STATE_OTP_PILIH_AKUN
        
    elif data == "sub_kirim_repeat":
        return await bot_repeat_last_action(update, context)
        
    elif data == "sub_akun_add_login":
        await query.edit_message_text(
            "🔑 Masukkan *API ID* Anda (angka, minimal 5 digit):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_TAMBAH_LOGIN_API_ID
        
    elif data == "sub_akun_add_manual":
        await query.edit_message_text(
            "🔑 Masukkan *API ID* Anda (angka, minimal 5 digit):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_TAMBAH_API_ID
        
    elif data == "sub_akun_list":
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await query.edit_message_text(f"❌ Error saat mengambil data akun: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await query.edit_message_text("⚠️ Tidak ada akun yang tersimpan di database.")
            return STATE_MAIN_MENU
        await query.edit_message_text(
            f"📊 *DAFTAR AKUN ({len(akun_list)} Akun)*\n\nPilih akun untuk melihat info ringkas:",
            reply_markup=get_paginated_accounts_keyboard(akun_list, "list", page=0),
            parse_mode="Markdown"
        )
        return STATE_MAIN_MENU
        
    elif data == "sub_akun_info":
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await query.edit_message_text(f"❌ Error saat mengambil data akun: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await query.edit_message_text("⚠️ Tidak ada akun yang tersimpan di database.")
            return STATE_MAIN_MENU
        context.user_data["info_akun_list"] = akun_list
        await query.edit_message_text(
            "ℹ️ *INFORMASI DETAIL AKUN*\n\nPilih akun untuk melihat detail lengkap:",
            reply_markup=get_paginated_accounts_keyboard(akun_list, "info", page=0),
            parse_mode="Markdown"
        )
        return STATE_INFO_AKUN_PILIH
        
    elif data == "sub_akun_status":
        return await bot_status_akun(update, context)
        
    elif data == "sub_akun_test":
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await query.edit_message_text("⚠️ Tidak ada akun di database.")
            return STATE_MAIN_MENU
        context.user_data["test_akun_list"] = akun_list
        await query.edit_message_text(
            "🧪 *TEST KONEKSI AKUN*\n\nPilih akun untuk ditest kinerjanya:",
            reply_markup=get_paginated_accounts_keyboard(akun_list, "test", page=0),
            parse_mode="Markdown"
        )
        return STATE_TEST_AKUN_PILIH
        
    elif data == "sub_akun_delete":
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await query.edit_message_text("⚠️ Tidak ada akun di database.")
            return STATE_MAIN_MENU
        context.user_data["hapus_akun_phones"] = [a.get("nomor_telepon", "") for a in akun_list]
        await query.edit_message_text(
            "🗑️ *HAPUS AKUN DARI DATABASE*\n\nPilih akun yang ingin dihapus:",
            reply_markup=get_paginated_accounts_keyboard(akun_list, "delete", page=0),
            parse_mode="Markdown"
        )
        return STATE_HAPUS_AKUN
        
    elif data == "sub_akun_reset":
        return await bot_reset_status_menu(update, context)
        
    elif data == "sub_akun_tags":
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await query.edit_message_text("⚠️ Tidak ada akun.")
            return STATE_MAIN_MENU
        context.user_data["tag_akun_list"] = akun_list
        await query.edit_message_text(
            "🏷️ *KELOLA TAG AKUN*\n\nPilih akun untuk menambah/mengedit tag:",
            reply_markup=get_paginated_accounts_keyboard(akun_list, "tags", page=0),
            parse_mode="Markdown"
        )
        return STATE_TAG_PILIH
        
    elif data == "sub_akun_search":
        await query.edit_message_text(
            "🔎 *CARI AKUN*\n\nMasukkan kata kunci pencarian (nama/nomor/username/tag):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_SEARCH_QUERY

    elif data == "sub_export_json":
        return await bot_export_json(update, context)
        
    elif data == "sub_export_ringkasan":
        return await bot_export_ringkasan(update, context)
        
    elif data == "sub_import_json":
        await query.edit_message_text(
            "⬆️ *IMPORT AKUN JSON*\n\nSilakan *upload file JSON* yang berisi data backup akun Telegram:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_IMPORT_JSON_WAIT

    elif data == "sub_settings_opt":
        return await bot_settings_menu(update, context)
        
    elif data == "sub_settings_testdb":
        try:
            client.admin.command('ping')
            await query.edit_message_text(
                "✅ *Koneksi Database Oke!*\n\nMongoDB Firestore responsif dan normal.",
                reply_markup=get_submenu_settings_inline_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as e:
            await query.edit_message_text(f"❌ *Koneksi Database Gagal:* {e}", parse_mode="Markdown")
        return STATE_MAIN_MENU
        
    elif data == "sub_settings_btnid":
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await query.edit_message_text("⚠️ Tidak ada akun di database.")
            return STATE_MAIN_MENU
        context.user_data["btnid_akun_list"] = akun_list
        await query.edit_message_text(
            "🔘 *AMBIL ID BUTTON INTERAKTIF*\n\nPilih akun untuk mengambil ID tombol:",
            reply_markup=get_paginated_accounts_keyboard(akun_list, "btnid", page=0),
            parse_mode="Markdown"
        )
        return STATE_BTNID_PILIH_AKUN

    elif data == "sub_auto_create":
        return await bot_auto_mulai_buat(update, context)
        
    elif data == "sub_auto_list":
        return await bot_auto_daftar(update, context)
        
    elif data == "sub_auto_run":
        return await bot_auto_run_pilih(update, context)
        
    elif data == "sub_auto_stop":
        return await bot_auto_stop_menu(update, context)
        
    elif data == "sub_auto_delete":
        return await bot_auto_hapus_menu(update, context)
        
    elif data == "sub_auto_schedule":
        context.user_data["last_submenu"] = "schedule"
        await query.edit_message_text(
            "📅 *PENGATURAN JADWAL AUTOMATION*\n\nPilih aksi:",
            reply_markup=get_submenu_schedule_inline_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_MAIN_MENU

    elif data == "sub_sch_create":
        return await bot_sch_mulai_buat(update, context)
        
    elif data == "sub_sch_list":
        return await bot_sch_daftar(update, context)
        
    elif data == "sub_sch_toggle":
        return await bot_sch_toggle_menu(update, context)
        
    elif data == "sub_sch_delete":
        return await bot_sch_delete_menu(update, context)

    return STATE_MAIN_MENU

def get_submenu_kirim_keyboard():
    return _make_keyboard(SUBMENU_KIRIM)

async def bot_menu_router(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Membaca pilihan tombol/menu utama dan sub-menu, lalu mengarahkan ke state berikutnya."""
    pesan = (update.message.text or "").strip()

    # === Sedang menunggu input pencarian akun ===
    if context.user_data.get("awaiting_acc_search"):
        return await bot_accounts_search_input(update, context)

    # === TOMBOL KEMBALI ===
    if pesan == "🔙 Kembali" or pesan.startswith("🔙 Kembali ke Menu"):
        context.user_data.pop("last_submenu", None)
        await bot_send_main_menu(update, context, "Silakan pilih kategori menu:")
        return STATE_MAIN_MENU

    # =============================================
    # KATEGORI MENU UTAMA → TAMPILKAN SUB-MENU
    # =============================================

    if pesan == "📨 Kirim Pesan":
        context.user_data["last_submenu"] = "kirim"
        await update.message.reply_text(
            "📨 *MENU KIRIM PESAN*\n\nPilih fitur pengiriman:",
            reply_markup=get_submenu_kirim_inline_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_MAIN_MENU

    if pesan == "👤 Kelola Akun":
        context.user_data["last_submenu"] = "akun"
        await update.message.reply_text(
            "👤 *KELOLA AKUN*\n\nPilih aksi:",
            reply_markup=get_submenu_akun_inline_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_MAIN_MENU

    if pesan == "📦 Import & Export":
        context.user_data["last_submenu"] = "export"
        await update.message.reply_text(
            "📦 *IMPORT & EXPORT*\n\nPilih aksi:",
            reply_markup=get_submenu_export_inline_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_MAIN_MENU

    if pesan == "🛠️ Tools & Pengaturan":
        context.user_data["last_submenu"] = "settings"
        await update.message.reply_text(
            "🛠️ *TOOLS & PENGATURAN*\n\nPilih aksi:",
            reply_markup=get_submenu_settings_inline_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_MAIN_MENU

    if pesan == "❓ Bantuan":
        return await bot_help(update, context)

    # =============================================
    # ITEM SUB-MENU KIRIM PESAN
    # =============================================

    if pesan.startswith("⚡"):
        await update.message.reply_text(
            "🎯 Masukkan *username bot/user* tujuan (contoh: `@username`):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_KIRIM_CEPAT_TARGET

    if pesan.startswith("📤"):
        try:
            count = await db_count(collection, {})
        except Exception as e:
            await update.message.reply_text(f"❌ Error saat membaca database: {e}")
            return STATE_MAIN_MENU
        if count == 0:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan. Tambahkan akun dahulu.")
            return STATE_MAIN_MENU
        await update.message.reply_text(
            "📤 *KIRIM PESAN*\n\n🎯 Masukkan *username bot/user* tujuan (contoh: `@username`):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_KIRIM_TARGET

    if pesan.startswith("📄"):
        try:
            count = await db_count(collection, {})
        except Exception as e:
            await update.message.reply_text(f"❌ Error saat membaca database: {e}")
            return STATE_MAIN_MENU
        if count == 0:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan. Tambahkan akun dahulu.")
            return STATE_MAIN_MENU
        await update.message.reply_text(
            "📄 *KIRIM PESAN DARI FILE TXT*\n\n"
            "Fitur ini membagi pesan dari file TXT ke semua akun secara round-robin.\n"
            "Setiap baris = 1 pesan, dibagi rata ke semua akun.\n\n"
            "🎯 Masukkan *username bot/user* tujuan (contoh: `@username`):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_KIRIM_FILE_TARGET

    if pesan.startswith("🔐"):
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await update.message.reply_text(f"❌ Error saat mengambil data akun: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan di database.")
            return STATE_MAIN_MENU
        context.user_data["otp_akun_list"] = akun_list
        lines = ["🔐 *AMBIL PESAN OTP*\n\nPilih akun (balas dengan *nomor urut*):\n"]
        for idx, akun in enumerate(akun_list, 1):
            lines.append(f"{idx}. `{akun.get('nomor_telepon', 'N/A')}` ({akun.get('name', 'N/A')})")
        await update.message.reply_text("\n".join(lines), reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
        return STATE_OTP_PILIH_AKUN

    if pesan.startswith("🔁"):
        return await bot_repeat_last_action(update, context)

    # =============================================
    # ITEM SUB-MENU KELOLA AKUN
    # =============================================

    if pesan.startswith("➕ Tambah Akun Login"):
        await update.message.reply_text(
            "🔑 Masukkan *API ID* Anda (angka, minimal 5 digit):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_TAMBAH_LOGIN_API_ID

    if pesan.startswith("➕ Tambah Akun Manual"):
        await update.message.reply_text(
            "🔑 Masukkan *API ID* Anda (angka, minimal 5 digit):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_TAMBAH_API_ID

    if pesan.startswith("📋 Lihat Semua Akun"):
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await update.message.reply_text(f"❌ Error saat mengambil data akun: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan di database.")
            return STATE_MAIN_MENU
        lines = [f"📊 *Total Akun: {len(akun_list)}*\n"]
        for idx, akun in enumerate(akun_list, 1):
            lines.append(f"{idx}. `{akun.get('nomor_telepon', 'N/A')}` | {akun.get('name', 'N/A')}")
        await bot_send_main_menu(update, context, "\n".join(lines))
        return STATE_MAIN_MENU

    if pesan.startswith("ℹ️"):
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await update.message.reply_text(f"❌ Error saat mengambil data akun: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan di database.")
            return STATE_MAIN_MENU
        context.user_data["info_akun_list"] = akun_list
        lines = ["ℹ️ *INFORMASI AKUN*\n\nPilih akun (balas dengan *nomor urut*):\n"]
        for idx, akun in enumerate(akun_list, 1):
            lines.append(f"{idx}. `{akun.get('nomor_telepon', 'N/A')}` ({akun.get('name', 'N/A')})")
        await update.message.reply_text("\n".join(lines), reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
        return STATE_INFO_AKUN_PILIH

    if pesan.startswith("📊"):
        return await bot_status_akun(update, context)

    if pesan.startswith("🧪"):
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await update.message.reply_text(f"❌ Error saat mengambil data akun: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan di database.")
            return STATE_MAIN_MENU
        context.user_data["test_akun_list"] = akun_list
        lines = ["🧪 *TEST AKUN*\n\nPilih akun (balas dengan *nomor urut*):\n"]
        for idx, akun in enumerate(akun_list, 1):
            lines.append(f"{idx}. `{akun.get('nomor_telepon', 'N/A')}` ({akun.get('name', 'N/A')})")
        await update.message.reply_text("\n".join(lines), reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
        return STATE_TEST_AKUN_PILIH

    if pesan.startswith("🗑️ Hapus Akun"):
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await update.message.reply_text(f"❌ Error saat mengambil data akun: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan di database.")
            return STATE_MAIN_MENU
        context.user_data["hapus_akun_phones"] = [a.get("nomor_telepon", "") for a in akun_list]
        lines = ["🗑️ *HAPUS AKUN*\n\nPilih akun (balas *nomor urut* atau *nomor telepon*):\n"]
        for idx, akun in enumerate(akun_list, 1):
            lines.append(f"{idx}. `{akun.get('nomor_telepon', 'N/A')}` ({akun.get('name', 'N/A')})")
        await update.message.reply_text("\n".join(lines), reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
        return STATE_HAPUS_AKUN

    if pesan.startswith("🔄"):
        return await bot_reset_status_menu(update, context)

    if pesan.startswith("🏷️"):
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await update.message.reply_text(f"❌ Error saat mengambil data akun: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan di database.")
            return STATE_MAIN_MENU
        context.user_data["tag_akun_list"] = akun_list
        lines = ["🏷️ *KELOLA TAG*\n\nPilih akun (balas dengan *nomor urut*):\n"]
        for idx, akun in enumerate(akun_list, 1):
            current_tags = ", ".join(akun.get("tags", []) or []) or "-"
            lines.append(f"{idx}. `{akun.get('nomor_telepon', 'N/A')}` ({akun.get('name', 'N/A')}) — {current_tags}")
        await update.message.reply_text("\n".join(lines), reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
        return STATE_TAG_PILIH

    if pesan.startswith("🔎"):
        await update.message.reply_text(
            "🔎 Masukkan kata kunci pencarian (nama/nomor/username/tag):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_SEARCH_QUERY

    # =============================================
    # ITEM SUB-MENU GABUNG GRUP (langsung dari menu utama)
    # =============================================

    if pesan.startswith("👥"):
        try:
            count = await db_count(collection, {})
        except Exception as e:
            await update.message.reply_text(f"❌ Error saat membaca database: {e}")
            return STATE_MAIN_MENU
        if count == 0:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan. Tambahkan akun dahulu.")
            return STATE_MAIN_MENU
        await update.message.reply_text(
            "👥 *GABUNG GRUP / CHANNEL (Bulk Join)*\n\n"
            "Masukkan *target* dengan salah satu cara:\n"
            "• 1 target (username/URL) per baris — bisa *multi-baris*\n"
            "• Atau *upload file .txt* (1 target per baris)\n\n"
            "*Format yang didukung:*\n"
            "• `@username` atau `username` (publik)\n"
            "• `https://t.me/username` (publik)\n"
            "• `https://t.me/+AbCdEf...` (private/invite)\n"
            "• `https://t.me/joinchat/AbCdEf...` (private/invite)\n\n"
            f"*Limit:* maks {MAX_BULK_JOIN_TARGETS} target per eksekusi.\n"
            "Duplikat otomatis di-skip.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_GABUNG_GROUP

    # =============================================
    # ITEM SUB-MENU IMPORT & EXPORT
    # =============================================

    if pesan.startswith("📥"):
        try:
            count = await db_count(collection, {})
        except Exception as e:
            await update.message.reply_text(f"❌ Error saat membaca database: {e}")
            return STATE_MAIN_MENU
        if count == 0:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan di database.")
            return STATE_MAIN_MENU
        await update.message.reply_text(
            f"📥 *EXPORT SEMUA AKUN*\n\nTotal akun: *{count}*\n⏳ Memproses export...",
            parse_mode="Markdown"
        )
        return await bot_export_json(update, context)

    if pesan.startswith("🧾"):
        return await bot_export_ringkasan(update, context)

    if pesan.startswith("⬆️"):
        await update.message.reply_text(
            "⬆️ Kirim file JSON berisi daftar akun untuk import:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_IMPORT_JSON_WAIT

    # =============================================
    # ITEM SUB-MENU PENGATURAN
    # =============================================

    if pesan.startswith("⚙️"):
        return await bot_settings_menu(update, context)

    if pesan.startswith("🔍"):
        try:
            client.admin.command("ping")
            count = await db_count(collection, {})
            msg = (
                "✅ Koneksi ke Google Firestore MongoDB *berhasil*.\n\n"
                "📊 *Informasi Database:*\n"
                "• Database: `indonesian`\n"
                "• Collection: `telegram_accounts`\n"
                f"• Total Akun: *{count}*"
            )
        except Exception as e:
            msg = f"❌ Error saat test koneksi database: {e}"
        await bot_send_main_menu(update, context, msg)
        return STATE_MAIN_MENU

    if pesan.startswith("🔘 Ambil ID Button"):
        # Ambil ID Button — pilih akun dulu
        try:
            akun_list = await db_find(collection, {})
        except Exception as e:
            await update.message.reply_text(f"❌ Error saat mengambil data akun: {e}")
            return STATE_MAIN_MENU
        if not akun_list:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan di database.")
            return STATE_MAIN_MENU
        context.user_data["btnid_akun_list"] = akun_list
        lines = ["🔘 *AMBIL ID BUTTON*\n\nPilih akun (balas dengan *nomor urut*):\n"]
        for idx, akun in enumerate(akun_list, 1):
            lines.append(f"{idx}. `{akun.get('nomor_telepon', 'N/A')}` ({akun.get('name', 'N/A')})")
        await update.message.reply_text("\n".join(lines), reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
        return STATE_BTNID_PILIH_AKUN

    # =============================================
    # KATEGORI MENU: AUTOMATION
    # =============================================
    if pesan == "🤖 Automation":
        context.user_data["last_submenu"] = "automation"
        await update.message.reply_text(
            "🤖 *AUTOMATION*\n\nBuat, jalankan, dan kelola automation custom Anda.\n\nPilih aksi:",
            reply_markup=get_submenu_automation_inline_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_MAIN_MENU

    if pesan.startswith("➕ Buat Automation"):
        return await bot_auto_mulai_buat(update, context)

    if pesan.startswith("📋 Daftar Automation"):
        return await bot_auto_daftar(update, context)

    if pesan.startswith("▶️ Jalankan Automation"):
        return await bot_auto_run_pilih(update, context)

    if pesan.startswith("⏹️ Stop Automation"):
        return await bot_auto_stop_menu(update, context)

    if pesan.startswith("🗑️ Hapus Automation"):
        return await bot_auto_hapus_menu(update, context)

    # =============================================
    # SUBMENU JADWAL
    # =============================================
    if pesan == "📅 Jadwal":
        context.user_data["last_submenu"] = "schedule"
        await update.message.reply_text(
            "📅 *JADWAL AUTOMATION*\n\n"
            "Atur automation agar berjalan otomatis berdasarkan waktu.\n\n"
            "Pilih aksi:",
            reply_markup=get_submenu_schedule_inline_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_MAIN_MENU

    if pesan.startswith("➕ Buat Jadwal"):
        return await bot_sch_mulai_buat(update, context)

    if pesan.startswith("📋 Daftar Jadwal"):
        return await bot_sch_daftar(update, context)

    if pesan.startswith("🔀 Toggle"):
        return await bot_sch_toggle_menu(update, context)

    if pesan.startswith("🗑️ Hapus Jadwal"):
        return await bot_sch_delete_menu(update, context)

    # Default: jika input tidak dikenali
    await bot_send_main_menu(
        update,
        context,
        "❓ Input tidak dikenali. Silakan pilih tombol menu di bawah.",
    )
    return STATE_MAIN_MENU

from __future__ import annotations
from ..keyboards import *
from ..database import *
from ..telegram_client import *
from ..ux import *
from ..states import *
from ..config import *
from ..config import ADMIN_USER_IDS, BOT_TOKEN, MONGO_URL
import asyncio
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from ..database import collection, db_count, db_find, db_find_one, db_update_one, db_delete_one
from .common import *
def _resolve_akun_for_schedule(akun_scope: str, akun_value: str):
    """Resolve daftar akun aktif berdasarkan scope yang disimpan."""
    try:
        akun_list = list(collection.find({}, {"_id": 0}))
    except Exception:
        return []
    if not akun_list:
        return []
    scope = (akun_scope or "all").lower()
    if scope == "all":
        selected = akun_list
    elif scope == "count":
        try:
            n = int(akun_value)
        except Exception:
            n = len(akun_list)
        selected = akun_list[: max(1, n)]
    elif scope == "tag":
        tag = (akun_value or "").lower()
        selected = [
            a for a in akun_list
            if tag in [t.lower() for t in (a.get("tags", []) or [])]
        ]
    else:
        selected = akun_list
    return [a for a in selected if a.get("status", "aktif") not in SKIP_STATUSES]

def get_submenu_akun_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ Tambah Akun Login", callback_data="sub_akun_add_login"),
         InlineKeyboardButton("➕ Tambah Akun Manual", callback_data="sub_akun_add_manual")],
        [InlineKeyboardButton("📋 Lihat Semua Akun", callback_data="sub_akun_list"),
         InlineKeyboardButton("ℹ️ Info Akun", callback_data="sub_akun_info")],
        [InlineKeyboardButton("📊 Status Akun", callback_data="sub_akun_status"),
         InlineKeyboardButton("🧪 Test Akun", callback_data="sub_akun_test")],
        [InlineKeyboardButton("🗑️ Hapus Akun", callback_data="sub_akun_delete"),
         InlineKeyboardButton("🔄 Reset Status", callback_data="sub_akun_reset")],
        [InlineKeyboardButton("🏷️ Kelola Tag", callback_data="sub_akun_tags"),
         InlineKeyboardButton("🔎 Cari Akun", callback_data="sub_akun_search")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="sub_back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_paginated_accounts_keyboard(akun_list, action, page=0, limit=5, show_search=True):
    """Membuat keyboard inline dengan paginasi + tombol cari untuk daftar akun."""
    total = len(akun_list)
    start_idx = page * limit
    end_idx = min(start_idx + limit, total)
    
    # Slice list akun untuk halaman saat ini
    page_akun = akun_list[start_idx:end_idx]
    
    buttons = []
    for idx, akun in enumerate(page_akun, start_idx + 1):
        nomor = akun.get("nomor_telepon", "N/A")
        name = akun.get("name", "N/A")
        status = akun.get("status", "aktif")
        
        # Status icon
        status_icon = "🟢" if status == "aktif" else "🔴" if status in ("terblokir", "expired") else "🟡"
        
        label = f"{status_icon} {idx}. {nomor} ({name[:12]})"
        # Callback data format: "acc_act:<action>:<phone>"
        buttons.append([InlineKeyboardButton(label, callback_data=f"acc_act:{action}:{nomor}")])
        
    # Tombol navigasi
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"acc_page:{action}:{page-1}"))
    
    # Status page
    total_pages = (total + limit - 1) // limit if total > 0 else 1
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="acc_page_nop"))
        
    if end_idx < total:
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"acc_page:{action}:{page+1}"))
        
    if nav_buttons:
        buttons.append(nav_buttons)

    if show_search:
        buttons.append([InlineKeyboardButton("🔎 Cari Akun", callback_data=f"acc_search:{action}")])
        
    # Tombol kembali ke Menu Sebelumnya (Contextual Back Button!)
    back_callback = "sub_back_main"
    back_label = "🔙 Kembali ke Menu Utama"
    
    if action == "otp":
        back_callback = "sub_back_kirim"
        back_label = "🔙 Kembali ke Menu Kirim"
    elif action in ("list", "info", "test", "delete", "tags"):
        back_callback = "sub_back_akun"
        back_label = "🔙 Kembali ke Kelola Akun"
    elif action == "btnid":
        back_callback = "sub_back_settings"
        back_label = "🔙 Kembali ke Pengaturan"
        
    buttons.append([InlineKeyboardButton(back_label, callback_data=back_callback)])
    
    return InlineKeyboardMarkup(buttons)

async def q_bot_reset_status_pilih(update, context): return await bot_inline_opt_bridge(update, context, bot_reset_status_pilih)

async def q_bot_reset_status_confirm(update, context): return await bot_inline_opt_bridge(update, context, bot_reset_status_confirm)

async def q_bot_sch_akun_scope(update, context): return await bot_inline_opt_bridge(update, context, bot_sch_akun_scope)

async def bot_accounts_page_callback(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"query.answer() gagal: {e}")
    data = query.data
    parts = data.split(":")
    if len(parts) < 3:
        return
        
    action = parts[1]
    page = int(parts[2])
    
    # Cek apakah ada filter pencarian aktif untuk action ini
    search_map = context.user_data.get("acc_search_query") or {}
    search_query = search_map.get(action, "")
    try:
        akun_list_all = await db_find(collection, {})
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {e}")
        return
    if search_query:
        akun_list = filter_accounts_by_query(akun_list_all, search_query)
    else:
        akun_list = akun_list_all
        
    title_map = {
        "list": "📊 *DAFTAR AKUN*",
        "info": "ℹ️ *INFORMASI DETAIL AKUN*",
        "test": "🧪 *TEST KONEKSI AKUN*",
        "delete": "🗑️ *HAPUS AKUN DARI DATABASE*",
        "tags": "🏷️ *KELOLA TAG AKUN*",
        "otp": "🔐 *AMBIL PESAN OTP*",
        "btnid": "🔘 *AMBIL ID BUTTON INTERAKTIF*"
    }
    
    title = title_map.get(action, "👥 *KELOLA AKUN*")
    hint = f" — filter: `{search_query}` ({len(akun_list)}/{len(akun_list_all)})" if search_query else f" ({len(akun_list)} akun)"
    await query.edit_message_text(
        f"{title}{hint}\n\nPilih akun dari daftar di bawah (Halaman {page+1}):",
        reply_markup=get_paginated_accounts_keyboard(akun_list, action, page=page),
        parse_mode="Markdown"
    )


async def bot_accounts_search_callback(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler tombol 🔎 Cari Akun pada paginated keyboard."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    data = query.data or ""
    parts = data.split(":", 1)
    if len(parts) < 2:
        return
    action = parts[1]
    context.user_data["acc_search_action"] = action
    context.user_data["awaiting_acc_search"] = True
    await query.edit_message_text(
        "🔎 *CARI AKUN*\n\n"
        "Ketik kata kunci pencarian (nama / nomor / username / tag).\n"
        "Ketik `all` untuk reset filter dan tampilkan semua akun.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Batal", callback_data=f"acc_search_cancel:{action}")]
        ]),
        parse_mode="Markdown",
    )
    return STATE_MAIN_MENU


async def bot_accounts_search_cancel_callback(update, context):
    """Batal cari, kembali ke daftar akun tanpa filter."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    data = query.data or ""
    parts = data.split(":", 1)
    action = parts[1] if len(parts) > 1 else "list"
    # Reset filter untuk action ini
    search_map = context.user_data.get("acc_search_query") or {}
    search_map.pop(action, None)
    context.user_data["acc_search_query"] = search_map
    try:
        akun_list = await db_find(collection, {})
    except Exception:
        akun_list = []
    title_map = {
        "list": "📊 *DAFTAR AKUN*",
        "info": "ℹ️ *INFORMASI DETAIL AKUN*",
        "test": "🧪 *TEST KONEKSI AKUN*",
        "delete": "🗑️ *HAPUS AKUN DARI DATABASE*",
        "tags": "🏷️ *KELOLA TAG AKUN*",
        "otp": "🔐 *AMBIL PESAN OTP*",
        "btnid": "🔘 *AMBIL ID BUTTON INTERAKTIF*",
    }
    title = title_map.get(action, "👥 *KELOLA AKUN*")
    await query.edit_message_text(
        f"{title} ({len(akun_list)} akun)\n\nPilih akun dari daftar di bawah:",
        reply_markup=get_paginated_accounts_keyboard(akun_list, action, page=0),
        parse_mode="Markdown",
    )
    context.user_data.pop("awaiting_acc_search", None)
    return STATE_MAIN_MENU


async def bot_accounts_search_input(update, context):
    """Menerima kata kunci pencarian dari user, lalu render ulang daftar akun terfilter."""
    text = (update.message.text or "").strip()
    action = context.user_data.get("acc_search_action", "list")
    context.user_data.pop("awaiting_acc_search", None)
    if text.startswith("🔙"):
        return await handle_cancel(update, context)
    try:
        akun_list_all = await db_find(collection, {})
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return STATE_MAIN_MENU
    search_map = context.user_data.get("acc_search_query") or {}
    if text.lower() in ("all", "*", "semua", ""):
        search_map.pop(action, None)
        akun_list = akun_list_all
        header_hint = f"filter di-reset — {len(akun_list)} akun"
    else:
        search_map[action] = text
        akun_list = filter_accounts_by_query(akun_list_all, text)
        header_hint = f"filter: `{text}` — {len(akun_list)}/{len(akun_list_all)} akun"
    context.user_data["acc_search_query"] = search_map

    title_map = {
        "list": "📊 *DAFTAR AKUN*",
        "info": "ℹ️ *INFORMASI DETAIL AKUN*",
        "test": "🧪 *TEST KONEKSI AKUN*",
        "delete": "🗑️ *HAPUS AKUN DARI DATABASE*",
        "tags": "🏷️ *KELOLA TAG AKUN*",
        "otp": "🔐 *AMBIL PESAN OTP*",
        "btnid": "🔘 *AMBIL ID BUTTON INTERAKTIF*",
    }
    title = title_map.get(action, "👥 *KELOLA AKUN*")
    if not akun_list:
        await update.message.reply_text(
            f"{title} — {header_hint}\n\n⚠️ Tidak ada akun yang cocok. Coba kata kunci lain.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔎 Cari Lagi", callback_data=f"acc_search:{action}")],
                [InlineKeyboardButton("🔙 Kembali", callback_data="sub_back_akun")],
            ]),
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"{title} — {header_hint}\n\nPilih akun:",
            reply_markup=get_paginated_accounts_keyboard(akun_list, action, page=0),
            parse_mode="Markdown",
        )
    return STATE_MAIN_MENU

async def bot_accounts_action_callback(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"query.answer() gagal: {e}")
    data = query.data
    parts = data.split(":", 2)
    if len(parts) < 3:
        return
        
    action = parts[1]
    phone = parts[2]
    
    try:
        akun = await asyncio.to_thread(collection.find_one, {"nomor_telepon": phone})
    except Exception as e:
        await query.edit_message_text(f"❌ Error DB: {e}")
        return
        
    if not akun:
        await query.edit_message_text("⚠️ Akun tidak ditemukan.")
        return
        
    if action == "list":
        nomor = akun.get("nomor_telepon", "N/A")
        name = akun.get("name", "N/A")
        status = akun.get("status", "aktif")
        tags = ", ".join(akun.get("tags", []) or []) or "Tidak ada tag"
        txt = (
            f"👤 *RINGKASAN AKUN*\n\n"
            f"📞 *Nomor:* `{nomor}`\n"
            f"👤 *Nama:* `{name}`\n"
            f"🏷️ *Tags:* `{tags}`\n"
            f"🚦 *Status:* `{status.upper()}`\n"
        )
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Daftar", callback_data="sub_akun_list")]]
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif action == "info":
        api_id = str(akun.get("api_id", "N/A"))
        api_hash = str(akun.get("api_hash", "N/A"))
        string_sesi = str(akun.get("string_sesi", "N/A"))
        name = akun.get("name", "N/A")
        status = akun.get("status", "aktif")
        tags = ", ".join(akun.get("tags", []) or []) or "-"
        
        session_masked = string_sesi[:15] + "..." + string_sesi[-15:] if len(string_sesi) > 30 else string_sesi
        
        txt = (
            f"ℹ️ *INFORMASI DETAIL AKUN*\n\n"
            f"📞 *Nomor Telepon:* `{phone}`\n"
            f"👤 *Nama Tampilan:* `{name}`\n"
            f"🔑 *API ID:* `{api_id}`\n"
            f"🔐 *API Hash:* `{api_hash}`\n"
            f"🏷️ *Tags:* `{tags}`\n"
            f"🚦 *Status:* `{status.upper()}`\n"
            f"📡 *Session String:* `{session_masked}`"
        )
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Daftar", callback_data="sub_akun_info")]]
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif action == "test":
        await query.edit_message_text(f"⏳ *Testing akun `{phone}`...*\nMenghubungi Telegram API, mohon tunggu.", parse_mode="Markdown")
        api_id = akun.get("api_id")
        api_hash = akun.get("api_hash")
        string_sesi = akun.get("string_sesi")
        
        sukses, user_data, error_msg = await validasi_akun_telegram(api_id, api_hash, string_sesi)
        
        if sukses:
            status_text = "🟢 *AKTIF / NORMAL*"
            update_account_status(phone, "aktif", "Test akun berhasil")
            detail = f"Nama: *{user_data.get('first_name', '')} {user_data.get('last_name', '')}*\nUsername: @{user_data.get('username', '-')}"
        else:
            status_text = "🔴 *BERMASALAH / MATI*"
            detail = f"Penyebab: `{error_msg}`"
            if "expired" in str(error_msg).lower() or "session" in str(error_msg).lower():
                update_account_status(phone, "expired", error_msg)
            else:
                update_account_status(phone, "dibatasi", error_msg)
                
        txt = (
            f"🧪 *HASIL TEST AKUN*\n\n"
            f"📞 *Akun:* `{phone}`\n"
            f"🚦 *Status:* {status_text}\n\n"
            f"{detail}"
        )
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Daftar", callback_data="sub_akun_test")]]
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif action == "delete":
        txt = (
            f"⚠️ *KONFIRMASI HAPUS AKUN*\n\n"
            f"Apakah Anda yakin ingin menghapus akun `{phone}` dari database?\n"
            f"Tindakan ini tidak dapat dibatalkan!"
        )
        keyboard = [
            [InlineKeyboardButton("🔥 Ya, Hapus Permanen!", callback_data=f"conf_delete:{phone}"),
             InlineKeyboardButton("❌ Batal", callback_data="sub_akun_delete")]
        ]
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif action == "tags":
        context.user_data["tag_pilih_phone"] = phone
        current_tags = ", ".join(akun.get("tags", []) or []) or "Tidak ada"
        await query.edit_message_text(
            f"🏷️ *KELOLA TAG AKUN `{phone}`*\n\n"
            f"Tag saat ini: `{current_tags}`\n\n"
            f"Silakan ketik tag baru untuk akun ini (pisahkan dengan koma jika multi-tag):\n"
            f"Atau ketik `/clear` untuk menghapus semua tag.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        context.user_data["last_state"] = STATE_TAG_PILIH
        return STATE_TAG_INPUT
        
    elif action == "otp":
        context.user_data["otp_akun_index"] = 0
        context.user_data["otp_akun_terpilih"] = akun
        
        await query.edit_message_text(
            f"🔐 *AMBIL PESAN OTP - AKUN `{phone}`*\n\n"
            f"Masukkan *ID Chat / Channel / Username* asal pesan OTP (contoh: `777000` untuk Telegram, atau `@username`):\n"
            f"Ketik *default* jika ingin membaca dari bot resmi Telegram (777000).",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_OTP_CHAT_ID
        
    elif action == "btnid":
        context.user_data["btnid_akun_terpilih"] = akun
        await query.edit_message_text(
            f"🔘 *AMBIL ID BUTTON INTERAKTIF - AKUN `{phone}`*\n\n"
            f"Masukkan *username grup/channel/bot* tujuan (contoh: `@namabot` atau `@namagrup`):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_BTNID_TARGET

def get_submenu_akun_keyboard():
    return _make_keyboard(SUBMENU_AKUN)

def get_auto_run_akun_scope_keyboard():
    return _make_keyboard(AUTO_RUN_AKUN_SCOPE_BUTTONS)

def get_reset_status_keyboard():
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in RESET_STATUS_BUTTONS],
        resize_keyboard=True,
    )

def get_akun_scope_keyboard():
    """Membuat keyboard untuk pemilihan scope akun dengan tombol."""
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in AKUN_SCOPE_BUTTONS],
        resize_keyboard=True,
    )

def filter_accounts_by_query(akun_list, query: str):
    q = (query or "").lower()
    if not q:
        return akun_list
    result = []
    for akun in akun_list:
        fields = [
            str(akun.get("name", "")),
            str(akun.get("nomor_telepon", "")),
            str(akun.get("username", "")),
            " ".join(akun.get("tags", []) or []),
        ]
        combined = " ".join(fields).lower()
        if q in combined:
            result.append(akun)
    return result

def _stats_akun_count():
    try:
        return collection.count_documents({}) if collection is not None else 0
    except Exception:
        return 0

async def bot_tambah_api_id(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    
    # Check untuk cancel
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    
    api_id = pesan
    if not api_id.isdigit() or len(api_id) < 5:
        await update.message.reply_text(
            "❌ API ID tidak valid.\nMasukkan *API ID* lagi (angka, minimal 5 digit):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_TAMBAH_API_ID

    context.user_data["api_id"] = api_id
    await update.message.reply_text(
        "🔐 Masukkan *API Hash* Anda:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    return STATE_TAMBAH_API_HASH

async def bot_tambah_api_hash(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    
    # Check untuk cancel
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    
    api_hash = pesan
    if not api_hash or len(api_hash) < 32:
        await update.message.reply_text(
            "❌ API Hash tidak valid.\nMasukkan *API Hash* yang benar:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_TAMBAH_API_HASH

    context.user_data["api_hash"] = api_hash
    await update.message.reply_text(
        "📝 Kirim *String Session* Anda:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    return STATE_TAMBAH_SESSION

async def bot_tambah_session(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    
    # Check untuk cancel
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    
    string_sesi = pesan
    if not string_sesi or len(string_sesi) < 50:
        await update.message.reply_text(
            "❌ String session tidak valid.\nKirim *String Session* yang benar:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_TAMBAH_SESSION

    api_id = context.user_data.get("api_id")
    api_hash = context.user_data.get("api_hash")
    if not api_id or not api_hash:
        await bot_send_main_menu(
            update,
            context,
            "⚠️ Data API ID/API Hash hilang. Silakan ulangi dari awal.",
        )
        return STATE_MAIN_MENU

    await update.message.reply_text("🔍 Memvalidasi akun... Mohon tunggu sebentar.")

    try:
        sukses, user_data, error_msg = await validasi_akun_telegram(api_id, api_hash, string_sesi)
    except Exception as e:
        await bot_send_main_menu(
            update,
            context,
            f"❌ Terjadi error saat validasi: {e}",
        )
        return STATE_MAIN_MENU

    if not sukses or not user_data:
        alasan = error_msg or "String session tidak valid atau akun tidak bisa login."
        await bot_send_main_menu(
            update,
            context,
            f"❌ *VALIDASI GAGAL*\n\nAlasan: {alasan}",
        )
        return STATE_MAIN_MENU

    nomor_telepon = user_data["nomor_telepon"]
    firstname = user_data["firstname"]
    lastname = user_data["lastname"]
    name = f"{firstname} {lastname}".strip()
    username = user_data.get("username") or "Tidak ada username"

    # Simpan data tanpa prompt (force overwrite jika sudah ada)
    success = simpan_data(
        api_id,
        api_hash,
        nomor_telepon,
        string_sesi,
        name,
        user_data,
        interactive=False,
        force_overwrite=True,
    )

    if success:
        await bot_send_main_menu(
            update,
            context,
            (
                "✅ *AKUN BERHASIL DITAMBAHKAN/DIUPDATE!*\n\n"
                f"👤 Nama: {name}\n"
                f"📝 Username: `@{username}`\n"
                f"📱 No. Telp: `{nomor_telepon}`"
            )
            + build_next_steps(["Tambah akun lain", "Lihat semua akun"]),
        )
    else:
        await bot_send_main_menu(
            update,
            context,
            "❌ Gagal menyimpan akun ke database.",
        )

    return STATE_MAIN_MENU

async def bot_btnid_pilih_akun(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler pemilihan akun untuk fitur Ambil ID Button."""
    pesan = (update.message.text or "").strip()

    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    akun_list = context.user_data.get("btnid_akun_list") or []
    if not akun_list:
        await bot_send_main_menu(update, context, "⚠️ Data akun tidak tersedia. Silakan ulangi.")
        return STATE_MAIN_MENU

    try:
        idx = int(pesan) - 1
    except ValueError:
        await update.message.reply_text(
            "❌ Input harus berupa angka.\nMasukkan *nomor urut akun* lagi:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_BTNID_PILIH_AKUN

    if idx < 0 or idx >= len(akun_list):
        await update.message.reply_text(
            "❌ Nomor di luar jangkauan.\nMasukkan nomor yang benar:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_BTNID_PILIH_AKUN

    akun = akun_list[idx]
    context.user_data["btnid_selected_akun"] = akun

    await update.message.reply_text(
        "🎯 Masukkan *username* atau *chat ID* target.\n\n"
        "Contoh:\n"
        "• `@namabot`\n"
        "• `@namachannel`\n"
        "• `123456789` (chat ID)",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_BTNID_TARGET

async def bot_status_akun(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    try:
        akun_list = await db_find(collection, {})
    except Exception as e:
        await bot_send_main_menu(update, context, f"❌ Error saat mengambil data akun: {e}")
        return STATE_MAIN_MENU

    if not akun_list:
        await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan di database.")
        return STATE_MAIN_MENU

    status_counts = {}
    for akun in akun_list:
        status = akun.get("status") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    # Emoji mapping for statuses
    status_emoji = {
        "aktif": "✅",
        "terblokir": "🚫",
        "expired": "⏰",
        "dibatasi": "⚠️",
        "flood_wait": "🕐",
        "timeout": "⏳",
        "unknown": "❓",
    }

    akun_aktif = sum(1 for a in akun_list if a.get('status', 'aktif') not in SKIP_STATUSES)
    akun_skip = len(akun_list) - akun_aktif

    lines = [
        "📊 *STATUS AKUN*\n",
        f"Total akun: {len(akun_list)}",
        f"Siap digunakan: {akun_aktif}",
        f"Akan di-skip: {akun_skip}\n",
    ]
    for status, count in sorted(status_counts.items()):
        emoji = status_emoji.get(status, "❓")
        lines.append(f"  {emoji} {status}: {count}")

    await bot_send_main_menu(
        update,
        context,
        "\n".join(lines) + build_next_steps(["Gunakan 🧪 Test Akun untuk update status", "Kembali ke menu"]),
    )
    return STATE_MAIN_MENU

async def bot_reset_status_menu(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Menu untuk reset status akun bermasalah."""
    try:
        akun_list = await db_find(collection, {})
    except Exception as e:
        await bot_send_main_menu(update, context, f"❌ Error saat mengambil data akun: {e}")
        return STATE_MAIN_MENU

    if not akun_list:
        await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan di database.")
        return STATE_MAIN_MENU

    # Hitung akun bermasalah per status
    problem_accounts = {}
    for akun in akun_list:
        status = akun.get("status", "aktif")
        if status in SKIP_STATUSES:
            problem_accounts.setdefault(status, []).append(akun)

    if not problem_accounts:
        await bot_send_main_menu(
            update, context,
            "✅ Semua akun sudah dalam status *aktif*. Tidak ada yang perlu di-reset."
        )
        return STATE_MAIN_MENU

    status_emoji = {
        "terblokir": "🚫", "expired": "⏰", "dibatasi": "⚠️",
        "flood_wait": "🕐", "timeout": "⏳",
    }

    lines = ["🔄 *RESET STATUS AKUN*\n"]
    lines.append(f"Total akun bermasalah: {sum(len(v) for v in problem_accounts.values())}\n")

    for status, accounts in sorted(problem_accounts.items()):
        emoji = status_emoji.get(status, "❓")
        lines.append(f"{emoji} *{status}*: {len(accounts)} akun")
        for akun in accounts[:5]:
            nomor = akun.get("nomor_telepon", "N/A")
            nama = akun.get("name", "N/A")
            lines.append(f"   • `{nomor}` ({nama})")
        if len(accounts) > 5:
            lines.append(f"   ...dan {len(accounts) - 5} lainnya")

    lines.append("\n*Pilih opsi reset:*")
    lines.append("1️⃣ Reset *SEMUA* akun bermasalah ke aktif")
    lines.append("2️⃣ Reset hanya *timeout* & *flood\\_wait* (sementara)")
    lines.append("3️⃣ Reset hanya *dibatasi*")
    lines.append("4️⃣ Reset hanya *expired*")
    lines.append("5️⃣ Reset hanya *terblokir*")
    lines.append("6️⃣ Reset akun tertentu (masukkan nomor telepon)")

    context.user_data["reset_problem_accounts"] = problem_accounts

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=get_reset_status_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_RESET_STATUS_PILIH

async def bot_reset_status_pilih(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler pilihan reset status."""
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    problem_accounts = context.user_data.get("reset_problem_accounts") or {}

    # Map tombol → nomor pilihan (startswith 1-6)
    pilihan = None
    for n in ("1", "2", "3", "4", "5", "6"):
        if pesan.startswith(n):
            pilihan = n
            break

    if pilihan == "1":
        target_statuses = list(SKIP_STATUSES)
        label = "SEMUA akun bermasalah"
    elif pilihan == "2":
        target_statuses = ["timeout", "flood_wait"]
        label = "akun timeout & flood_wait"
    elif pilihan == "3":
        target_statuses = ["dibatasi"]
        label = "akun dibatasi"
    elif pilihan == "4":
        target_statuses = ["expired"]
        label = "akun expired"
    elif pilihan == "5":
        target_statuses = ["terblokir"]
        label = "akun terblokir"
    elif pilihan == "6":
        await update.message.reply_text(
            "📱 Masukkan *nomor telepon* akun yang ingin di-reset (contoh: 994996946715):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        context.user_data["reset_mode"] = "single"
        return STATE_RESET_STATUS_CONFIRM
    else:
        await update.message.reply_text(
            "❌ Pilihan tidak valid. Gunakan tombol di bawah:",
            reply_markup=get_reset_status_keyboard(),
        )
        return STATE_RESET_STATUS_PILIH

    # Hitung jumlah yang akan di-reset
    count = sum(len(problem_accounts.get(s, [])) for s in target_statuses)
    if count == 0:
        await bot_send_main_menu(
            update, context,
            "⚠️ Tidak ada akun dengan status tersebut."
        )
        return STATE_MAIN_MENU

    context.user_data["reset_target_statuses"] = target_statuses
    context.user_data["reset_label"] = label
    context.user_data["reset_mode"] = "batch"

    await update.message.reply_text(
        f"🔄 *KONFIRMASI RESET*\n\n"
        f"Akan reset *{count}* {label} ke status *aktif*.\n\n"
        f"⚠️ Akun yang benar-benar banned/expired mungkin gagal lagi saat digunakan.\n"
        f"Gunakan 🧪 Test Akun untuk memvalidasi setelah reset.\n\n"
        f"Lanjutkan?",
        reply_markup=get_confirm_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_RESET_STATUS_CONFIRM

async def bot_reset_status_confirm(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler konfirmasi reset status."""
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    mode = context.user_data.get("reset_mode", "batch")

    if mode == "single":
        # Reset satu akun berdasarkan nomor telepon
        nomor = pesan.strip()
        if not nomor:
            await update.message.reply_text(
                "❌ Nomor telepon tidak boleh kosong. Masukkan lagi:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_RESET_STATUS_CONFIRM

        try:
            akun = await db_find_one(collection, {"nomor_telepon": nomor})
            if not akun:
                await bot_send_main_menu(
                    update, context,
                    f"⚠️ Akun dengan nomor `{nomor}` tidak ditemukan."
                )
                return STATE_MAIN_MENU

            old_status = akun.get("status", "aktif")
            if old_status == "aktif":
                await bot_send_main_menu(
                    update, context,
                    f"✅ Akun `{nomor}` sudah dalam status aktif."
                )
                return STATE_MAIN_MENU

            collection.update_one(
                {"nomor_telepon": nomor},
                {"$set": {
                    "status": "aktif",
                    "status_alasan": f"Reset manual dari {old_status}",
                    "status_updated_at": datetime.now().isoformat(),
                }},
            )
            nama = akun.get("name", "N/A")
            log_action("reset_status", {"nomor_telepon": nomor, "old_status": old_status, "new_status": "aktif"})

            await bot_send_main_menu(
                update, context,
                f"✅ Status akun `{nomor}` ({nama}) berhasil di-reset.\n"
                f"  {old_status} → aktif"
                + build_next_steps(["Reset akun lain", "Test akun ini", "Kembali ke menu"]),
            )
        except Exception as e:
            await bot_send_main_menu(update, context, f"❌ Error saat reset: {e}")

        return STATE_MAIN_MENU

    # Mode batch
    target_statuses = context.user_data.get("reset_target_statuses") or []
    label = context.user_data.get("reset_label", "")

    if not target_statuses:
        await bot_send_main_menu(update, context, "⚠️ Data reset tidak lengkap. Silakan ulangi.")
        return STATE_MAIN_MENU

    try:
        result = collection.update_many(
            {"status": {"$in": target_statuses}},
            {"$set": {
                "status": "aktif",
                "status_alasan": f"Reset manual batch dari {', '.join(target_statuses)}",
                "status_updated_at": datetime.now().isoformat(),
            }},
        )
        reset_count = result.modified_count

        log_action("reset_status_batch", {
            "target_statuses": target_statuses,
            "reset_count": reset_count,
        })

        # Ambil status terbaru
        akun_list = await db_find(collection, {})
        aktif_count = sum(1 for a in akun_list if a.get("status", "aktif") == "aktif")

        await bot_send_main_menu(
            update, context,
            f"✅ *RESET SELESAI*\n\n"
            f"• Di-reset: *{reset_count}* {label}\n"
            f"• Total akun aktif sekarang: *{aktif_count}*/{len(akun_list)}\n\n"
            f"💡 Gunakan 🧪 Test Akun untuk memvalidasi akun yang baru di-reset."
            + build_next_steps(["Cek status akun", "Kirim pesan", "Kembali ke menu"]),
        )
    except Exception as e:
        await bot_send_main_menu(update, context, f"❌ Error saat reset batch: {e}")

    return STATE_MAIN_MENU

async def bot_test_akun_pilih(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    akun_list = context.user_data.get("test_akun_list") or []
    if not akun_list:
        await bot_send_main_menu(update, context, "⚠️ Data akun tidak tersedia. Silakan ulangi.")
        return STATE_MAIN_MENU

    try:
        idx = int(pesan) - 1
    except ValueError:
        await update.message.reply_text(
            "❌ Input harus berupa angka. Masukkan nomor akun lagi:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_TEST_AKUN_PILIH

    if idx < 0 or idx >= len(akun_list):
        await update.message.reply_text(
            "❌ Nomor di luar jangkauan. Masukkan nomor yang benar:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_TEST_AKUN_PILIH

    akun = akun_list[idx]
    await update.message.reply_text("🔍 Memvalidasi akun... Mohon tunggu.")

    try:
        sukses, user_data, error_msg = await validasi_akun_telegram(
            akun["api_id"], akun["api_hash"], akun["string_sesi"]
        )
    except Exception as e:
        await bot_send_main_menu(update, context, f"❌ Error saat validasi: {e}")
        return STATE_MAIN_MENU

    status = "aktif" if sukses else "expired"
    if error_msg and "PHONE_NUMBER_BANNED" in str(error_msg):
        status = "terblokir"
    if error_msg and "USER_DEACTIVATED" in str(error_msg):
        status = "terblokir"

    try:
        collection.update_one(
            {"nomor_telepon": akun.get("nomor_telepon")},
            {"$set": {"status": status, "validated": bool(sukses), "status_updated_at": datetime.now().isoformat()}},
        )
    except Exception:
        pass

    detail = (
        f"✅ Akun aktif dan bisa login.\n"
        f"Status: {status}"
        if sukses
        else f"❌ Akun tidak valid.\nStatus: {status}\nAlasan: {error_msg}"
    )

    log_action(
        "test_akun",
        {
            "nomor_telepon": akun.get("nomor_telepon"),
            "status": status,
            "sukses": sukses,
        },
    )

    await bot_send_main_menu(
        update,
        context,
        detail + build_next_steps(["Test akun lain", "Lihat status akun"]),
    )
    return STATE_MAIN_MENU

async def bot_tag_pilih(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    akun_list = context.user_data.get("tag_akun_list") or []
    if not akun_list:
        await bot_send_main_menu(update, context, "⚠️ Data akun tidak tersedia. Silakan ulangi.")
        return STATE_MAIN_MENU

    try:
        idx = int(pesan) - 1
    except ValueError:
        await update.message.reply_text(
            "❌ Input harus berupa angka. Masukkan nomor akun lagi:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_TAG_PILIH

    if idx < 0 or idx >= len(akun_list):
        await update.message.reply_text(
            "❌ Nomor di luar jangkauan. Masukkan nomor yang benar:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_TAG_PILIH

    akun = akun_list[idx]
    context.user_data["tag_selected_account"] = akun
    current_tags = ", ".join(akun.get("tags", []) or []) or "-"
    await update.message.reply_text(
        f"🏷️ Tag saat ini: {current_tags}\nMasukkan tag baru (pisahkan dengan koma):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_TAG_INPUT

async def bot_tag_input(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    akun = context.user_data.get("tag_selected_account")
    if not akun:
        await bot_send_main_menu(update, context, "⚠️ Data akun tidak tersedia. Silakan ulangi.")
        return STATE_MAIN_MENU

    tags = [t.strip() for t in pesan.split(",") if t.strip()]
    try:
        collection.update_one(
            {"nomor_telepon": akun.get("nomor_telepon")},
            {"$set": {"tags": tags}},
        )
    except Exception as e:
        await bot_send_main_menu(update, context, f"❌ Gagal menyimpan tag: {e}")
        return STATE_MAIN_MENU

    log_action(
        "set_tag",
        {"nomor_telepon": akun.get("nomor_telepon"), "tags": tags},
    )

    await bot_send_main_menu(
        update,
        context,
        "✅ Tag berhasil disimpan." + build_next_steps(["Kelola tag akun lain", "Kembali ke menu"]),
    )
    return STATE_MAIN_MENU

async def bot_search_query(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    try:
        akun_list = await db_find(collection, {})
    except Exception as e:
        await bot_send_main_menu(update, context, f"❌ Error saat mengambil data akun: {e}")
        return STATE_MAIN_MENU

    hasil = filter_accounts_by_query(akun_list, pesan)
    if not hasil:
        await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang cocok.")
        return STATE_MAIN_MENU

    lines = [f"🔎 *Hasil Pencarian* ({len(hasil)} akun)\n"]
    for idx, akun in enumerate(hasil, 1):
        tags = ", ".join(akun.get("tags", []) or []) or "-"
        lines.append(f"{idx}. `{akun.get('nomor_telepon', 'N/A')}` | {akun.get('name', 'N/A')} | {tags}")

    await bot_send_main_menu(
        update,
        context,
        "\n".join(lines) + build_next_steps(["Cari lagi dengan kata kunci lain", "Kembali ke menu"]),
    )
    return STATE_MAIN_MENU

async def bot_hapus_akun(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    
    # Check untuk cancel
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    
    text = pesan
    phones = context.user_data.get("hapus_akun_phones") or []

    if not phones:
        await bot_send_main_menu(
            update,
            context,
            "⚠️ Data akun tidak tersedia. Silakan pilih menu Hapus Akun lagi.",
        )
        return STATE_MAIN_MENU

    nomor = None
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(phones):
            nomor = phones[idx]

    if not nomor:
        nomor = text

    try:
        result = collection.delete_one({"nomor_telepon": nomor})
        if result.deleted_count > 0:
            msg = f"✅ Akun dengan nomor `{nomor}` berhasil dihapus."
        else:
            msg = f"⚠️ Akun dengan nomor `{nomor}` tidak ditemukan."
    except Exception as e:
        msg = f"❌ Error saat menghapus akun: {e}"

    await bot_send_main_menu(update, context, msg + build_next_steps(["Hapus akun lain", "Kembali ke menu"]))
    return STATE_MAIN_MENU

async def bot_info_akun_pilih(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler untuk memilih akun yang akan ditampilkan infonya"""
    pesan = (update.message.text or "").strip()
    
    # Check untuk cancel
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    
    akun_list = context.user_data.get("info_akun_list") or []
    text = pesan

    if not akun_list:
        await bot_send_main_menu(
            update,
            context,
            "⚠️ Data akun tidak tersedia. Silakan ulangi dari menu Info Akun.",
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
        return STATE_INFO_AKUN_PILIH

    if idx < 0 or idx >= len(akun_list):
        await update.message.reply_text(
            "❌ Nomor di luar jangkauan.\nMasukkan nomor yang benar:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_INFO_AKUN_PILIH

    akun = akun_list[idx]
    
    # Format informasi akun
    firstname = akun.get('firstname', '')
    lastname = akun.get('lastname', '')
    nama_lengkap = f"{firstname} {lastname}".strip()
    username = akun.get('username', '')
    username_display = f"`@{username}`" if username else "Tidak ada"

    info_message = (
        "```\n"
        "╔══════════════════════════════════╗\n"
        "║     INFORMASI AKUN LENGKAP      ║\n"
        "╚══════════════════════════════════╝\n"
        "```\n\n"
        f"👤 *Nama:* {nama_lengkap}\n"
        f"📱 *Telepon:* `{akun.get('nomor_telepon', 'N/A')}`\n"
        f"🆔 *User ID:* `{akun.get('user_id', 'N/A')}`\n"
        f"📝 *Username:* {username_display}\n\n"
        "Di bawah ini dikirim terpisah supaya mudah disalin."
    ) + build_next_steps(["Lihat akun lain", "Kembali ke menu"])

    await bot_send_main_menu(update, context, info_message)

    api_id = str(akun.get("api_id", "N/A"))
    api_hash = str(akun.get("api_hash", "N/A"))
    string_sesi = str(akun.get("string_sesi", "N/A"))

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🔑 *API ID*\n`{api_id}`",
        parse_mode="Markdown",
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🔐 *API Hash*\n`{api_hash}`",
        parse_mode="Markdown",
    )

    try:
        filename = f"string_session_{akun.get('nomor_telepon', 'akun')}.txt"
        buf = io.BytesIO(string_sesi.encode("utf-8"))
        buf.name = filename
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=buf,
            filename=filename,
            caption="🔗 String Session (file)",
        )
    except Exception:
        pass
    return STATE_MAIN_MENU

async def bot_auto_run_pilih_akun(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    akun_list = context.user_data.get("auto_run_akun_list") or []
    if not akun_list:
        await bot_send_main_menu(update, context, "⚠️ Data akun tidak tersedia.")
        return STATE_MAIN_MENU

    if pesan == "📋 Semua Akun":
        akun_terpilih = akun_list
    elif pesan == "🔢 Jumlah Tertentu":
        await update.message.reply_text(
            f"🔢 Berapa akun? (1-{len(akun_list)}):",
            reply_markup=get_cancel_keyboard(),
        )
        context.user_data["auto_run_wait_jumlah"] = True
        return STATE_AUTO_RUN_PILIH_AKUN
    elif pesan == "🏷️ Berdasarkan Tag":
        await update.message.reply_text(
            "🏷️ Masukkan nama tag:", reply_markup=get_cancel_keyboard()
        )
        context.user_data["auto_run_wait_tag"] = True
        return STATE_AUTO_RUN_PILIH_AKUN
    else:
        if context.user_data.pop("auto_run_wait_jumlah", False):
            if not pesan.isdigit() or int(pesan) < 1 or int(pesan) > len(akun_list):
                await update.message.reply_text(
                    f"❌ Harus 1-{len(akun_list)}. Coba lagi:",
                    reply_markup=get_cancel_keyboard(),
                )
                context.user_data["auto_run_wait_jumlah"] = True
                return STATE_AUTO_RUN_PILIH_AKUN
            akun_terpilih = akun_list[: int(pesan)]
        elif context.user_data.pop("auto_run_wait_tag", False):
            tag = pesan.lower()
            akun_terpilih = [
                a for a in akun_list
                if tag in [t.lower() for t in (a.get("tags", []) or [])]
            ]
            if not akun_terpilih:
                await update.message.reply_text(
                    "⚠️ Tidak ada akun dengan tag tersebut. Coba lagi:",
                    reply_markup=get_cancel_keyboard(),
                )
                context.user_data["auto_run_wait_tag"] = True
                return STATE_AUTO_RUN_PILIH_AKUN
        else:
            await update.message.reply_text(
                "❓ Pilih dari tombol.",
                reply_markup=get_auto_run_akun_scope_keyboard(),
            )
            return STATE_AUTO_RUN_PILIH_AKUN

    akun_terpilih = [a for a in akun_terpilih if a.get("status", "aktif") not in SKIP_STATUSES]
    if not akun_terpilih:
        await bot_send_main_menu(update, context, "⚠️ Tidak ada akun AKTIF yang bisa digunakan.")
        return STATE_MAIN_MENU
    context.user_data["auto_run_akun_terpilih"] = akun_terpilih
    await update.message.reply_text(
        f"✅ Dipilih: *{len(akun_terpilih)}* akun aktif\n\n"
        "🔁 Pilih *mode loop*:",
        reply_markup=get_auto_loop_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_AUTO_RUN_LOOP_MODE

async def bot_sch_akun_scope(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        context.user_data.pop("sch_new", None)
        return await handle_cancel(update, context)
    if pesan == "📋 Semua Akun":
        context.user_data["sch_new"]["akun_scope"] = "all"
        context.user_data["sch_new"]["akun_value"] = ""
        return await _show_sch_confirm(update, context)
    if pesan == "🔢 Jumlah Tertentu":
        context.user_data["sch_new"]["_akun_mode"] = "count"
        akun_count = context.user_data["sch_new"].get("_akun_count", 1)
        await update.message.reply_text(
            f"🔢 Berapa akun? (1-{akun_count}):",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_SCH_AKUN_VALUE
    if pesan == "🏷️ Berdasarkan Tag":
        context.user_data["sch_new"]["_akun_mode"] = "tag"
        await update.message.reply_text(
            "🏷️ Masukkan nama tag:", reply_markup=get_cancel_keyboard()
        )
        return STATE_SCH_AKUN_VALUE
    await update.message.reply_text("❓ Pilih dari tombol di bawah.",
                                    reply_markup=get_auto_run_akun_scope_keyboard())
    return STATE_SCH_AKUN_SCOPE

async def bot_sch_akun_value(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        context.user_data.pop("sch_new", None)
        return await handle_cancel(update, context)
    mode = context.user_data["sch_new"].get("_akun_mode")
    if mode == "count":
        akun_count = context.user_data["sch_new"].get("_akun_count", 1)
        if not pesan.isdigit() or int(pesan) < 1 or int(pesan) > akun_count:
            await update.message.reply_text(
                f"❌ Harus 1-{akun_count}. Coba lagi:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_SCH_AKUN_VALUE
        context.user_data["sch_new"]["akun_scope"] = "count"
        context.user_data["sch_new"]["akun_value"] = pesan
    elif mode == "tag":
        if not pesan:
            await update.message.reply_text("❌ Tag tidak boleh kosong:", reply_markup=get_cancel_keyboard())
            return STATE_SCH_AKUN_VALUE
        context.user_data["sch_new"]["akun_scope"] = "tag"
        context.user_data["sch_new"]["akun_value"] = pesan.lower()
    else:
        context.user_data["sch_new"]["akun_scope"] = "all"
        context.user_data["sch_new"]["akun_value"] = ""
    return await _show_sch_confirm(update, context)


async def bot_delete_confirm_callback(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"query.answer() gagal: {e}")
    data = query.data
    phone = data.split(":", 1)[1]
    
    try:
        res = await asyncio.to_thread(collection.delete_one, {"nomor_telepon": phone})
        if res.deleted_count > 0:
            txt = f"✅ *SUKSES HAPUS AKUN*\n\nAkun dengan nomor `{phone}` berhasil dihapus selamanya dari database."
        else:
            txt = f"⚠️ Akun `{phone}` sudah tidak ada atau sudah dihapus."
    except Exception as e:
        txt = f"❌ *Error saat menghapus akun:* {e}"
        
    keyboard = [[InlineKeyboardButton("🔙 Kembali ke Daftar", callback_data="sub_akun_delete")]]
    await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")



async def bot_login_api_id(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()

    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    api_id = pesan
    if not api_id.isdigit() or len(api_id) < 5:
        await update.message.reply_text(
            "❌ API ID tidak valid.\nMasukkan *API ID* lagi (angka, minimal 5 digit):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_TAMBAH_LOGIN_API_ID

    context.user_data["login_api_id"] = api_id
    await update.message.reply_text(
        "🔐 Masukkan *API Hash* Anda:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    return STATE_TAMBAH_LOGIN_API_HASH




async def bot_login_api_hash(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()

    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    api_hash = pesan
    if not api_hash or len(api_hash) < 32:
        await update.message.reply_text(
            "❌ API Hash tidak valid.\nMasukkan *API Hash* yang benar:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_TAMBAH_LOGIN_API_HASH

    context.user_data["login_api_hash"] = api_hash
    await update.message.reply_text(
        "📱 Masukkan *nomor telepon* Telegram (contoh: +628123456789):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    return STATE_TAMBAH_LOGIN_PHONE




async def bot_login_phone(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()

    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    phone = pesan
    if not phone or not (phone.isdigit() or (phone.startswith("+") and phone[1:].isdigit())):
        await update.message.reply_text(
            "❌ Nomor telepon tidak valid.\nMasukkan nomor telepon yang benar (contoh: +628123456789):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_TAMBAH_LOGIN_PHONE

    api_id = context.user_data.get("login_api_id")
    api_hash = context.user_data.get("login_api_hash")
    if not api_id or not api_hash:
        await bot_send_main_menu(
            update,
            context,
            "⚠️ Data API ID/API Hash hilang. Silakan ulangi dari awal.",
        )
        return STATE_MAIN_MENU

    await update.message.reply_text("📨 Mengirim kode OTP ke Telegram... Mohon tunggu.")

    client = get_telegram_client(None, api_id, api_hash)
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        context.user_data["login_phone"] = phone
        context.user_data["login_phone_code_hash"] = sent.phone_code_hash
        context.user_data["login_session"] = client.session.save()
    except PhoneNumberInvalidError:
        await client.disconnect()
        await update.message.reply_text(
            "❌ Nomor telepon tidak valid di Telegram.\nMasukkan nomor telepon yang benar:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_TAMBAH_LOGIN_PHONE
    except Exception as e:
        await client.disconnect()
        await bot_send_main_menu(
            update,
            context,
            f"❌ Gagal mengirim kode OTP: {e}",
        )
        return STATE_MAIN_MENU

    await client.disconnect()
    await update.message.reply_text(
        "🔐 Masukkan *kode OTP* yang dikirim ke Telegram:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_TAMBAH_LOGIN_CODE




async def bot_login_code(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()

    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    code = pesan.replace(" ", "")
    if not code.isdigit():
        await update.message.reply_text(
            "❌ Kode OTP harus berupa angka.\nMasukkan kode OTP lagi:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_TAMBAH_LOGIN_CODE

    api_id = context.user_data.get("login_api_id")
    api_hash = context.user_data.get("login_api_hash")
    phone = context.user_data.get("login_phone")
    phone_code_hash = context.user_data.get("login_phone_code_hash")
    session_string = context.user_data.get("login_session")

    if not api_id or not api_hash or not phone or not phone_code_hash or not session_string:
        await bot_send_main_menu(
            update,
            context,
            "⚠️ Data login tidak lengkap. Silakan ulangi dari awal.",
        )
        return STATE_MAIN_MENU

    client = get_telegram_client(session_string, api_id, api_hash)
    try:
        await client.connect()
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        me = await client.get_me()
        string_sesi = client.session.save()
    except SessionPasswordNeededError:
        context.user_data["login_session"] = client.session.save()
        await client.disconnect()
        await update.message.reply_text(
            "🔐 Akun ini memakai kata sandi 2FA.\nMasukkan *password Telegram*:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_TAMBAH_LOGIN_PASSWORD
    except PhoneCodeInvalidError:
        await client.disconnect()
        await update.message.reply_text(
            "❌ Kode OTP salah.\nMasukkan kode OTP lagi:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_TAMBAH_LOGIN_CODE
    except PhoneCodeExpiredError:
        try:
            sent = await client.send_code_request(phone)
            context.user_data["login_phone_code_hash"] = sent.phone_code_hash
            context.user_data["login_session"] = client.session.save()
        except Exception as e:
            await client.disconnect()
            await bot_send_main_menu(
                update,
                context,
                f"❌ Gagal mengirim ulang kode OTP: {e}",
            )
            return STATE_MAIN_MENU
        await client.disconnect()
        await update.message.reply_text(
            "⚠️ Kode OTP kadaluarsa. Kode baru sudah dikirim.\nMasukkan kode OTP baru:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_TAMBAH_LOGIN_CODE
    except Exception as e:
        await client.disconnect()
        await bot_send_main_menu(
            update,
            context,
            f"❌ Error saat login: {e}",
        )
        return STATE_MAIN_MENU

    await client.disconnect()

    user_data = {
        "nomor_telepon": me.phone,
        "firstname": me.first_name,
        "lastname": me.last_name if me.last_name else "",
        "username": me.username if me.username else "",
        "user_id": me.id,
    }

    name = f"{user_data['firstname']} {user_data['lastname']}".strip()
    username = user_data.get("username") or "Tidak ada username"

    success = simpan_data(
        api_id,
        api_hash,
        user_data["nomor_telepon"],
        string_sesi,
        name,
        user_data,
        interactive=False,
        force_overwrite=True,
    )

    for key in [
        "login_api_id",
        "login_api_hash",
        "login_phone",
        "login_phone_code_hash",
        "login_session",
    ]:
        context.user_data.pop(key, None)

    if success:
        await bot_send_main_menu(
            update,
            context,
            (
                "✅ *AKUN BERHASIL DITAMBAHKAN/DIUPDATE!*\n\n"
                f"👤 Nama: {name}\n"
                f"📝 Username: `@{username}`\n"
                f"📱 No. Telp: `{user_data['nomor_telepon']}`"
            )
            + build_next_steps(["Tambah akun lain", "Lihat semua akun"]),
        )
    else:
        await bot_send_main_menu(
            update,
            context,
            "❌ Gagal menyimpan akun ke database.",
        )

    return STATE_MAIN_MENU




async def bot_login_password(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()

    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    password = pesan
    if not password:
        await update.message.reply_text(
            "❌ Password tidak boleh kosong.\nMasukkan password lagi:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_TAMBAH_LOGIN_PASSWORD

    api_id = context.user_data.get("login_api_id")
    api_hash = context.user_data.get("login_api_hash")
    session_string = context.user_data.get("login_session")

    if not api_id or not api_hash or not session_string:
        await bot_send_main_menu(
            update,
            context,
            "⚠️ Data login tidak lengkap. Silakan ulangi dari awal.",
        )
        return STATE_MAIN_MENU

    client = get_telegram_client(session_string, api_id, api_hash)
    try:
        await client.connect()
        await client.sign_in(password=password)
        me = await client.get_me()
        string_sesi = client.session.save()
    except Exception as e:
        await client.disconnect()
        await bot_send_main_menu(
            update,
            context,
            f"❌ Error saat verifikasi password: {e}",
        )
        return STATE_MAIN_MENU

    await client.disconnect()

    user_data = {
        "nomor_telepon": me.phone,
        "firstname": me.first_name,
        "lastname": me.last_name if me.last_name else "",
        "username": me.username if me.username else "",
        "user_id": me.id,
    }

    name = f"{user_data['firstname']} {user_data['lastname']}".strip()
    username = user_data.get("username") or "Tidak ada username"

    success = simpan_data(
        api_id,
        api_hash,
        user_data["nomor_telepon"],
        string_sesi,
        name,
        user_data,
        interactive=False,
        force_overwrite=True,
    )

    for key in [
        "login_api_id",
        "login_api_hash",
        "login_phone",
        "login_phone_code_hash",
        "login_session",
    ]:
        context.user_data.pop(key, None)

    if success:
        await bot_send_main_menu(
            update,
            context,
            (
                "✅ *AKUN BERHASIL DITAMBAHKAN/DIUPDATE!*\n\n"
                f"👤 Nama: {name}\n"
                f"📝 Username: `@{username}`\n"
                f"📱 No. Telp: `{user_data['nomor_telepon']}`"
            )
            + build_next_steps(["Tambah akun lain", "Lihat semua akun"]),
        )
    else:
        await bot_send_main_menu(
            update,
            context,
            "❌ Gagal menyimpan akun ke database.",
        )

    return STATE_MAIN_MENU



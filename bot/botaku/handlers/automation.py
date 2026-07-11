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
from telegram.ext import ContextTypes
from ..database import automation_collection, db_count, db_find
from .common import *
async def q_bot_auto_run_loop_mode(update, context): return await bot_inline_opt_bridge(update, context, bot_auto_run_loop_mode)

async def q_bot_auto_run_loop_n(update, context): return await bot_inline_opt_bridge(update, context, bot_auto_run_loop_n)

async def q_bot_auto_run_loop_delay(update, context): return await bot_inline_opt_bridge(update, context, bot_auto_run_loop_delay)

async def q_bot_auto_run_confirm(update, context): return await bot_inline_opt_bridge(update, context, bot_auto_run_confirm)

async def q_bot_auto_step_menu(update, context): return await bot_inline_opt_bridge(update, context, bot_auto_step_menu)

async def bot_auto_mulai_buat(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Mulai alur buat automation baru: minta nama dulu."""
    context.user_data["auto_new"] = {"name": "", "steps": []}
    await update.message.reply_text(
        "➕ *BUAT AUTOMATION BARU*\n\n"
        "📝 Masukkan *nama automation* (contoh: `Claim Harian Bot XYZ`):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_AUTO_NAME

async def bot_auto_nama(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        context.user_data.pop("auto_new", None)
        return await handle_cancel(update, context)
    if not pesan:
        await update.message.reply_text("❌ Nama tidak boleh kosong. Masukkan lagi:",
                                        reply_markup=get_cancel_keyboard())
        return STATE_AUTO_NAME
    if len(pesan) > 60:
        await update.message.reply_text("❌ Nama terlalu panjang (max 60 karakter). Masukkan lagi:",
                                        reply_markup=get_cancel_keyboard())
        return STATE_AUTO_NAME
    context.user_data["auto_new"]["name"] = pesan
    return await _show_step_menu(update, context)

async def _show_step_menu(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    data = context.user_data.get("auto_new") or {}
    steps = data.get("steps", [])
    lines = [f"🤖 *{data.get('name', '')}*\n"]
    if steps:
        lines.append(f"📋 *Steps ({len(steps)}):*")
        for i, s in enumerate(steps, 1):
            lines.append(f"  {i}. {format_step_summary(s)}")
    else:
        lines.append("📋 _Belum ada step._")
    lines.append("\nPilih tindakan berikutnya:")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=get_auto_step_menu_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_AUTO_STEP_MENU

async def bot_auto_step_menu(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        context.user_data.pop("auto_new", None)
        return await handle_cancel(update, context)
    if pesan.startswith("✉️"):
        await update.message.reply_text(
            "✉️ Masukkan *teks pesan* yang akan dikirim:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_AUTO_STEP_SEND_TEXT
    if pesan.startswith("🔘"):
        await update.message.reply_text(
            "🔘 Masukkan *ID tombol (callback_data)*.\n\n"
            "Anda bisa dapatkan ID tombol dari fitur: *Tools & Pengaturan → Ambil ID Button*.\n\n"
            "Contoh ID: `claim_daily_123`",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_AUTO_STEP_CLICK_ID
    if pesan.startswith("⏱️"):
        await update.message.reply_text(
            "⏱️ Masukkan *delay dalam detik* (angka, contoh: `5`):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_AUTO_STEP_DELAY_SEC
    if pesan.startswith("⏳"):
        await update.message.reply_text(
            "⏳ Masukkan *timeout tunggu balasan* dalam detik (contoh: `30`):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_AUTO_STEP_WAIT_TIMEOUT
    if pesan.startswith("📄"):
        await update.message.reply_text(
            "📄 *KIRIM TXT per-AKUN*\n\n"
            "Kirim file `.txt` ATAU paste teks langsung.\n"
            "*Setiap baris = 1 pesan untuk 1 akun*, diurut sesuai urutan akun.\n\n"
            "📌 Jika jumlah akun lebih banyak dari baris, baris akan diulang "
            "(round-robin — akun ke-N dapat baris `N mod total_baris`).\n"
            "📌 Baris kosong akan di-skip.\n\n"
            "Contoh TXT:\n"
            "```\n"
            "Halo, saya akun 1\n"
            "Pesan untuk akun 2\n"
            "Halo dari akun 3\n"
            "```",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_AUTO_STEP_SEND_TXT
    if pesan.startswith("🎲"):
        await update.message.reply_text(
            "🎲 *KIRIM TXT RANDOM*\n\n"
            "Kirim file `.txt` ATAU paste teks langsung.\n"
            "*Setiap baris = 1 kandidat pesan*. Setiap kali step dijalankan, "
            "bot akan memilih *1 baris secara acak* untuk dikirim.\n\n"
            "📌 Baris berbeda dapat dipilih pada setiap akun & setiap loop.\n"
            "📌 Baris kosong akan di-skip otomatis.\n"
            "📌 Maksimal 500 baris / 2 MB.\n\n"
            "Contoh TXT:\n"
            "```\n"
            "Halo kak 👋\n"
            "Selamat pagi!\n"
            "Apa kabar hari ini?\n"
            "```",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_AUTO_STEP_SEND_TXT_RANDOM
    if pesan.startswith("✏️"):
        return await _show_step_edit_menu(update, context)
    if pesan.startswith("💾"):
        return await _finalize_save(update, context)
    await update.message.reply_text(
        "❓ Pilih salah satu tombol step di bawah.",
        reply_markup=get_auto_step_menu_keyboard(),
    )
    return STATE_AUTO_STEP_MENU

async def bot_auto_step_send_text(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = update.message.text or ""
    if pesan.strip().startswith("🔙"):
        return await _show_step_menu(update, context)
    if not pesan.strip():
        await update.message.reply_text("❌ Teks tidak boleh kosong.", reply_markup=get_cancel_keyboard())
        return STATE_AUTO_STEP_SEND_TEXT
    context.user_data["auto_new"]["steps"].append({"type": "send_message", "text": pesan})
    await update.message.reply_text(f"✅ Step ditambahkan: Kirim pesan ({shorten_text(pesan, 60)})")
    return await _show_step_menu(update, context)

async def bot_auto_step_click_id(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await _show_step_menu(update, context)
    if not pesan:
        await update.message.reply_text("❌ ID button tidak boleh kosong.", reply_markup=get_cancel_keyboard())
        return STATE_AUTO_STEP_CLICK_ID
    context.user_data["auto_new"]["steps"].append({"type": "click_button", "button_id": pesan, "scan_limit": 20})
    await update.message.reply_text(f"✅ Step ditambahkan: Klik tombol ID `{shorten_text(pesan, 50)}`",
                                    parse_mode="Markdown")
    return await _show_step_menu(update, context)

async def bot_auto_step_delay(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await _show_step_menu(update, context)
    if not pesan.isdigit() or int(pesan) < 1 or int(pesan) > 86400:
        await update.message.reply_text(
            "❌ Delay harus berupa angka 1-86400 detik. Coba lagi:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_AUTO_STEP_DELAY_SEC
    sec = int(pesan)
    context.user_data["auto_new"]["steps"].append({"type": "delay", "seconds": sec})
    await update.message.reply_text(f"✅ Step ditambahkan: Delay {sec} detik")
    return await _show_step_menu(update, context)

async def bot_auto_step_wait(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await _show_step_menu(update, context)
    if not pesan.isdigit() or int(pesan) < 1 or int(pesan) > 600:
        await update.message.reply_text(
            "❌ Timeout harus 1-600 detik. Coba lagi:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_AUTO_STEP_WAIT_TIMEOUT
    sec = int(pesan)
    context.user_data["auto_new"]["steps"].append({"type": "wait_reply", "timeout": sec})
    await update.message.reply_text(f"✅ Step ditambahkan: Tunggu balasan ({sec}s timeout)")
    return await _show_step_menu(update, context)

async def bot_auto_step_send_txt(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Terima file .txt atau paste teks langsung, parse per-line jadi list pesan."""
    message = update.message
    # Handle tombol 🔙 kembali
    if message.text and message.text.strip().startswith("🔙"):
        return await _show_step_menu(update, context)

    raw_content = None

    # Kasus 1: user upload file TXT
    if message.document is not None:
        doc = message.document
        filename = (doc.file_name or "").lower()
        if not filename.endswith(".txt"):
            await message.reply_text(
                "❌ File harus berekstensi `.txt`. Coba lagi:",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown",
            )
            return STATE_AUTO_STEP_SEND_TXT
        if (doc.file_size or 0) > 2 * 1024 * 1024:  # 2 MB limit
            await message.reply_text(
                "❌ Ukuran file maksimal 2 MB. Coba lagi dengan file lebih kecil:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_AUTO_STEP_SEND_TXT
        try:
            tg_file = await doc.get_file()
            raw_bytes = await tg_file.download_as_bytearray()
            try:
                raw_content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raw_content = raw_bytes.decode("latin-1", errors="replace")
        except Exception as e:
            await message.reply_text(
                f"❌ Gagal download file: {e}",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_AUTO_STEP_SEND_TXT

    # Kasus 2: user paste teks langsung
    elif message.text:
        raw_content = message.text

    if not raw_content:
        await message.reply_text(
            "❌ Kirim file `.txt` atau paste teks langsung.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_AUTO_STEP_SEND_TXT

    # Parse: split per baris, buang line kosong/whitespace-only
    lines = [ln.rstrip("\r\n") for ln in raw_content.splitlines()]
    lines = [ln for ln in lines if ln.strip()]

    if not lines:
        await message.reply_text(
            "❌ Tidak ada baris valid ditemukan. Coba lagi:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_AUTO_STEP_SEND_TXT

    if len(lines) > 500:
        await message.reply_text(
            f"❌ Maksimal 500 baris (Anda kirim {len(lines)}). Kurangi dulu:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_AUTO_STEP_SEND_TXT

    # Simpan step
    context.user_data["auto_new"]["steps"].append({
        "type": "send_txt_line",
        "lines": lines,
        "round_robin": True,
    })

    preview = "\n".join(f"  {i+1}. {shorten_text(line_text, 50)}" for i, line_text in enumerate(lines[:5]))
    if len(lines) > 5:
        preview += f"\n  … dan {len(lines) - 5} baris lagi"

    await message.reply_text(
        f"✅ Step ditambahkan: *Kirim TXT per-Akun* ({len(lines)} baris)\n\n"
        f"Preview:\n{preview}",
        parse_mode="Markdown",
    )
    return await _show_step_menu(update, context)

async def bot_auto_step_send_txt_random(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Terima file .txt atau paste teks langsung, parse per-line.
    Setiap eksekusi step akan memilih 1 baris secara acak."""
    message = update.message
    if message.text and message.text.strip().startswith("🔙"):
        return await _show_step_menu(update, context)

    raw_content = None

    # Kasus 1: upload file TXT
    if message.document is not None:
        doc = message.document
        filename = (doc.file_name or "").lower()
        if not filename.endswith(".txt"):
            await message.reply_text(
                "❌ File harus berekstensi `.txt`. Coba lagi:",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown",
            )
            return STATE_AUTO_STEP_SEND_TXT_RANDOM
        if (doc.file_size or 0) > 2 * 1024 * 1024:
            await message.reply_text(
                "❌ Ukuran file maksimal 2 MB. Coba lagi dengan file lebih kecil:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_AUTO_STEP_SEND_TXT_RANDOM
        try:
            tg_file = await doc.get_file()
            raw_bytes = await tg_file.download_as_bytearray()
            try:
                raw_content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raw_content = raw_bytes.decode("latin-1", errors="replace")
        except Exception as e:
            await message.reply_text(
                f"❌ Gagal download file: {e}",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_AUTO_STEP_SEND_TXT_RANDOM

    # Kasus 2: paste teks langsung
    elif message.text:
        raw_content = message.text

    if not raw_content:
        await message.reply_text(
            "❌ Kirim file `.txt` atau paste teks langsung.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_AUTO_STEP_SEND_TXT_RANDOM

    lines = [ln.rstrip("\r\n") for ln in raw_content.splitlines()]
    lines = [ln for ln in lines if ln.strip()]

    if not lines:
        await message.reply_text(
            "❌ Tidak ada baris valid ditemukan. Coba lagi:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_AUTO_STEP_SEND_TXT_RANDOM

    if len(lines) > 500:
        await message.reply_text(
            f"❌ Maksimal 500 baris (Anda kirim {len(lines)}). Kurangi dulu:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_AUTO_STEP_SEND_TXT_RANDOM

    context.user_data["auto_new"]["steps"].append({
        "type": "send_txt_random",
        "lines": lines,
    })

    preview = "\n".join(f"  {i+1}. {shorten_text(line_text, 50)}" for i, line_text in enumerate(lines[:5]))
    if len(lines) > 5:
        preview += f"\n  … dan {len(lines) - 5} baris lagi"

    await message.reply_text(
        f"✅ Step ditambahkan: *Kirim TXT Random* ({len(lines)} baris)\n"
        f"🎲 Setiap eksekusi akan memilih 1 baris secara acak.\n\n"
        f"Preview:\n{preview}",
        parse_mode="Markdown",
    )
    return await _show_step_menu(update, context)

async def _show_step_edit_menu(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Tampilkan daftar step untuk di-hapus. User balas nomor step → step dihapus.
    Kalau list kosong, otomatis kembali ke menu step."""
    steps = context.user_data.get("auto_new", {}).get("steps", [])
    if not steps:
        await update.message.reply_text(
            "⚠️ Belum ada step yang bisa dikelola. Tambahkan step dulu.",
            reply_markup=get_auto_step_menu_keyboard(),
        )
        return STATE_AUTO_STEP_MENU

    lines = ["✏️ *KELOLA STEP*\n"]
    lines.append("Daftar step saat ini:\n")
    for i, step in enumerate(steps, 1):
        lines.append(f"{i}. {format_step_summary(step)}")
    lines.append("")
    lines.append("💡 Balas *nomor urut* untuk menghapus step tersebut.")
    lines.append("📌 Untuk edit: hapus step lalu tambah ulang dengan input baru.")
    lines.append("🔙 Tekan tombol Kembali untuk selesai.")

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_AUTO_STEP_EDIT

async def bot_auto_step_edit(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await _show_step_menu(update, context)

    steps = context.user_data.get("auto_new", {}).get("steps", [])
    if not steps:
        await update.message.reply_text(
            "⚠️ Tidak ada step.",
            reply_markup=get_auto_step_menu_keyboard(),
        )
        return STATE_AUTO_STEP_MENU

    if not pesan.isdigit():
        await update.message.reply_text(
            "❌ Balas dengan *nomor urut* step yang ingin dihapus (contoh: `1`), "
            "atau tekan 🔙 Kembali.",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_AUTO_STEP_EDIT

    idx = int(pesan)
    if idx < 1 or idx > len(steps):
        await update.message.reply_text(
            f"❌ Nomor tidak valid. Masukkan angka 1-{len(steps)}:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_AUTO_STEP_EDIT

    removed = steps.pop(idx - 1)
    await update.message.reply_text(
        f"🗑️ Step #{idx} dihapus:\n_{format_step_summary(removed)}_",
        parse_mode="Markdown",
    )

    if not steps:
        await update.message.reply_text(
            "✅ Semua step sudah dihapus. Tambahkan step baru atau kembali.",
            reply_markup=get_auto_step_menu_keyboard(),
        )
        return STATE_AUTO_STEP_MENU

    # Tampilkan ulang daftar agar user bisa hapus step lain
    return await _show_step_edit_menu(update, context)

async def bot_automation_callback(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"query.answer() gagal: {e}")
    data = query.data
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await query.edit_message_text("⛔️ Akses ditolak.")
        return STATE_MAIN_MENU
        
    parts = data.split(":")
    prefix = parts[0]
    
    if prefix == "aut_view":
        auto_id = parts[1]
        auto = await asyncio.to_thread(automation_get, user_id, auto_id)
        if not auto:
            await query.edit_message_text("⚠️ Script tidak ditemukan.")
            return STATE_MAIN_MENU
            
        preview = format_automation_preview(auto)
        keyboard = [
            [InlineKeyboardButton("▶️ Jalankan Script", callback_data=f"aut_run_sel:{auto_id}"),
             InlineKeyboardButton("🗑️ Hapus Script", callback_data=f"aut_del_conf:{auto_id}")],
            [InlineKeyboardButton("🔙 Kembali ke Daftar", callback_data="sub_auto_list")]
        ]
        await query.edit_message_text(
            f"ℹ️ *RINCIAN SCRIPT AUTOMATION*\n\n{preview}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return STATE_MAIN_MENU
        
    elif prefix == "aut_del_conf":
        auto_id = parts[1]
        auto = await asyncio.to_thread(automation_get, user_id, auto_id)
        if not auto:
            await query.edit_message_text("⚠️ Script tidak ditemukan.")
            return STATE_MAIN_MENU
            
        txt = (
            f"⚠️ *KONFIRMASI HAPUS AUTOMATION*\n\n"
            f"Apakah Anda yakin ingin menghapus script automation *'{auto.get('name')}'*?\n"
            f"Tindakan ini tidak dapat dibatalkan!"
        )
        keyboard = [
            [InlineKeyboardButton("🔥 Ya, Hapus!", callback_data=f"aut_del_exe:{auto_id}"),
             InlineKeyboardButton("❌ Batal", callback_data="sub_auto_list")]
        ]
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return STATE_MAIN_MENU
        
    elif prefix == "aut_del_exe":
        auto_id = parts[1]
        auto = await asyncio.to_thread(automation_get, user_id, auto_id)
        if auto:
            ok = await asyncio.to_thread(automation_delete, user_id, auto_id)
            if ok:
                txt = f"✅ *SUKSES HAPUS*\n\nScript automation *'{auto.get('name')}'* berhasil dihapus selamanya."
            else:
                txt = "❌ Gagal menghapus script automation."
        else:
            txt = "⚠️ Script sudah tidak ada atau sudah dihapus."
            
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Daftar", callback_data="sub_auto_list")]]
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return STATE_MAIN_MENU
        
    elif prefix == "aut_run_sel":
        auto_id = parts[1]
        auto = await asyncio.to_thread(automation_get, user_id, auto_id)
        if not auto:
            await query.edit_message_text("⚠️ Script tidak ditemukan.")
            return STATE_MAIN_MENU
            
        context.user_data["auto_run_pilih"] = auto
        
        txt = (
            f"▶️ *JALANKAN AUTOMATION: '{auto.get('name')}'*\n\n"
            f"Silakan pilih *Scope Akun* yang akan digunakan untuk menjalankan script ini:"
        )
        keyboard = [
            [InlineKeyboardButton("📋 Semua Akun", callback_data=f"aut_run_scope:all:{auto_id}")],
            [InlineKeyboardButton("🔢 Jumlah Tertentu", callback_data=f"aut_run_scope:count:{auto_id}"),
             InlineKeyboardButton("🏷️ Berdasarkan Tag", callback_data=f"aut_run_scope:tag:{auto_id}")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="sub_auto_list")]
        ]
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return STATE_MAIN_MENU
        
    elif prefix == "aut_run_scope":
        scope = parts[1]
        auto_id = parts[2]
        
        context.user_data["auto_run_scope"] = scope
        
        if scope == "all":
            txt = (
                "🔁 *PILIH LOOP MODE*\n\n"
                "Berapa kali automation ini harus dijalankan per-akun?\n\n"
                "• *Sekali* - 1 kali eksekusi.\n"
                "• *N Kali* - Masukkan jumlah perulangan khusus.\n"
                "• *Infinite* - Berjalan tanpa henti."
            )
            # Set state to STATE_AUTO_RUN_LOOP_MODE so text input or button choice works
            await query.edit_message_text(
                txt,
                reply_markup=get_auto_loop_keyboard(),
                parse_mode="Markdown"
            )
            return STATE_AUTO_RUN_LOOP_MODE
            
        elif scope == "count":
            await query.edit_message_text(
                "🔢 Masukkan *jumlah akun* yang ingin digunakan (contoh: `5`):",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown"
            )
            return STATE_AUTO_RUN_PILIH_AKUN
            
        elif scope == "tag":
            await query.edit_message_text(
                "🏷️ Masukkan *Tag Akun* yang ingin difilter (contoh: `tag1`):",
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown"
            )
            return STATE_AUTO_RUN_PILIH_AKUN

    return STATE_MAIN_MENU

async def bot_auto_daftar(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    user_id = update.effective_user.id
    items = automation_list(user_id)
    if not items:
        await bot_send_main_menu(update, context, "📋 Belum ada automation yang tersimpan.")
        return STATE_MAIN_MENU
    lines = [f"📋 *DAFTAR AUTOMATION* (Total: {len(items)})\n"]
    for i, a in enumerate(items, 1):
        lines.append(
            f"{i}. *{a.get('name', '')}* — {len(a.get('steps', []))} step — `{a.get('id', '')}`"
        )
    lines.append("\n_Tekan ▶️ Jalankan Automation untuk eksekusi._")
    await bot_send_main_menu(update, context, join_lines_truncate(lines))
    return STATE_MAIN_MENU

async def bot_auto_hapus_menu(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    user_id = update.effective_user.id
    items = automation_list(user_id)
    if not items:
        await bot_send_main_menu(update, context, "📋 Belum ada automation yang bisa dihapus.")
        return STATE_MAIN_MENU
    context.user_data["auto_delete_list"] = items
    lines = ["🗑️ *HAPUS AUTOMATION*\n\nBalas dengan *nomor urut* automation yang ingin dihapus:\n"]
    for i, a in enumerate(items, 1):
        lines.append(f"{i}. {a.get('name', '')} — `{a.get('id', '')}`")
    await update.message.reply_text(
        "\n".join(lines), reply_markup=get_cancel_keyboard(), parse_mode="Markdown"
    )
    return STATE_AUTO_DELETE_PILIH

async def bot_auto_delete_pilih(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    items = context.user_data.get("auto_delete_list", [])
    if not pesan.isdigit():
        await update.message.reply_text("❌ Masukkan nomor urut yang valid:", reply_markup=get_cancel_keyboard())
        return STATE_AUTO_DELETE_PILIH
    idx = int(pesan) - 1
    if idx < 0 or idx >= len(items):
        await update.message.reply_text("❌ Nomor di luar range. Coba lagi:", reply_markup=get_cancel_keyboard())
        return STATE_AUTO_DELETE_PILIH
    auto = items[idx]
    ok = automation_delete(update.effective_user.id, auto["id"])
    if ok:
        await bot_send_main_menu(update, context, f"✅ Automation *{auto.get('name', '')}* berhasil dihapus.")
    else:
        await bot_send_main_menu(update, context, "❌ Gagal menghapus automation.")
    return STATE_MAIN_MENU

async def bot_auto_run_pilih(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    user_id = update.effective_user.id
    items = automation_list(user_id)
    if not items:
        await bot_send_main_menu(update, context, "📋 Belum ada automation. Buat dulu lewat ➕ Buat Automation.")
        return STATE_MAIN_MENU
    context.user_data["auto_run_list"] = items
    lines = [
        "▶️ *JALANKAN AUTOMATION*\n",
        "Balas nomor automation (satu atau banyak dengan koma, misal: `1,3,5`):\n",
    ]
    for i, a in enumerate(items, 1):
        lines.append(f"{i}. {a.get('name', '')} — {len(a.get('steps', []))} step")
    await update.message.reply_text(
        "\n".join(lines), reply_markup=get_cancel_keyboard(), parse_mode="Markdown"
    )
    return STATE_AUTO_RUN_PILIH

async def bot_auto_run_pilih_handler(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    items = context.user_data.get("auto_run_list", [])
    parts = [p.strip() for p in pesan.replace(" ", "").split(",") if p.strip()]
    selected_idx = []
    for p in parts:
        if not p.isdigit():
            await update.message.reply_text(
                "❌ Format tidak valid. Gunakan angka/koma (contoh: `1,2,3`):",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_AUTO_RUN_PILIH
        v = int(p) - 1
        if v < 0 or v >= len(items):
            await update.message.reply_text(
                f"❌ Nomor {p} di luar range. Coba lagi:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_AUTO_RUN_PILIH
        if v not in selected_idx:
            selected_idx.append(v)
    context.user_data["auto_run_selected"] = [items[i] for i in selected_idx]
    await update.message.reply_text(
        f"✅ Dipilih {len(selected_idx)} automation.\n\n"
        "🎯 Sekarang masukkan *target chat* (username bot/grup/user, contoh: `@bot_username`):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_AUTO_RUN_TARGET

async def bot_auto_run_target(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    if not pesan:
        await update.message.reply_text("❌ Target tidak boleh kosong:", reply_markup=get_cancel_keyboard())
        return STATE_AUTO_RUN_TARGET
    target = pesan.lstrip("@")
    context.user_data["auto_run_target"] = target
    try:
        akun_list = await db_find(collection, {})
    except Exception as e:
        await bot_send_main_menu(update, context, f"❌ Error baca akun: {e}")
        return STATE_MAIN_MENU
    if not akun_list:
        await bot_send_main_menu(update, context, "⚠️ Tidak ada akun tersimpan.")
        return STATE_MAIN_MENU
    context.user_data["auto_run_akun_list"] = akun_list
    await update.message.reply_text(
        f"🎯 Target: `@{target}`\n\n"
        f"👥 Pilih *akun* yang akan menjalankan automation (total: {len(akun_list)} akun):",
        reply_markup=get_auto_run_akun_scope_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_AUTO_RUN_PILIH_AKUN

async def bot_auto_run_loop_mode(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    if pesan.startswith("1️⃣"):
        context.user_data["auto_run_loop_count"] = 1
        return await _ask_loop_delay(update, context)
    if pesan.startswith("🔢"):
        await update.message.reply_text(
            "🔢 Masukkan jumlah loop (2-10000):",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_AUTO_RUN_LOOP_N
    if pesan.startswith("♾️"):
        context.user_data["auto_run_loop_count"] = 0
        return await _ask_loop_delay(update, context)
    await update.message.reply_text("❓ Pilih salah satu mode.", reply_markup=get_auto_loop_keyboard())
    return STATE_AUTO_RUN_LOOP_MODE

async def bot_auto_run_loop_n(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    if not pesan.isdigit() or int(pesan) < 2 or int(pesan) > 10000:
        await update.message.reply_text(
            "❌ Harus angka 2-10000. Coba lagi:", reply_markup=get_cancel_keyboard()
        )
        return STATE_AUTO_RUN_LOOP_N
    context.user_data["auto_run_loop_count"] = int(pesan)
    return await _ask_loop_delay(update, context)

async def bot_auto_run_loop_delay(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    if not pesan.isdigit() or int(pesan) < 0 or int(pesan) > 86400:
        await update.message.reply_text(
            "❌ Harus angka 0-86400 detik. Coba lagi:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_AUTO_RUN_LOOP_DELAY
    context.user_data["auto_run_loop_delay"] = int(pesan)
    return await _show_run_confirm(update, context)

async def bot_auto_run_confirm(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip().lower()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    if not (pesan.startswith("✅") or "ya, lanjutkan" in pesan or pesan in ("ya", "y", "yes", "oke", "ok")):
        await update.message.reply_text(
            "❓ Tekan *✅ Ya, lanjutkan* untuk jalankan atau 🔙 untuk batal.",
            reply_markup=get_confirm_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_AUTO_RUN_CONFIRM

    selected = context.user_data.get("auto_run_selected", [])
    target = context.user_data.get("auto_run_target", "")
    akun_t = context.user_data.get("auto_run_akun_terpilih", [])
    lc = context.user_data.get("auto_run_loop_count", 1)
    ld = context.user_data.get("auto_run_loop_delay", 0)
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    bot_ref = context.bot

    run_ids = []
    _settings = get_user_settings(context)
    _auto_batch = int(_settings.get("auto_parallel_batch", 0) or 0)
    _auto_adelay = int(_settings.get("auto_account_delay", 0) or 0)

    async def _start_live_dashboard(auto_name, run_id, akun_count):
        """Buat LiveMessage dashboard untuk 1 run, lalu polling stats."""
        start_ts = _now_ts()
        initial_text = render_live_dashboard(
            title=f"AUTOMATION: {auto_name}", icon=ICON["bot"],
            target_summary=f"`@{target}`", accounts_count=akun_count,
            done=0, total=akun_count, sukses=0, gagal=0, skip=0,
            start_ts=start_ts,
            loop_info="♾️ Infinite" if lc == 0 else f"0/{lc}",
            current_line="🚀 Mempersiapkan akun...",
        )
        live = await LiveMessage.create(
            bot_ref, chat_id, initial_text=initial_text,
            reply_markup=build_runtime_inline_keyboard(run_id, kind="auto"),
        )
        return live, start_ts

    async def _dashboard_poller(live, run_id, start_ts, auto_name, akun_count):
        """Poll stats dari running_automations tiap 1.5s, update dashboard."""
        trend_values = []
        last_sukses = 0
        while run_id in running_automations:
            info = running_automations.get(run_id)
            if not info:
                break
            stats_list = info.get("stats_list", [])
            sukses = sum(1 for s in stats_list
                         if s.get("loops_done", 0) > 0 and not s.get("dropped_reason"))
            gagal = sum(1 for s in stats_list if s.get("dropped_reason"))
            done = sukses + gagal
            pause_event = info.get("pause_event")
            paused = pause_event.is_set() if pause_event else False

            # Track trend per 1.5s tick
            delta = sukses - last_sukses
            last_sukses = sukses
            trend_values.append(delta)
            if len(trend_values) > 20:
                trend_values = trend_values[-20:]

            # Loop info: ambil max loops_done
            max_loop = max((s.get("loops_done", 0) for s in stats_list), default=0)
            loop_info = "♾️ Infinite" if lc == 0 else f"{max_loop}/{lc}"

            frame = SPINNER_FRAMES[(int(_now_ts() * 2) % len(SPINNER_FRAMES))]
            current = "⏸ PAUSED — tap Resume untuk lanjut" if paused else \
                      f"{frame} Menjalankan {akun_count} akun paralel..."

            txt = render_live_dashboard(
                title=f"AUTOMATION: {auto_name}" + (" ⏸" if paused else ""),
                icon=ICON["bot"],
                target_summary=f"`@{target}`",
                accounts_count=akun_count,
                done=done, total=akun_count, sukses=sukses, gagal=gagal,
                start_ts=start_ts,
                loop_info=loop_info,
                current_line=current,
                trend_values=trend_values if len(trend_values) >= 3 else None,
            )
            await live.update(
                txt,
                reply_markup=build_runtime_inline_keyboard(run_id, kind="auto", paused=paused),
            )
            await asyncio.sleep(1.5)

    async def _on_complete(info):
        logs = info.get("log_lines", [])
        stats_list = info.get("stats_list", [])
        stats_text = format_run_stats_summary(stats_list)
        elapsed = fmt_duration(_now_ts() - info.get("started_ts", _now_ts()))
        summary = (
            f"{ICON['done']} *AUTOMATION SELESAI*\n\n"
            f"📋 {info.get('name')}\n"
            f"🆔 Run: `{info.get('run_id')}`\n"
            f"{ICON['users']} Akun: {info.get('accounts_count')}\n"
            f"{ICON['timer']} Durasi: *{elapsed}*\n\n"
            f"{stats_text}\n\n"
            f"*Log ({len(logs)} entri):*\n" + join_lines_truncate(logs[-60:], 2000)
        )
        # Finalize live dashboard jika ada
        live = info.get("_live_message")
        if live is not None:
            try:
                await live.finalize(summary[:4000])
            except Exception:
                pass
        else:
            try:
                await bot_ref.send_message(chat_id=chat_id, text=summary, parse_mode="Markdown")
            except Exception:
                try:
                    await bot_ref.send_message(chat_id=chat_id, text=summary)
                except Exception:
                    pass
        # Toast notification
        await send_toast(
            bot_ref, chat_id,
            f"{ICON['success']} Automation *{info.get('name')}* selesai ({elapsed})",
            duration=8,
        )

    for auto in selected:
        run_id, log_lines, _ce = start_automation_run(
            automation=auto,
            akun_list=akun_t,
            target=target,
            loop_count=lc,
            loop_delay=ld,
            owner_user_id=user_id,
            completion_callback=_on_complete,
            parallel_batch=_auto_batch,
            account_delay=_auto_adelay,
        )
        # Setup live dashboard + poller
        try:
            live, start_ts = await _start_live_dashboard(auto["name"], run_id, len(akun_t))
            if run_id in running_automations:
                running_automations[run_id]["_live_message"] = live
            asyncio.create_task(_dashboard_poller(live, run_id, start_ts, auto["name"], len(akun_t)))
        except Exception:
            pass
        run_ids.append((auto["name"], run_id))

    lines = ["🚀 *AUTOMATION DIJALANKAN*\n"]
    for name, rid in run_ids:
        lines.append(f"• {name} — run: `{rid}`")
    lines.append("")
    lines.append(f"👥 {len(akun_t)} akun • 🎯 `@{target}`")
    lines.append(f"🔁 {'♾️ Infinite' if lc == 0 else str(lc) + 'x'}")
    lines.append("")
    lines.append("_Gunakan ⏹️ Stop Automation untuk menghentikan._")
    lines.append("_Laporan otomatis dikirim saat selesai._")

    for k in [
        "auto_run_list", "auto_run_selected", "auto_run_target",
        "auto_run_akun_list", "auto_run_akun_terpilih",
        "auto_run_loop_count", "auto_run_loop_delay",
        "auto_run_wait_jumlah", "auto_run_wait_tag",
    ]:
        context.user_data.pop(k, None)

    await bot_send_main_menu(update, context, "\n".join(lines))
    log_action("automation_run", {
        "user_id": user_id, "target": target,
        "accounts": len(akun_t), "loop_count": lc,
        "automations": [a["name"] for a in selected],
    })
    return STATE_MAIN_MENU

async def bot_auto_stop_menu(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    user_id = update.effective_user.id
    running = list_running_automations(user_id)
    if not running:
        await bot_send_main_menu(update, context, "ℹ️ Tidak ada automation yang sedang berjalan.")
        return STATE_MAIN_MENU
    context.user_data["auto_stop_list"] = running
    lines = [f"⏹️ *STOP AUTOMATION* ({len(running)} berjalan)\n"]
    for i, r in enumerate(running, 1):
        lc = r.get("loop_count", 1)
        loop_label = "♾️" if lc == 0 else f"{lc}x"
        lines.append(
            f"{i}. *{r.get('name')}* — `{r.get('run_id')}`\n"
            f"   🎯 @{r.get('target')} • 👥 {r.get('accounts_count')} • 🔁 {loop_label}"
        )
    lines.append("\nBalas nomor urut untuk stop, atau `semua` untuk hentikan semua:")
    await update.message.reply_text(
        "\n".join(lines), reply_markup=get_cancel_keyboard(), parse_mode="Markdown"
    )
    return STATE_AUTO_STOP_PILIH

async def bot_auto_stop_pilih(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip().lower()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    running = context.user_data.get("auto_stop_list", [])
    user_id = update.effective_user.id
    stopped = []
    if pesan == "semua":
        for r in running:
            if stop_automation_run(r["run_id"], user_id):
                stopped.append(r["name"])
    elif pesan.isdigit():
        idx = int(pesan) - 1
        if idx < 0 or idx >= len(running):
            await update.message.reply_text("❌ Nomor di luar range. Coba lagi:",
                                            reply_markup=get_cancel_keyboard())
            return STATE_AUTO_STOP_PILIH
        r = running[idx]
        if stop_automation_run(r["run_id"], user_id):
            stopped.append(r["name"])
    else:
        await update.message.reply_text("❌ Balas angka atau `semua`.",
                                        reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
        return STATE_AUTO_STOP_PILIH
    if stopped:
        await bot_send_main_menu(
            update, context,
            f"⏹️ Dihentikan: {', '.join(stopped)}\n\n_Task akan berhenti setelah step saat ini selesai._",
        )
    else:
        await bot_send_main_menu(update, context, "⚠️ Tidak ada automation yang dihentikan.")
    return STATE_MAIN_MENU

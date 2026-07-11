from __future__ import annotations
from ..keyboards import *
from ..database import *
from ..telegram_client import *
from ..ux import *
from ..states import *
from ..config import *
from ..config import ADMIN_USER_IDS, BOT_TOKEN, MONGO_URL
import asyncio, json
from telegram import Update
from telegram.ext import ContextTypes
from ..database import collection, db_count, db_find
from .common import *
def get_submenu_export_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("📥 Export JSON", callback_data="sub_export_json"),
         InlineKeyboardButton("🧾 Export Ringkasan", callback_data="sub_export_ringkasan")],
        [InlineKeyboardButton("⬆️ Import JSON", callback_data="sub_import_json")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="sub_back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_submenu_export_keyboard():
    return _make_keyboard(SUBMENU_EXPORT)

def get_cancel_repeat_keyboard():
    """Membuat keyboard dengan tombol cancel untuk proses repeat."""
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in CANCEL_REPEAT_BUTTONS],
        resize_keyboard=True,
    )

async def bot_export_ringkasan(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    try:
        akun_list = await db_find(collection, {})
    except Exception as e:
        await bot_send_main_menu(update, context, f"❌ Error saat membaca database: {e}")
        return STATE_MAIN_MENU

    if not akun_list:
        await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan di database.")
        return STATE_MAIN_MENU

    lines = [f"🧾 *RINGKASAN AKUN* ({len(akun_list)} akun)\n"]
    for idx, akun in enumerate(akun_list, 1):
        username = akun.get("username") or "-"
        tags = ", ".join(akun.get("tags", []) or []) or "-"
        lines.append(f"{idx}. `{akun.get('nomor_telepon', 'N/A')}` | {akun.get('name', 'N/A')} | {username} | {tags}")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n(⚠️ Dipotong karena terlalu panjang)"

    await bot_send_main_menu(
        update,
        context,
        text + build_next_steps(["Gunakan Export JSON untuk file lengkap", "Kembali ke menu"]),
    )
    return STATE_MAIN_MENU

async def bot_import_json_document(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    if update.message is None or update.message.document is None:
        await bot_send_main_menu(update, context, "⚠️ Tidak ada file yang diterima.")
        return STATE_MAIN_MENU

    doc = update.message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".json"):
        await update.message.reply_text(
            "❌ File harus berformat JSON. Kirim ulang file JSON:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_IMPORT_JSON_WAIT

    file = await doc.get_file()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = BASE_DIR / f"import_akun_{timestamp}.json"
    await file.download_to_drive(custom_path=str(filepath))

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        filepath.unlink(missing_ok=True)
        await bot_send_main_menu(update, context, f"❌ Gagal membaca JSON: {e}")
        return STATE_MAIN_MENU

    if not isinstance(data, list):
        filepath.unlink(missing_ok=True)
        await bot_send_main_menu(update, context, "❌ Format JSON harus berupa list akun.")
        return STATE_MAIN_MENU

    sukses = 0
    gagal = 0
    for akun in data:
        try:
            api_id = str(akun.get("api_id", "")).strip()
            api_hash = str(akun.get("api_hash", "")).strip()
            string_sesi = str(akun.get("string_sesi", "")).strip()
            nomor_telepon = str(akun.get("nomor_telepon", "")).strip()
            name = str(akun.get("name", "")).strip() or nomor_telepon
            if not api_id or not api_hash or not string_sesi or not nomor_telepon:
                gagal += 1
                continue
            user_data = {
                "username": akun.get("username", ""),
                "user_id": akun.get("user_id", ""),
                "firstname": akun.get("firstname", ""),
                "lastname": akun.get("lastname", ""),
            }
            ok = simpan_data(
                api_id,
                api_hash,
                nomor_telepon,
                string_sesi,
                name,
                user_data,
                interactive=False,
                force_overwrite=True,
            )
            if ok:
                sukses += 1
            else:
                gagal += 1
        except Exception:
            gagal += 1

    filepath.unlink(missing_ok=True)
    log_action("import_json", {"sukses": sukses, "gagal": gagal})

    await bot_send_main_menu(
        update,
        context,
        f"✅ Import selesai.\nBerhasil: {sukses}\nGagal: {gagal}"
        + build_next_steps(["Lihat semua akun", "Cek status akun"]),
    )
    return STATE_MAIN_MENU

async def bot_repeat_last_action(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    last = get_last_action(context)
    if not last:
        await bot_send_main_menu(update, context, "⚠️ Belum ada aksi terakhir untuk diulang.")
        return STATE_MAIN_MENU

    action = last.get("action")
    data = last.get("data") or {}

    # Deskripsi aksi terakhir
    desc = ""
    if action == "kirim_pesan":
        desc = f"Kirim Pesan ke @{data.get('target')}"
    elif action == "gabung_grup":
        desc = f"Gabung Grup @{data.get('grup_username')}"
    elif action == "kirim_file_txt":
        desc = f"Kirim File TXT ke @{data.get('target')}"
    elif action == "otp":
        desc = "Ambil Pesan OTP"
    else:
        desc = action

    cancel_event = asyncio.Event()
    context.user_data["repeat_cancel_event"] = cancel_event
    context.user_data["repeat_done"] = False

    chat_id = update.effective_chat.id

    # Kirim pesan processing
    await update.message.reply_text(
        f"🔁 *MENGULANG AKSI TERAKHIR*\n\n"
        f"📌 Aksi: {desc}\n\n"
        f"⏳ Sedang memproses...\n"
        f"Tekan tombol di bawah untuk membatalkan.",
        reply_markup=get_cancel_repeat_keyboard(),
        parse_mode="Markdown",
    )

    async def run_repeat_task():
        try:
            hasil = ""
            if action == "kirim_pesan":
                target = data.get("target")
                pesan = data.get("pesan")
                akun_list = data.get("akun_list") or []
                settings = get_user_settings(context)
                hasil = await proses_kirim_akun_terpilih_async(
                    target, pesan, akun_list,
                    delay_detik=settings["kirim_delay"],
                    parallel_batch=settings["parallel_batch"],
                    cancel_event=cancel_event,
                )
            elif action == "gabung_grup":
                # Prioritaskan list targets baru, fallback ke grup_username legacy
                targets = data.get("targets") or data.get("grup_username")
                akun_list = data.get("akun_list") or []
                settings = get_user_settings(context)
                hasil = await proses_join_semua_akun_async(
                    targets,
                    akun_list=akun_list,
                    delay_detik=settings["join_delay"],
                    parallel_batch=settings["parallel_batch"],
                    cancel_event=cancel_event,
                )
            elif action == "kirim_file_txt":
                target = data.get("target")
                pesan_list = data.get("pesan_list") or []
                akun_list = data.get("akun_list") or []
                settings = get_user_settings(context)
                hasil = await proses_kirim_file_round_robin_async(
                    target, pesan_list, akun_list,
                    delay_detik=settings["kirim_delay"],
                    parallel_batch=settings["parallel_batch"],
                    cancel_event=cancel_event,
                )
            elif action == "otp":
                akun = data.get("akun")
                group_id = data.get("group_id")
                jumlah_pesan = data.get("jumlah_pesan")
                if akun:
                    hasil = await ambil_pesan_terbaru_text(
                        akun["api_id"], akun["api_hash"], akun["string_sesi"],
                        group_id, jumlah_pesan,
                    )
                else:
                    hasil = "⚠️ Data aksi terakhir tidak lengkap."
            else:
                hasil = "⚠️ Aksi terakhir tidak dikenali."

            if len(hasil) > 3900:
                hasil = hasil[:3900] + "\n\n(⚠️ Dipotong karena terlalu panjang)"

            context.user_data["repeat_result"] = hasil
            context.user_data["repeat_done"] = True

            # Kirim hasil ke chat
            last_sub = context.user_data.get("last_submenu")
            kb_map = {
                "kirim": get_submenu_kirim_keyboard,
                "akun": get_submenu_akun_keyboard,
                "export": get_submenu_export_keyboard,
                "settings": get_submenu_settings_keyboard,
            }
            kb_func = kb_map.get(last_sub, get_main_menu_keyboard)
            kb = kb_func()

            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=hasil,
                    reply_markup=kb,
                    parse_mode="Markdown",
                )
            except Exception:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=hasil,
                    reply_markup=kb,
                )

        except Exception as e:
            context.user_data["repeat_done"] = True
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Error saat mengulang aksi: {e}",
                    reply_markup=get_submenu_kirim_inline_keyboard(),
                )
            except Exception:
                pass

    # Jalankan di background
    task = asyncio.create_task(run_repeat_task())
    context.user_data["repeat_task"] = task

    return STATE_REPEAT_RUNNING

async def bot_repeat_running(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler untuk STATE_REPEAT_RUNNING - menangani tombol cancel saat repeat berjalan."""
    pesan = (update.message.text or "").strip()

    if pesan.startswith("🔙"):
        # Juga cancel jika kembali ke menu
        cancel_event = context.user_data.get("repeat_cancel_event")
        if cancel_event and not cancel_event.is_set():
            cancel_event.set()
        task = context.user_data.get("repeat_task")
        if task and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=15)
            except (asyncio.TimeoutError, Exception):
                pass
        await bot_send_main_menu(update, context, "❌ Proses dibatalkan, kembali ke menu.")
        return STATE_MAIN_MENU

    if "Batalkan" in pesan or "Cancel" in pesan:
        cancel_event = context.user_data.get("repeat_cancel_event")
        if cancel_event and not cancel_event.is_set():
            cancel_event.set()
            await update.message.reply_text(
                "⏳ Membatalkan proses... Menunggu batch saat ini selesai.",
                parse_mode="Markdown",
            )
        # Tunggu task selesai
        task = context.user_data.get("repeat_task")
        if task and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=30)
            except (asyncio.TimeoutError, Exception):
                pass
        await bot_send_main_menu(update, context, "❌ Proses ulangi aksi telah dibatalkan.")
        return STATE_MAIN_MENU

    # Cek apakah task sudah selesai
    if context.user_data.get("repeat_done"):
        await bot_send_main_menu(update, context, "✅ Proses selesai. Lihat hasil di atas.")
        return STATE_MAIN_MENU

    # Masih berjalan
    await update.message.reply_text(
        "⏳ Proses masih berjalan...\nTekan '❌ Batalkan Proses' untuk membatalkan.",
        reply_markup=get_cancel_repeat_keyboard(),
    )
    return STATE_REPEAT_RUNNING

async def bot_export_json(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler untuk export semua akun ke JSON"""
    try:
        akun_list = await db_find(collection, {})
        
        if not akun_list:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan di database.")
            return STATE_MAIN_MENU
        
        # Hapus _id dari MongoDB sebelum export
        export_data = []
        for akun in akun_list:
            akun_copy = dict(akun)
            akun_copy.pop('_id', None)  # Hapus _id
            export_data.append(akun_copy)
        
        # Generate nama file dengan timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"telegram_accounts_export_{timestamp}.json"
        filepath = BASE_DIR / filename
        
        # Simpan ke file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        # Kirim file ke user
        with open(filepath, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=(
                    f"✅ *Export Berhasil!*\n\n"
                    f"📊 Total akun: {len(export_data)}\n"
                    f"📅 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                ),
                parse_mode="Markdown"
            )
        
        # Hapus file setelah dikirim
        filepath.unlink()
        
        await bot_send_main_menu(
            update,
            context,
            "📥 File JSON telah dikirim. Silakan cek dokumen di atas."
            + build_next_steps(["Export ringkasan ke chat", "Kembali ke menu"])
        )
        
    except Exception as e:
        await bot_send_main_menu(
            update,
            context,
            f"❌ Error saat export: {e}"
        )
    
    return STATE_MAIN_MENU

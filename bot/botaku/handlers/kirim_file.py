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
from ..database import collection, db_count, db_find
from .common import *
async def q_bot_kirim_file_scope(update, context): return await bot_inline_opt_bridge(update, context, bot_kirim_file_scope)

async def q_bot_kirim_file_confirm(update, context): return await bot_inline_opt_bridge(update, context, bot_kirim_file_confirm)

async def proses_kirim_file_round_robin_async(target, pesan_list, akun_list, delay_detik=2, progress_hook=None, parallel_batch=3, cancel_event=None):
    """
    Mengirim pesan dari file TXT ke target menggunakan distribusi round-robin.
    progress_hook(processed, total, sukses, gagal) dipanggil setiap pesan selesai.
    cancel_event: asyncio.Event - jika di-set, pengiriman akan dihentikan.
    """
    if not akun_list:
        return "⚠️ Tidak ada akun yang tersimpan di database."
    if not pesan_list:
        return "⚠️ Tidak ada pesan dalam file TXT."

    hasil = []
    mode_label = f"PARALEL ({parallel_batch} akun/batch)" if parallel_batch > 1 else "SEKUENSIAL"
    hasil.append("📄 *Kirim Pesan dari File TXT (Round-Robin)*\n")
    hasil.append(f"🎯 Target: `@{target}`")
    hasil.append(f"📊 Total pesan: {len(pesan_list)} baris")
    hasil.append(f"👥 Total akun: {len(akun_list)}")
    hasil.append(f"⚡ Mode: {mode_label}\n")

    # Pisahkan akun aktif dan skip
    akun_aktif = []
    akun_skip_list = []
    for akun in akun_list:
        akun_status = akun.get('status', 'aktif')
        if akun_status in SKIP_STATUSES:
            akun_skip_list.append(akun)
        else:
            akun_aktif.append(akun)

    if not akun_aktif:
        return "⚠️ Semua akun dalam status bermasalah. Tidak bisa mengirim pesan."

    if akun_skip_list:
        hasil.append(f"⏭️ {len(akun_skip_list)} akun di-skip (status bermasalah)\n")

    num_akun = len(akun_aktif)
    akun_assignments = [[] for _ in range(num_akun)]
    for idx_pesan, pesan in enumerate(pesan_list):
        akun_idx = idx_pesan % num_akun
        akun_assignments[akun_idx].append((idx_pesan + 1, pesan))

    pesan_per_akun = len(pesan_list) // num_akun
    sisa = len(pesan_list) % num_akun
    hasil.append(f"📋 Distribusi: ~{pesan_per_akun} pesan/akun" + (f" (+1 untuk {sisa} akun pertama)" if sisa > 0 else ""))
    hasil.append("⏳ *Mohon tunggu, sedang diproses...*\n")

    sukses_total = 0
    gagal_total = 0
    detail_errors = {}
    last_detail = ""
    cancelled = False

    max_pesan_per_akun = max(len(msgs) for msgs in akun_assignments)
    total_pengiriman = len(pesan_list)
    processed_count = 0

    for ronde in range(max_pesan_per_akun):
        # Cek cancel sebelum setiap ronde
        if cancel_event and cancel_event.is_set():
            cancelled = True
            break

        tasks_ronde = []
        for akun_idx in range(num_akun):
            if ronde < len(akun_assignments[akun_idx]):
                nomor_baris, pesan_text = akun_assignments[akun_idx][ronde]
                akun = akun_aktif[akun_idx]
                tasks_ronde.append((akun_idx, akun, nomor_baris, pesan_text))

        for batch_start in range(0, len(tasks_ronde), parallel_batch):
            # Cek cancel sebelum setiap batch
            if cancel_event and cancel_event.is_set():
                cancelled = True
                break

            batch = tasks_ronde[batch_start:batch_start + parallel_batch]

            async def _kirim_satu(task_tuple):
                a_idx, akun, no_baris, pesan_text = task_tuple
                nama_akun = akun.get('name', 'Unknown')
                success, err = await kirim_pesan_ke_bot_async(nama_akun, akun, target, pesan_text)
                return a_idx, akun, no_baris, pesan_text, success, err

            coros = [_kirim_satu(item) for item in batch]
            batch_results = await asyncio.gather(*coros, return_exceptions=True)

            for result in batch_results:
                processed_count += 1
                if isinstance(result, Exception):
                    gagal_total += 1
                    err_category = type(result).__name__
                    detail_errors[err_category] = detail_errors.get(err_category, 0) + 1
                    last_detail = f"❌ Error: {shorten_text(str(result), 60)}"
                    hasil.append(f"❌ Error: {shorten_text(str(result), 120)}")
                else:
                    a_idx, akun, no_baris, pesan_text, success, err = result
                    nama_akun = akun.get('name', 'Unknown')
                    nomor = akun.get('nomor_telepon', 'N/A')
                    if success:
                        sukses_total += 1
                        last_detail = f"✅ Baris {no_baris} -> {nomor} ({nama_akun})"
                        hasil.append(f"✅ Baris {no_baris} -> {nomor} ({nama_akun})")
                    else:
                        gagal_total += 1
                        err_category = (err or "unknown").split(":")[0].strip()
                        detail_errors[err_category] = detail_errors.get(err_category, 0) + 1
                        last_detail = f"❌ Baris {no_baris} -> {nomor} — {shorten_text(err, 50)}"
                        hasil.append(f"❌ Baris {no_baris} -> {nomor} ({nama_akun}) — {shorten_text(err, 100)}")

                    log_action("kirim_file_txt", {
                        "nomor_telepon": nomor,
                        "nama": nama_akun,
                        "target": target,
                        "baris": no_baris,
                        "status": "sukses" if success else "gagal",
                        "error": err if not success else None,
                    })

                if progress_hook:
                    await progress_hook(processed_count, total_pengiriman, sukses_total, gagal_total, last_detail)

            if cancelled:
                break

            if batch_start + parallel_batch < len(tasks_ronde):
                await asyncio.sleep(delay_detik)

        if cancelled:
            break

        if ronde + 1 < max_pesan_per_akun:
            await asyncio.sleep(delay_detik)

    hasil.append(f"\n{'='*40}")
    if cancelled:
        belum_terkirim = total_pengiriman - processed_count
        hasil.append("⚠️ *Pengiriman DIBATALKAN oleh user!*")
        hasil.append(f"• Terkirim: {processed_count}/{total_pengiriman}")
        hasil.append(f"• Belum terkirim: {belum_terkirim}")
    else:
        hasil.append("✅ *Proses Selesai!*")
    hasil.append(f"• Berhasil: {sukses_total}")
    hasil.append(f"• Gagal: {gagal_total}")
    hasil.append(f"• Total pesan: {total_pengiriman}")
    hasil.append(f"• Akun aktif: {num_akun}")
    if akun_skip_list:
        hasil.append(f"• Akun di-skip: {len(akun_skip_list)}")

    if detail_errors:
        hasil.append("\n📋 *Rincian Error:*")
        for err_type, count in detail_errors.items():
            hasil.append(f"  • {err_type}: {count}")

    hasil.append(f"{'='*40}")

    return join_lines_truncate(hasil)

async def _run_file_sending_task(chat_id, context, target, pesan_list, akun_terpilih, settings, cancel_event, label_extra=""):
    """Background task: kirim pesan dari file TXT, update progress, dan posting hasil setelah selesai."""
    progress_message = await context.bot.send_message(
        chat_id=chat_id,
        text=_build_progress_text(0, len(pesan_list), 0, 0, "Memulai...", label_extra=label_extra),
    )

    async def progress_hook(processed, total, sukses, gagal, last_detail):
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_message.message_id,
                text=_build_progress_text(processed, total, sukses, gagal, last_detail, label_extra=label_extra),
            )
        except Exception:
            pass

    try:
        hasil = await proses_kirim_file_round_robin_async(
            target,
            pesan_list,
            akun_terpilih,
            delay_detik=settings["kirim_delay"],
            progress_hook=progress_hook,
            parallel_batch=settings["parallel_batch"],
            cancel_event=cancel_event,
        )
    except Exception as e:
        hasil = f"❌ Terjadi error saat mengirim pesan:\n{e}"

    # Simpan hasil
    context.user_data["file_sending_done"] = True
    context.user_data["file_sending_result"] = hasil

    # Kirim hasil ke chat
    try:
        if len(hasil) > 3900:
            hasil = hasil[:3900] + "\n\n(⚠️ Dipotong)"
        await context.bot.send_message(chat_id=chat_id, text=hasil, parse_mode="Markdown")
    except Exception:
        try:
            await context.bot.send_message(chat_id=chat_id, text=hasil)
        except Exception:
            pass

    # Tampilkan opsi setelah selesai
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🔀 *Ingin mengacak pesan dan kirim ulang?*\n\n"
            "Pesan akan diacak sehingga setiap akun mendapatkan pesan berbeda.\n\n"
            "Pilih opsi di bawah:"
        ),
        reply_markup=get_selesai_keyboard(),
        parse_mode="Markdown",
    )

async def bot_kirim_file_target(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler untuk input target username pada fitur Kirim File TXT."""
    pesan = (update.message.text or "").strip()

    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    last_target = context.user_data.get("last_target")
    target = pesan or last_target
    if not target:
        await update.message.reply_text(
            "❌ Username tidak boleh kosong.\nMasukkan username lagi (contoh: `@username`):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_KIRIM_FILE_TARGET

    if target.startswith("@"):
        target = target[1:]

    # Validasi username
    await update.message.reply_text("🔍 Memvalidasi username target... Mohon tunggu.")

    try:
        akun_list = await db_find(collection, {})
        if not akun_list:
            await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan.")
            return STATE_MAIN_MENU

        first_akun = None
        for a in akun_list:
            if a.get('status', 'aktif') not in SKIP_STATUSES:
                first_akun = a
                break

        if not first_akun:
            await bot_send_main_menu(
                update, context,
                "⚠️ Semua akun dalam status bermasalah. Tidak bisa validasi target."
            )
            return STATE_MAIN_MENU

        valid, error_msg = await validasi_target_user(
            first_akun['api_id'], first_akun['api_hash'], first_akun['string_sesi'], target
        )

        if not valid:
            await bot_send_main_menu(
                update, context,
                f"❌ *VALIDASI GAGAL*\n\n{error_msg}\n\n"
                f"💡 Pastikan username ditulis dengan benar."
            )
            return STATE_MAIN_MENU

        await update.message.reply_text("✅ Username valid!")
        context.user_data["file_target"] = target
        context.user_data["file_akun_list"] = akun_list

        await update.message.reply_text(
            "📄 Sekarang kirim *file TXT* yang berisi pesan.\n"
            "Setiap baris = 1 pesan utuh.\n\n"
            "Contoh isi file:\n"
            "`Halo, ini pesan pertama`\n"
            "`Ini pesan kedua`\n"
            "`Pesan ketiga, dst...`",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_KIRIM_FILE_UPLOAD

    except Exception as e:
        await bot_send_main_menu(update, context, f"❌ Error saat validasi: {e}")
        return STATE_MAIN_MENU

async def bot_kirim_file_upload(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler untuk menerima file TXT yang di-upload."""
    # Cek cancel dari teks
    if update.message and update.message.text:
        pesan = (update.message.text or "").strip()
        if pesan.startswith("🔙"):
            return await handle_cancel(update, context)
        await update.message.reply_text(
            "❌ Kirim dalam bentuk *file/dokumen* .txt, bukan teks.\n"
            "Upload file TXT Anda:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_KIRIM_FILE_UPLOAD

    if update.message is None or update.message.document is None:
        await bot_send_main_menu(update, context, "⚠️ Tidak ada file yang diterima.")
        return STATE_MAIN_MENU

    doc = update.message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text(
            "❌ File harus berformat *.txt*\nKirim ulang file TXT:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_KIRIM_FILE_UPLOAD

    # Download dan baca file
    file = await doc.get_file()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = BASE_DIR / f"pesan_file_{timestamp}.txt"
    await file.download_to_drive(custom_path=str(filepath))

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        filepath.unlink(missing_ok=True)
        await bot_send_main_menu(update, context, f"❌ Gagal membaca file: {e}")
        return STATE_MAIN_MENU

    filepath.unlink(missing_ok=True)

    # Filter baris kosong
    pesan_list = [line.strip() for line in lines if line.strip()]

    if not pesan_list:
        await bot_send_main_menu(update, context, "⚠️ File TXT kosong atau tidak ada baris yang valid.")
        return STATE_MAIN_MENU

    context.user_data["file_pesan_list"] = pesan_list

    akun_list = context.user_data.get("file_akun_list") or []
    akun_aktif = [a for a in akun_list if a.get('status', 'aktif') not in SKIP_STATUSES]
    akun_skip = len(akun_list) - len(akun_aktif)

    skip_info = ""
    if akun_skip > 0:
        skip_info = f"\n⚠️ {akun_skip} akun akan di-skip (status bermasalah)\n"

    # Preview beberapa baris pertama
    preview_count = min(5, len(pesan_list))
    preview_lines = "\n".join([f"  {i+1}. {shorten_text(pesan_list[i], 50)}" for i in range(preview_count)])
    if len(pesan_list) > preview_count:
        preview_lines += f"\n  ... dan {len(pesan_list) - preview_count} baris lagi"

    await update.message.reply_text(
        f"✅ File berhasil dibaca!\n\n"
        f"📊 Total baris/pesan: *{len(pesan_list)}*\n"
        f"👥 Total akun: {len(akun_list)} ({len(akun_aktif)} aktif)"
        f"{skip_info}\n\n"
        f"📋 Preview pesan:\n{preview_lines}\n\n"
        f"📊 Pilih akun untuk kirim:",
        reply_markup=get_akun_scope_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_KIRIM_FILE_SCOPE

async def bot_kirim_file_scope(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler untuk memilih scope akun pada fitur Kirim File TXT."""
    pesan = (update.message.text or "").strip()

    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    akun_list = context.user_data.get("file_akun_list") or []
    if not akun_list:
        await bot_send_main_menu(update, context, "⚠️ Data akun tidak tersedia. Silakan ulangi.")
        return STATE_MAIN_MENU

    if pesan == "📋 Semua Akun":
        akun_terpilih = akun_list
    elif pesan == "🔢 Jumlah Tertentu":
        await update.message.reply_text(
            f"🔢 Masukkan jumlah akun (1-{len(akun_list)}):",
            reply_markup=get_cancel_keyboard(),
        )
        context.user_data["file_waiting_jumlah"] = True
        return STATE_KIRIM_FILE_SCOPE
    elif pesan == "🏷️ Berdasarkan Tag":
        await update.message.reply_text(
            "🏷️ Masukkan nama tag (contoh: marketing):",
            reply_markup=get_cancel_keyboard(),
        )
        context.user_data["file_waiting_tag"] = True
        return STATE_KIRIM_FILE_SCOPE
    else:
        if context.user_data.get("file_waiting_jumlah"):
            try:
                jumlah = int(pesan)
            except ValueError:
                await update.message.reply_text(
                    "❌ Input harus berupa angka. Coba lagi:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_FILE_SCOPE
            if jumlah < 1 or jumlah > len(akun_list):
                await update.message.reply_text(
                    f"❌ Jumlah harus antara 1-{len(akun_list)}. Coba lagi:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_FILE_SCOPE
            akun_terpilih = akun_list[:jumlah]
            context.user_data.pop("file_waiting_jumlah", None)
        elif context.user_data.get("file_waiting_tag"):
            tag = pesan.strip().lower()
            if not tag:
                await update.message.reply_text(
                    "❌ Tag tidak boleh kosong. Masukkan nama tag:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_FILE_SCOPE
            akun_terpilih = [
                a for a in akun_list if tag in [t.lower() for t in (a.get("tags", []) or [])]
            ]
            if not akun_terpilih:
                await update.message.reply_text(
                    "⚠️ Tidak ada akun dengan tag tersebut. Coba lagi:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_FILE_SCOPE
            context.user_data.pop("file_waiting_tag", None)
        elif pesan.lower().startswith("tag:"):
            tag = pesan.split(":", 1)[1].strip().lower()
            if not tag:
                await update.message.reply_text(
                    "❌ Tag tidak boleh kosong. Gunakan format tag:nama:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_FILE_SCOPE
            akun_terpilih = [
                a for a in akun_list if tag in [t.lower() for t in (a.get("tags", []) or [])]
            ]
            if not akun_terpilih:
                await update.message.reply_text(
                    "⚠️ Tidak ada akun dengan tag tersebut. Coba lagi:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_FILE_SCOPE
        else:
            try:
                jumlah = int(pesan)
            except ValueError:
                await update.message.reply_text(
                    "❌ Input tidak valid. Pilih opsi dari tombol:",
                    reply_markup=get_akun_scope_keyboard(),
                )
                return STATE_KIRIM_FILE_SCOPE
            if jumlah < 1 or jumlah > len(akun_list):
                await update.message.reply_text(
                    f"❌ Jumlah harus antara 1-{len(akun_list)}. Coba lagi:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_FILE_SCOPE
            akun_terpilih = akun_list[:jumlah]

    context.user_data["file_akun_terpilih"] = akun_terpilih

    pesan_list = context.user_data.get("file_pesan_list") or []
    target = context.user_data.get("file_target")
    akun_aktif_count = sum(1 for a in akun_terpilih if a.get('status', 'aktif') not in SKIP_STATUSES)
    # settings unused - FIXED: removed

    pesan_per_akun = len(pesan_list) // akun_aktif_count if akun_aktif_count > 0 else 0
    sisa = len(pesan_list) % akun_aktif_count if akun_aktif_count > 0 else 0

    await update.message.reply_text(
        f"📦 *RINGKASAN KIRIM FILE TXT*\n\n"
        f"🎯 Target: `@{target}`\n"
        f"📄 Total pesan: {len(pesan_list)} baris\n"
        f"👥 Akun dipilih: {len(akun_terpilih)} ({akun_aktif_count} aktif)\n"
        f"📋 Distribusi: ~{pesan_per_akun} pesan/akun"
        + (f" (+1 untuk {sisa} akun)" if sisa > 0 else "")
        + "\n🔄 Mode: Round-Robin\n\n"
        "Konfirmasi untuk melanjutkan.",
        reply_markup=get_confirm_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_KIRIM_FILE_CONFIRM

async def bot_kirim_file_confirm(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler konfirmasi: mulai kirim sebagai background task agar bisa di-cancel."""
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    target = context.user_data.get("file_target")
    akun_terpilih = context.user_data.get("file_akun_terpilih") or []
    pesan_list = context.user_data.get("file_pesan_list") or []

    if not target or not akun_terpilih or not pesan_list:
        await bot_send_main_menu(update, context, "⚠️ Data tidak lengkap. Silakan ulangi.")
        return STATE_MAIN_MENU

    settings = get_user_settings(context)

    # Buat cancel event
    cancel_event = asyncio.Event()
    context.user_data["file_cancel_event"] = cancel_event
    context.user_data["file_sending_done"] = False

    await update.message.reply_text(
        f"⏳ *MENGIRIM PESAN DARI FILE TXT...*\n\n"
        f"🎯 Target: `@{target}`\n"
        f"📄 Total: {len(pesan_list)} pesan\n"
        f"👥 Akun: {len(akun_terpilih)}\n\n"
        f"Tekan *❌ Batalkan Pengiriman* untuk menghentikan.",
        reply_markup=get_cancel_sending_keyboard(),
        parse_mode="Markdown"
    )

    # Jalankan kirim sebagai background task
    context.user_data["last_target"] = target
    set_last_action(
        context,
        "kirim_file_txt",
        {"target": target, "pesan_list": pesan_list, "akun_list": akun_terpilih},
    )
    asyncio.create_task(
        _run_file_sending_task(
            update.effective_chat.id, context, target, pesan_list,
            akun_terpilih, settings, cancel_event,
        )
    )

    return STATE_KIRIM_FILE_SENDING

async def bot_kirim_file_sending(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler saat pengiriman berlangsung - bisa cancel, atau handle post-completion."""
    pesan = (update.message.text or "").strip()

    # Cek apakah pengiriman sudah selesai
    if context.user_data.get("file_sending_done"):
        # Pengiriman sudah selesai, handle opsi post-completion
        if pesan.startswith("🔀"):
            # Acak dan kirim ulang
            target = context.user_data.get("file_target")
            akun_terpilih = context.user_data.get("file_akun_terpilih") or []
            pesan_list = context.user_data.get("file_pesan_list") or []

            if not target or not akun_terpilih or not pesan_list:
                await bot_send_main_menu(update, context, "⚠️ Data tidak lengkap. Silakan ulangi dari awal.")
                return STATE_MAIN_MENU

            # Acak pesan
            pesan_acak = pesan_list.copy()
            random.shuffle(pesan_acak)
            context.user_data["file_pesan_list"] = pesan_acak

            settings = get_user_settings(context)
            cancel_event = asyncio.Event()
            context.user_data["file_cancel_event"] = cancel_event
            context.user_data["file_sending_done"] = False

            set_last_action(
                context,
                "kirim_file_txt",
                {"target": target, "pesan_list": pesan_acak, "akun_list": akun_terpilih},
            )

            await update.message.reply_text(
                f"🔀 *MENGIRIM PESAN ACAK...*\n\n"
                f"🎯 Target: `@{target}`\n"
                f"📄 Total: {len(pesan_acak)} pesan (DIACAK)\n"
                f"👥 Akun: {len(akun_terpilih)}\n\n"
                f"Tekan *❌ Batalkan Pengiriman* untuk menghentikan.",
                reply_markup=get_cancel_sending_keyboard(),
                parse_mode="Markdown"
            )

            asyncio.create_task(
                _run_file_sending_task(
                    update.effective_chat.id, context, target, pesan_acak,
                    akun_terpilih, settings, cancel_event, label_extra=" (ACAK)",
                )
            )
            return STATE_KIRIM_FILE_SENDING

        if pesan.startswith("🔙"):
            return await handle_cancel(update, context)

        # Input tidak dikenali saat sudah selesai
        await update.message.reply_text(
            "Pilih opsi di bawah:\n🔀 Acak & Kirim Ulang\n🔙 Kembali ke Menu Utama",
            reply_markup=get_selesai_keyboard(),
        )
        return STATE_KIRIM_FILE_SENDING

    # ===== Pengiriman masih berlangsung =====

    # Cancel pengiriman
    if pesan.startswith("❌") or "batal" in pesan.lower():
        cancel_event = context.user_data.get("file_cancel_event")
        if cancel_event:
            cancel_event.set()
        await update.message.reply_text(
            "⚠️ *Membatalkan pengiriman...*\n"
            "Menunggu batch saat ini selesai, lalu proses dihentikan.",
            parse_mode="Markdown",
        )
        return STATE_KIRIM_FILE_SENDING

    if pesan.startswith("🔙"):
        cancel_event = context.user_data.get("file_cancel_event")
        if cancel_event:
            cancel_event.set()
        await update.message.reply_text(
            "⚠️ *Membatalkan pengiriman...*\n"
            "Menunggu batch saat ini selesai.",
            parse_mode="Markdown",
        )
        return STATE_KIRIM_FILE_SENDING

    # Pesan lain saat sedang kirim
    await update.message.reply_text(
        "⏳ Pengiriman sedang berjalan.\n"
        "Tekan *❌ Batalkan Pengiriman* untuk menghentikan.",
        reply_markup=get_cancel_sending_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_KIRIM_FILE_SENDING

async def bot_kirim_file_selesai(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Fallback handler jika masih ada user di state ini."""
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    if pesan.startswith("🔀"):
        # Redirect ke sending handler
        context.user_data["file_sending_done"] = True
        return await bot_kirim_file_sending(update, context)
    return await handle_cancel(update, context)

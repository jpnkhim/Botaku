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
from ..database import collection, db_count, db_find
from .common import *
async def kirim_pesan_ke_bot_async(nama_akun, data, target, pesan):
    """Mengirim pesan dari satu akun ke bot/user - dengan timeout dan error handling pembatasan"""
    client = None
    nomor = data.get('nomor_telepon', 'N/A')
    try:
        client = get_telegram_client(
            data['string_sesi'], 
            data['api_id'], 
            data['api_hash'],
            connection_retries=1,
            retry_delay=1,
            timeout=TELEGRAM_CONNECT_TIMEOUT,
        )
        
        # Gunakan safe_connect_and_check daripada client.start()
        ok, connect_err = await safe_connect_and_check(client, timeout=TELEGRAM_CONNECT_TIMEOUT)
        if not ok:
            # Tandai akun bermasalah berdasarkan error
            if "TIMEOUT" in str(connect_err).upper():
                update_account_status(nomor, "timeout", connect_err)
            elif "SESSION" in str(connect_err).upper() or "expired" in str(connect_err).lower():
                update_account_status(nomor, "expired", connect_err)
            else:
                # Cek apakah error menunjukkan restriction
                update_account_status(nomor, "timeout", connect_err)
            return False, f"CONNECT_FAIL: {connect_err}"
        
        await safe_telegram_operation(client.send_message(target, pesan), timeout=TELEGRAM_OP_TIMEOUT)
        
        # Jika berhasil dan status sebelumnya bermasalah, reset ke aktif
        prev_status = data.get('status', 'aktif')
        if prev_status != 'aktif':
            update_account_status(nomor, "aktif", "Berhasil kirim pesan")
        
        return True, None
        
    except asyncio.TimeoutError:
        update_account_status(nomor, "timeout", "Timeout saat kirim pesan")
        return False, "TIMEOUT: Akun tidak merespon, kemungkinan dibatasi/diblokir"
    except FloodWaitError as e:
        update_account_status(nomor, "flood_wait", f"FloodWait {e.seconds}s")
        return False, f"FLOOD_WAIT: Harus tunggu {e.seconds} detik (skip ke akun berikutnya)"
    except (UserDeactivatedBanError, InputUserDeactivatedError) as e:
        update_account_status(nomor, "terblokir", str(e))
        return False, "BANNED: Akun dinonaktifkan/banned"
    except AuthKeyUnregisteredError as e:
        update_account_status(nomor, "expired", str(e))
        return False, "EXPIRED: Session tidak valid"
    except (PeerFloodError, UserBannedInChannelError, ChatWriteForbiddenError) as e:
        update_account_status(nomor, "dibatasi", str(e))
        return False, f"RESTRICTED: {type(e).__name__}"
    except (ConnectionError, OSError, ConnectionResetError) as e:
        update_account_status(nomor, "timeout", f"Connection error: {e}")
        return False, f"CONNECTION_ERROR: {type(e).__name__}: {e}"
    except Exception as e:
        # Cek apakah error generik menunjukkan pembatasan
        is_restricted, status, alasan = is_account_restricted_error(e)
        if is_restricted:
            update_account_status(nomor, status, alasan)
            return False, f"{status.upper()}: {alasan}"
        return False, str(e)
    finally:
        await safe_disconnect(client)

async def proses_kirim_akun_terpilih_async(target, pesan, akun_list, delay_detik=2, progress_hook=None, parallel_batch=3, cancel_event=None, stats_hook=None, pause_event=None):
    """Memproses pengiriman pesan ke akun yang dipilih - PARALLEL BATCH MODE"""
    if not akun_list:
        return "⚠️ Tidak ada akun yang tersimpan di database."
    
    hasil = []
    mode_label = f"PARALEL ({parallel_batch} akun/batch)" if parallel_batch > 1 else "SEKUENSIAL"
    hasil.append(f"📊 *Mengirim pesan ke {len(akun_list)} akun...*\n")
    hasil.append(f"🎯 Target: `@{target}`")
    hasil.append(f"💬 Pesan: {pesan}")
    hasil.append(f"⚡ Mode: {mode_label}\n")
    hasil.append("⏳ *Mohon tunggu, sedang diproses...*\n")
    
    sukses = 0
    gagal = 0
    dilewati = 0
    cancelled = False
    detail_errors = {}  # Track error types for report
    
    # Pisahkan akun aktif dan yang di-skip
    akun_aktif = []
    for idx, akun in enumerate(akun_list, 1):
        nama_akun = akun.get('name', 'Unknown')
        nomor = akun.get('nomor_telepon', 'N/A')
        akun_status = akun.get('status', 'aktif')
        
        if akun_status in SKIP_STATUSES:
            dilewati += 1
            alasan_skip = akun.get('status_alasan', akun_status)
            hasil.append(f"{idx}. ⏭️ {nomor} ({nama_akun}) — SKIP: {akun_status} ({shorten_text(alasan_skip, 60)})")
            log_action(
                "kirim_pesan",
                {
                    "nomor_telepon": nomor,
                    "nama": nama_akun,
                    "target": target,
                    "status": "dilewati",
                    "alasan": f"status akun: {akun_status}",
                },
            )
        else:
            akun_aktif.append((idx, akun))
    
    # Proses akun aktif dalam batch paralel
    processed_count = 0
    for batch_start in range(0, len(akun_aktif), parallel_batch):
        # Cek cancel sebelum setiap batch
        if cancel_event and cancel_event.is_set():
            cancelled = True
            break

        batch = akun_aktif[batch_start:batch_start + parallel_batch]
        
        # Jalankan batch secara paralel
        async def _kirim_satu(idx_akun_tuple):
            idx, akun = idx_akun_tuple
            nama_akun = akun.get('name', 'Unknown')
            return idx, akun, await kirim_pesan_ke_bot_async(nama_akun, akun, target, pesan)
        
        tasks = [_kirim_satu(item) for item in batch]
        for completed_task in asyncio.as_completed(tasks):
            processed_count += 1
            try:
                result = await completed_task
                idx, akun, (success, err) = result
                nama_akun = akun.get('name', 'Unknown')
                nomor = akun.get('nomor_telepon', 'N/A')
                if success:
                    sukses += 1
                    hasil.append(f"{idx}. ✅ {nomor} ({nama_akun})")
                else:
                    gagal += 1
                    err_category = (err or "unknown").split(":")[0].strip()
                    detail_errors[err_category] = detail_errors.get(err_category, 0) + 1
                    hasil.append(f"{idx}. ❌ {nomor} ({nama_akun}) — {shorten_text(err, 120)}")
                
                # Non-blocking db logging
                await asyncio.to_thread(log_action, "kirim_pesan", {"nomor_telepon": nomor, "nama": nama_akun, "target": target, "status": "sukses" if success else "gagal", "error": err if not success else None})
                
            except Exception as e:
                gagal += 1
                err_str = str(e)
                err_category = type(e).__name__
                detail_errors[err_category] = detail_errors.get(err_category, 0) + 1
                hasil.append(f"❌ Akun bermasalah — {shorten_text(err_str, 120)}")
                
            # Update screen immediately after EACH individual account finishes!
            if stats_hook:
                try:
                    await stats_hook({
                        "done": processed_count,
                        "total": len(akun_aktif),
                        "sukses": sukses,
                        "gagal": gagal,
                        "skip": dilewati,
                        "current_target": target,
                    })
                except Exception:
                    pass
        
        if progress_hook:
            await progress_hook(processed_count + dilewati, len(akun_list), True)

        # Stats hook untuk dashboard
        if stats_hook:
            try:
                await stats_hook({
                    "done": processed_count,
                    "total": len(akun_aktif),
                    "sukses": sukses,
                    "gagal": gagal,
                    "skip": dilewati,
                    "current_target": target,
                })
            except Exception:
                pass

        # Pause support
        if pause_event is not None:
            while pause_event.is_set():
                if cancel_event and cancel_event.is_set():
                    break
                await asyncio.sleep(0.5)

        # Delay antar batch (bukan antar akun) untuk mengurangi rate limit
        if batch_start + parallel_batch < len(akun_aktif):
            await asyncio.sleep(delay_detik)
    
    hasil.append(f"\n{'='*40}")
    if cancelled:
        belum = len(akun_aktif) - processed_count
        hasil.append("⚠️ *Pengiriman DIBATALKAN oleh user!*")
        hasil.append(f"• Terkirim: {processed_count}/{len(akun_aktif)}")
        hasil.append(f"• Belum terkirim: {belum}")
    else:
        hasil.append("✅ *Proses Selesai!*")
    hasil.append(f"• Berhasil: {sukses}")
    hasil.append(f"• Gagal: {gagal}")
    if dilewati > 0:
        hasil.append(f"• Dilewati (akun bermasalah): {dilewati}")
    hasil.append(f"• Mode: {mode_label}")
    
    # Laporan detail error
    if detail_errors:
        hasil.append("\n📋 *Rincian Error:*")
        for err_type, count in detail_errors.items():
            hasil.append(f"  • {err_type}: {count} akun")
    
    hasil.append(f"{'='*40}")
    
    return join_lines_truncate(hasil)

async def q_bot_kirim_confirm(update, context): return await bot_inline_opt_bridge(update, context, bot_kirim_confirm)

async def q_bot_kirim_cepat_confirm(update, context): return await bot_inline_opt_bridge(update, context, bot_kirim_cepat_confirm)

async def q_bot_kirim_cepat_scope(update, context): return await bot_inline_opt_bridge(update, context, bot_kirim_cepat_scope)

async def bot_kirim_target(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    
    # Check untuk cancel
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
        return STATE_KIRIM_TARGET

    if target.startswith("@"):
        target = target[1:]

    # Validasi username terlebih dahulu
    await update.message.reply_text("🔍 Memvalidasi username target... Mohon tunggu.")
    
    try:
        akun_list = await db_find(collection, {})
        if not akun_list:
            await bot_send_main_menu(
                update,
                context,
                "⚠️ Tidak ada akun yang tersimpan."
            )
            return STATE_MAIN_MENU
        
        # Cari akun pertama yang aktif untuk validasi (jangan pakai akun bermasalah)
        first_akun = None
        for a in akun_list:
            if a.get('status', 'aktif') not in SKIP_STATUSES:
                first_akun = a
                break
        
        if not first_akun:
            await bot_send_main_menu(
                update,
                context,
                "⚠️ Semua akun dalam status bermasalah. Tidak bisa validasi target.\n"
                "Gunakan 🧪 Test Akun untuk memperbarui status akun."
            )
            return STATE_MAIN_MENU
        
        valid, error_msg = await validasi_target_user(
            first_akun['api_id'],
            first_akun['api_hash'],
            first_akun['string_sesi'],
            target
        )
        
        if not valid:
            await bot_send_main_menu(
                update,
                context,
                (
                    f"❌ *VALIDASI GAGAL*\n\n"
                    f"{error_msg}\n\n"
                    f"💡 *Tips:*\n"
                    f"• Pastikan username ditulis dengan benar\n"
                    f"• Username harus tanpa spasi\n"
                    f"• Cek apakah user/bot tersebut aktif"
                )
            )
            return STATE_MAIN_MENU
        
        await update.message.reply_text("✅ Username valid!")
        
        context.user_data["kirim_target"] = target
        context.user_data["kirim_akun_list"] = akun_list
        
        # Hitung akun yang bisa digunakan (tidak termasuk yang di-skip)
        akun_aktif = [a for a in akun_list if a.get('status', 'aktif') not in SKIP_STATUSES]
        akun_skip = len(akun_list) - len(akun_aktif)
        
        skip_info = ""
        if akun_skip > 0:
            skip_info = f"\n⚠️ {akun_skip} akun akan di-skip (status bermasalah)\n"
        
        # Tampilkan opsi jumlah akun dengan tombol
        await update.message.reply_text(
            f"📊 *PILIHAN PENGIRIMAN*\n\n"
            f"Total akun tersedia: {len(akun_list)} ({len(akun_aktif)} aktif)"
            f"{skip_info}\n\n"
            f"Pilih opsi pengiriman:",
            reply_markup=get_akun_scope_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_KIRIM_PILIH_AKUN
        
    except Exception as e:
        await bot_send_main_menu(
            update,
            context,
            f"❌ Error saat validasi: {e}"
        )
        return STATE_MAIN_MENU

async def bot_kirim_pilih_akun(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler untuk memilih jumlah akun yang akan mengirim pesan"""
    pesan = (update.message.text or "").strip()
    
    # Check untuk cancel
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)
    
    akun_list = context.user_data.get("kirim_akun_list") or []
    
    if not akun_list:
        await bot_send_main_menu(
            update,
            context,
            "⚠️ Data akun tidak tersedia. Silakan ulangi dari menu Kirim Pesan."
        )
        return STATE_MAIN_MENU
    
    try:
        if pesan == "📋 Semua Akun":
            # Semua akun
            akun_terpilih = akun_list
        elif pesan == "🔢 Jumlah Tertentu":
            # Minta input jumlah
            await update.message.reply_text(
                f"🔢 Berapa akun yang akan mengirim pesan? (1-{len(akun_list)}):",
                reply_markup=get_cancel_keyboard()
            )
            context.user_data["kirim_waiting_jumlah"] = True
            return STATE_KIRIM_PILIH_AKUN
        elif pesan == "🏷️ Berdasarkan Tag":
            # Minta input nama tag
            await update.message.reply_text(
                "🏷️ Masukkan nama tag (contoh: marketing):",
                reply_markup=get_cancel_keyboard()
            )
            context.user_data["kirim_waiting_tag"] = True
            return STATE_KIRIM_PILIH_AKUN
        else:
            # Cek apakah sedang menunggu input jumlah
            if context.user_data.get("kirim_waiting_jumlah"):
                jumlah = int(pesan)
                if jumlah < 1 or jumlah > len(akun_list):
                    await update.message.reply_text(
                        f"❌ Jumlah harus antara 1-{len(akun_list)}. Coba lagi:",
                        reply_markup=get_cancel_keyboard()
                    )
                    return STATE_KIRIM_PILIH_AKUN
                akun_terpilih = akun_list[:jumlah]
                context.user_data.pop("kirim_waiting_jumlah", None)
            elif context.user_data.get("kirim_waiting_tag"):
                tag = pesan.strip().lower()
                if not tag:
                    await update.message.reply_text(
                        "❌ Tag tidak boleh kosong. Masukkan nama tag:",
                        reply_markup=get_cancel_keyboard(),
                    )
                    return STATE_KIRIM_PILIH_AKUN
                akun_terpilih = [
                    a for a in akun_list if tag in [t.lower() for t in (a.get("tags", []) or [])]
                ]
                if not akun_terpilih:
                    await update.message.reply_text(
                        "⚠️ Tidak ada akun dengan tag tersebut. Coba lagi:",
                        reply_markup=get_cancel_keyboard(),
                    )
                    return STATE_KIRIM_PILIH_AKUN
                context.user_data.pop("kirim_waiting_tag", None)
            else:
                # Fallback: coba parse sebagai angka atau tag:xxx
                if pesan.lower().startswith("tag:"):
                    tag = pesan.split(":", 1)[1].strip().lower()
                    if not tag:
                        await update.message.reply_text(
                            "❌ Tag tidak boleh kosong. Gunakan format tag:nama:",
                            reply_markup=get_cancel_keyboard(),
                        )
                        return STATE_KIRIM_PILIH_AKUN
                    akun_terpilih = [
                        a for a in akun_list if tag in [t.lower() for t in (a.get("tags", []) or [])]
                    ]
                    if not akun_terpilih:
                        await update.message.reply_text(
                            "⚠️ Tidak ada akun dengan tag tersebut. Coba lagi:",
                            reply_markup=get_cancel_keyboard(),
                        )
                        return STATE_KIRIM_PILIH_AKUN
                else:
                    jumlah = int(pesan)
                    if jumlah < 1 or jumlah > len(akun_list):
                        await update.message.reply_text(
                            f"❌ Jumlah harus antara 1-{len(akun_list)}. Coba lagi:",
                            reply_markup=get_cancel_keyboard()
                        )
                        return STATE_KIRIM_PILIH_AKUN
                    akun_terpilih = akun_list[:jumlah]
        
        context.user_data["kirim_akun_terpilih"] = akun_terpilih
        
        await update.message.reply_text(
            f"✅ Dipilih: *{len(akun_terpilih)}* akun\n\n"
            f"💬 Sekarang masukkan *pesan* yang ingin dikirim:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_KIRIM_PESAN
        
    except ValueError:
        await update.message.reply_text(
            "❌ Input harus berupa angka. Coba lagi:",
            reply_markup=get_cancel_keyboard()
        )
        return STATE_KIRIM_PILIH_AKUN

async def bot_kirim_pesan(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan_text = (update.message.text or "").strip()
    
    # Check untuk cancel
    if pesan_text.startswith("🔙"):
        return await handle_cancel(update, context)
    
    pesan = pesan_text
    if not pesan:
        await update.message.reply_text(
            "❌ Pesan tidak boleh kosong. Masukkan pesan lagi:",
            reply_markup=get_cancel_keyboard()
        )
        return STATE_KIRIM_PESAN

    target = context.user_data.get("kirim_target")
    akun_terpilih = context.user_data.get("kirim_akun_terpilih")
    
    if not target or not akun_terpilih:
        await bot_send_main_menu(
            update,
            context,
            "⚠️ Data tidak lengkap. Silakan ulangi dari menu Kirim Pesan.",
        )
        return STATE_MAIN_MENU

    context.user_data["kirim_pesan"] = pesan
    settings = get_user_settings(context)
    estimasi = estimate_time(len(akun_terpilih), settings["kirim_delay"])

    await update.message.reply_text(
        f"📦 *RINGKASAN PENGIRIMAN*\n\n"
        f"🎯 Target: `@{target}`\n"
        f"📊 Jumlah: {len(akun_terpilih)} akun\n"
        f"⏱️ Estimasi: {estimasi}\n"
        f"💬 Pesan: {pesan}\n\n"
        f"Konfirmasi untuk melanjutkan.",
        reply_markup=get_confirm_keyboard(),
        parse_mode="Markdown"
    )
    return STATE_KIRIM_CONFIRM

async def bot_kirim_confirm(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    target = context.user_data.get("kirim_target")
    akun_terpilih = context.user_data.get("kirim_akun_terpilih")
    pesan_text = context.user_data.get("kirim_pesan")

    if not target or not akun_terpilih or not pesan_text:
        await bot_send_main_menu(update, context, "⚠️ Data tidak lengkap. Silakan ulangi.")
        return STATE_MAIN_MENU

    settings = get_user_settings(context)
    chat_id = update.effective_chat.id
    total = len(akun_terpilih)

    cancel_event = asyncio.Event()
    pause_event = asyncio.Event()
    context.user_data["repeat_cancel_event"] = cancel_event
    context.user_data["repeat_done"] = False

    run_id = _uuid.uuid4().hex[:10]
    register_runtime_control("kirim", run_id, cancel_event, pause_event, update.effective_user.id)
    start_ts = _now_ts()

    initial_text = render_live_dashboard(
        title="KIRIM PESAN BERJALAN", icon=ICON["sent"],
        target_summary=f"`@{target}`", accounts_count=total,
        done=0, total=total, sukses=0, gagal=0, skip=0,
        start_ts=start_ts, current_line="Mempersiapkan batch pertama...",
    )
    live = await LiveMessage.create(
        context.bot, chat_id, initial_text=initial_text,
        reply_markup=build_runtime_inline_keyboard(run_id, kind="kirim"),
    )

    async def _stats_hook(stats):
        paused = pause_event.is_set()
        frame = SPINNER_FRAMES[(int(_now_ts() * 2) % len(SPINNER_FRAMES))]
        current = "⏸ PAUSED — tekan Resume untuk lanjut" if paused else \
                  f"{frame} Memproses batch akun..."
        txt = render_live_dashboard(
            title="KIRIM PESAN BERJALAN" + (" ⏸" if paused else ""),
            icon=ICON["sent"],
            target_summary=f"`@{target}`",
            accounts_count=total,
            done=stats["done"], total=total,
            sukses=stats["sukses"], gagal=stats["gagal"], skip=stats.get("skip", 0),
            start_ts=start_ts, current_line=current,
        )
        await live.update(txt, reply_markup=build_runtime_inline_keyboard(run_id, kind="kirim", paused=paused))

    async def run_kirim_task():
        try:
            hasil = await proses_kirim_akun_terpilih_async(
                target, pesan_text, akun_terpilih,
                delay_detik=settings["kirim_delay"],
                parallel_batch=settings["parallel_batch"],
                cancel_event=cancel_event,
                stats_hook=_stats_hook,
                pause_event=pause_event,
            )
            context.user_data["last_target"] = target
            set_last_action(
                context, "kirim_pesan",
                {"target": target, "pesan": pesan_text, "akun_list": akun_terpilih},
            )
            context.user_data["repeat_done"] = True
            final_txt = (
                f"{ICON['done']} *KIRIM PESAN SELESAI*\n\n"
                f"{ICON['timer']} Durasi: *{fmt_duration(_now_ts() - start_ts)}*\n\n"
                + hasil[:3600]
            )
            await live.finalize(final_txt)
            await send_toast(
                context.bot, chat_id,
                f"{ICON['success']} Kirim pesan selesai ({fmt_duration(_now_ts() - start_ts)})",
                duration=8,
            )
        except Exception as e:
            context.user_data["repeat_done"] = True
            await live.finalize(f"{ICON['error']} *Error:* {e}")
        finally:
            unregister_runtime_control("kirim", run_id)

    task = asyncio.create_task(run_kirim_task())
    context.user_data["repeat_task"] = task
    return STATE_REPEAT_RUNNING

async def bot_kirim_cepat_target(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
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
        return STATE_KIRIM_CEPAT_TARGET

    if target.startswith("@"):
        target = target[1:]

    context.user_data["quick_target"] = target
    await update.message.reply_text(
        "💬 Masukkan pesan yang ingin dikirim:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_KIRIM_CEPAT_PESAN

async def bot_kirim_cepat_pesan(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    if not pesan:
        await update.message.reply_text(
            "❌ Pesan tidak boleh kosong. Masukkan pesan lagi:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_KIRIM_CEPAT_PESAN

    context.user_data["quick_pesan"] = pesan
    await update.message.reply_text(
        "📊 Pilih akun untuk kirim cepat:",
        reply_markup=get_akun_scope_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_KIRIM_CEPAT_SCOPE

async def bot_kirim_cepat_scope(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    akun_list = await db_find(collection, {})
    if not akun_list:
        await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan.")
        return STATE_MAIN_MENU

    if pesan == "📋 Semua Akun":
        akun_terpilih = akun_list
    elif pesan == "🔢 Jumlah Tertentu":
        await update.message.reply_text(
            f"🔢 Masukkan jumlah akun (1-{len(akun_list)}):",
            reply_markup=get_cancel_keyboard(),
        )
        context.user_data["cepat_waiting_jumlah"] = True
        return STATE_KIRIM_CEPAT_SCOPE
    elif pesan == "🏷️ Berdasarkan Tag":
        await update.message.reply_text(
            "🏷️ Masukkan nama tag (contoh: marketing):",
            reply_markup=get_cancel_keyboard(),
        )
        context.user_data["cepat_waiting_tag"] = True
        return STATE_KIRIM_CEPAT_SCOPE
    else:
        if context.user_data.get("cepat_waiting_jumlah"):
            try:
                jumlah = int(pesan)
            except ValueError:
                await update.message.reply_text(
                    "❌ Input harus berupa angka. Coba lagi:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_CEPAT_SCOPE
            if jumlah < 1 or jumlah > len(akun_list):
                await update.message.reply_text(
                    f"❌ Jumlah harus antara 1-{len(akun_list)}. Coba lagi:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_CEPAT_SCOPE
            akun_terpilih = akun_list[:jumlah]
            context.user_data.pop("cepat_waiting_jumlah", None)
        elif context.user_data.get("cepat_waiting_tag"):
            tag = pesan.strip().lower()
            if not tag:
                await update.message.reply_text(
                    "❌ Tag tidak boleh kosong. Masukkan nama tag:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_CEPAT_SCOPE
            akun_terpilih = [
                a for a in akun_list if tag in [t.lower() for t in (a.get("tags", []) or [])]
            ]
            if not akun_terpilih:
                await update.message.reply_text(
                    "⚠️ Tidak ada akun dengan tag tersebut. Masukkan lagi:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_CEPAT_SCOPE
            context.user_data.pop("cepat_waiting_tag", None)
        elif pesan.lower().startswith("tag:"):
            tag = pesan.split(":", 1)[1].strip().lower()
            if not tag:
                await update.message.reply_text(
                    "❌ Tag tidak boleh kosong. Gunakan format tag:nama:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_CEPAT_SCOPE
            akun_terpilih = [
                a for a in akun_list if tag in [t.lower() for t in (a.get("tags", []) or [])]
            ]
            if not akun_terpilih:
                await update.message.reply_text(
                    "⚠️ Tidak ada akun dengan tag tersebut. Masukkan lagi:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_CEPAT_SCOPE
        else:
            try:
                jumlah = int(pesan)
            except ValueError:
                await update.message.reply_text(
                    "❌ Input tidak valid. Pilih opsi dari tombol:",
                    reply_markup=get_akun_scope_keyboard(),
                )
                return STATE_KIRIM_CEPAT_SCOPE
            if jumlah < 1 or jumlah > len(akun_list):
                await update.message.reply_text(
                    f"❌ Jumlah harus antara 1-{len(akun_list)}. Coba lagi:",
                    reply_markup=get_cancel_keyboard(),
                )
                return STATE_KIRIM_CEPAT_SCOPE
            akun_terpilih = akun_list[:jumlah]

    context.user_data["quick_akun_list"] = akun_terpilih
    settings = get_user_settings(context)
    target = context.user_data.get("quick_target")
    pesan_text = context.user_data.get("quick_pesan")
    estimasi = estimate_time(len(akun_terpilih), settings["kirim_delay"])

    await update.message.reply_text(
        f"📦 *RINGKASAN KIRIM CEPAT*\n\n"
        f"🎯 Target: `@{target}`\n"
        f"📊 Jumlah: {len(akun_terpilih)} akun\n"
        f"⏱️ Estimasi: {estimasi}\n"
        f"💬 Pesan: {pesan_text}\n\n"
        f"Konfirmasi untuk melanjutkan.",
        reply_markup=get_confirm_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_KIRIM_CEPAT_CONFIRM

async def bot_kirim_cepat_confirm(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    target = context.user_data.get("quick_target")
    pesan_text = context.user_data.get("quick_pesan")
    akun_terpilih = context.user_data.get("quick_akun_list") or []
    if not target or not pesan_text or not akun_terpilih:
        await bot_send_main_menu(update, context, "⚠️ Data tidak lengkap. Silakan ulangi.")
        return STATE_MAIN_MENU

    settings = get_user_settings(context)
    progress_step = settings["progress_step"]

    chat_id = update.effective_chat.id
    progress_message = await context.bot.send_message(
        chat_id=chat_id,
        text=f"📈 Progres: 0/{len(akun_terpilih)} akun diproses",
    )

    async def progress_hook(idx, total, success):
        if progress_step <= 0:
            return
        if idx % progress_step != 0 and idx != total:
            return
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_message.message_id,
                text=f"📈 Progres: {idx}/{total} akun diproses",
            )
        except Exception:
            pass

    cancel_event = asyncio.Event()
    context.user_data["repeat_cancel_event"] = cancel_event
    context.user_data["repeat_done"] = False

    await update.message.reply_text(
        f"⏳ *SEDANG MENGIRIM PESAN...*\n\n"
        f"🎯 Target: `@{target}`\n"
        f"📊 Jumlah: {len(akun_terpilih)} akun\n\n"
        f"Tekan tombol di bawah untuk membatalkan.",
        reply_markup=get_cancel_repeat_keyboard(),
        parse_mode="Markdown",
    )

    async def run_kirim_cepat_task():
        try:
            hasil = await proses_kirim_akun_terpilih_async(
                target,
                pesan_text,
                akun_terpilih,
                delay_detik=settings["kirim_delay"],
                progress_hook=progress_hook,
                parallel_batch=settings["parallel_batch"],
                cancel_event=cancel_event,
            )
            context.user_data["last_target"] = target
            set_last_action(
                context,
                "kirim_pesan",
                {"target": target, "pesan": pesan_text, "akun_list": akun_terpilih},
            )
            context.user_data["repeat_done"] = True
            if len(hasil) > 3900:
                hasil = hasil[:3900] + "\n\n(⚠️ Dipotong karena terlalu panjang)"
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=hasil + build_next_steps(["Kirim cepat lagi", "Kembali ke menu"]),
                    reply_markup=get_main_menu_keyboard(),
                    parse_mode="Markdown",
                )
            except Exception:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=hasil,
                    reply_markup=get_main_menu_keyboard(),
                )
        except Exception as e:
            context.user_data["repeat_done"] = True
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Terjadi error saat mengirim pesan:\n{e}",
                    reply_markup=get_main_menu_keyboard(),
                )
            except Exception:
                pass

    task = asyncio.create_task(run_kirim_cepat_task())
    context.user_data["repeat_task"] = task
    return STATE_REPEAT_RUNNING

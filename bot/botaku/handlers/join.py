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
def parse_join_target(raw):
    """
    Parse satu input (username / URL publik / invite link private) → dict.
    Return: {"type": "public"|"private"|"invalid",
             "value": username atau invite_hash atau teks asli,
             "original": str,
             "display": str (untuk ditampilkan),
             "error": str (hanya jika invalid)}
    Atau None kalau input kosong.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    # 1. Private invite link (t.me/+xxx atau t.me/joinchat/xxx)
    m = _INVITE_RE.match(s)
    if m:
        invite_hash = m.group(1)
        return {
            "type": "private",
            "value": invite_hash,
            "original": s,
            "display": f"🔒 invite:{invite_hash[:10]}…",
        }

    # 2. Public URL t.me/username
    m = _PUBLIC_URL_RE.match(s)
    if m:
        uname = m.group(1)
        if uname.lower() in _RESERVED_PATHS:
            return {
                "type": "invalid", "value": s, "original": s,
                "display": s, "error": "URL tidak valid (reserved path)",
            }
        return {
            "type": "public", "value": uname, "original": s,
            "display": f"@{uname}",
        }

    # 3. @username atau username biasa
    m = _USERNAME_RE.match(s)
    if m:
        uname = m.group(1)
        return {
            "type": "public", "value": uname, "original": s,
            "display": f"@{uname}",
        }

    return {
        "type": "invalid", "value": s, "original": s,
        "display": s, "error": "Format tidak dikenali",
    }

def parse_join_targets_text(text, limit=MAX_BULK_JOIN_TARGETS):
    """
    Parse teks multi-baris / dipisah koma → (valid_list, invalid_list, truncated_bool).
    Duplikat (case-insensitive) dibuang otomatis.
    """
    if not text:
        return [], [], False
    # Pisahkan via newline atau koma
    raw_lines = []
    for chunk in str(text).replace(",", "\n").splitlines():
        c = chunk.strip()
        if c:
            raw_lines.append(c)

    seen = set()
    valid, invalid = [], []
    for line in raw_lines:
        p = parse_join_target(line)
        if p is None:
            continue
        if p["type"] == "invalid":
            invalid.append(p)
            continue
        key = f"{p['type']}:{p['value'].lower()}"
        if key in seen:
            continue
        seen.add(key)
        valid.append(p)

    truncated = False
    if len(valid) > limit:
        valid = valid[:limit]
        truncated = True
    return valid, invalid, truncated

def _normalize_target(t):
    """
    Terima legacy string atau dict parsed → selalu kembalikan dict parsed.
    """
    if isinstance(t, dict) and "type" in t:
        return t
    return parse_join_target(t) or {
        "type": "invalid", "value": str(t), "original": str(t),
        "display": str(t), "error": "Target kosong",
    }

async def validasi_join_target(api_id, api_hash, string_sesi, parsed_target):
    """
    Validasi apakah grup/channel (public) atau invite link (private) bisa diakses.
    Return: (success: bool, error_message: str|None, info: dict|None)
    info untuk private berisi title invite jika tersedia.
    """
    parsed = _normalize_target(parsed_target)
    if parsed["type"] == "invalid":
        return False, parsed.get("error") or "Target tidak valid", None

    client = None
    try:
        client = get_telegram_client(
            string_sesi, api_id, api_hash,
            connection_retries=1, retry_delay=1,
            timeout=TELEGRAM_CONNECT_TIMEOUT,
        )
        ok, connect_err = await safe_connect_and_check(client, timeout=TELEGRAM_CONNECT_TIMEOUT)
        if not ok:
            return False, f"Gagal connect untuk validasi: {connect_err}", None

        if parsed["type"] == "private":
            # Cek invite tanpa join
            info_obj = await safe_telegram_operation(
                client(CheckChatInviteRequest(parsed["value"])),
                timeout=TELEGRAM_OP_TIMEOUT,
            )
            title = getattr(info_obj, "title", None) or getattr(
                getattr(info_obj, "chat", None), "title", None
            )
            already = bool(getattr(info_obj, "chat", None)) and not getattr(info_obj, "request_needed", False) \
                and not hasattr(info_obj, "participants_count")
            return True, None, {"title": title or "(private chat)", "already_member": already}
        else:
            entity = await safe_telegram_operation(
                client.get_entity(parsed["value"]),
                timeout=TELEGRAM_OP_TIMEOUT,
            )
            title = getattr(entity, "title", None) or getattr(entity, "username", None) or parsed["display"]
            return True, None, {"title": title}
    except asyncio.TimeoutError:
        return False, "Timeout saat menghubungi Telegram (akun mungkin bermasalah)", None
    except InviteHashInvalidError:
        return False, "Invite link tidak valid / sudah dicabut", None
    except InviteHashExpiredError:
        return False, "Invite link sudah kadaluarsa", None
    except (ConnectionError, OSError) as e:
        return False, f"Connection error: {e}", None
    except Exception as e:
        return False, f"Target tidak ditemukan / tidak bisa diakses: {e}", None
    finally:
        await safe_disconnect(client)

async def validasi_grup_channel(api_id, api_hash, string_sesi, grup_username):
    """Validasi legacy: terima string username → panggil validasi_join_target."""
    parsed = _normalize_target(grup_username)
    ok, err, _ = await validasi_join_target(api_id, api_hash, string_sesi, parsed)
    return ok, err

async def join_grup_async(nama_akun, data, target):
    """
    Join grup/channel dari satu akun - dukung PUBLIC (username) & PRIVATE (invite link).
    `target` bisa string legacy atau dict parsed (lihat parse_join_target).
    Return: (success: bool, msg: str|None)
    """
    parsed = _normalize_target(target)
    if parsed["type"] == "invalid":
        return False, f"INVALID_TARGET: {parsed.get('error', 'format tidak dikenali')}"

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
            if "TIMEOUT" in str(connect_err).upper():
                update_account_status(nomor, "timeout", connect_err)
            elif "SESSION" in str(connect_err).upper() or "expired" in str(connect_err).lower():
                update_account_status(nomor, "expired", connect_err)
            else:
                update_account_status(nomor, "timeout", connect_err)
            return False, f"CONNECT_FAIL: {connect_err}"
        
        # === Eksekusi join berdasarkan tipe target ===
        try:
            if parsed["type"] == "private":
                await safe_telegram_operation(
                    client(ImportChatInviteRequest(parsed["value"])),
                    timeout=TELEGRAM_OP_TIMEOUT,
                )
            else:
                await safe_telegram_operation(
                    client(JoinChannelRequest(parsed["value"])),
                    timeout=TELEGRAM_OP_TIMEOUT,
                )
        except UserAlreadyParticipantError:
            # Sudah member → anggap sukses (skip)
            prev_status = data.get('status', 'aktif')
            if prev_status != 'aktif':
                update_account_status(nomor, "aktif", "Sudah member (join grup)")
            return True, "ALREADY_MEMBER"
        except InviteRequestSentError:
            # Bukan gagal — permintaan terkirim, tinggal tunggu approval admin
            return True, "REQUEST_SENT"
        
        # Reset status jika berhasil
        prev_status = data.get('status', 'aktif')
        if prev_status != 'aktif':
            update_account_status(nomor, "aktif", "Berhasil join grup")
        
        return True, None
        
    except asyncio.TimeoutError:
        update_account_status(nomor, "timeout", "Timeout saat join grup")
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
    except (ChannelPrivateError, ChatAdminRequiredError) as e:
        return False, f"ACCESS_DENIED: {type(e).__name__}"
    except InviteHashInvalidError:
        return False, "INVITE_INVALID: Link undangan tidak valid"
    except InviteHashExpiredError:
        return False, "INVITE_EXPIRED: Link undangan kadaluarsa"
    except ChannelsTooMuchError:
        return False, "CHANNELS_TOO_MUCH: Akun sudah join terlalu banyak channel/grup"
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

async def proses_join_semua_akun_async(grup_username, akun_list=None, delay_detik=3, progress_hook=None, parallel_batch=3, cancel_event=None, stats_hook=None, pause_event=None):
    """
    Memproses join grup/channel - PARALLEL BATCH MODE.
    `grup_username` bisa berupa:
      - string (legacy) → 1 target
      - list of parsed_target dict → BULK JOIN (multi target)
    """
    try:
        # Normalisasi input → selalu list of parsed_target dict
        if isinstance(grup_username, list):
            targets = [_normalize_target(t) for t in grup_username]
        else:
            targets = [_normalize_target(grup_username)]
        # Filter target invalid (tetap laporkan)
        invalid_targets = [t for t in targets if t["type"] == "invalid"]
        targets = [t for t in targets if t["type"] != "invalid"]
        if not targets:
            return "⚠️ Tidak ada target valid untuk diproses."

        if akun_list is None:
            akun_list = await db_find(collection, {})
        if not akun_list:
            return "⚠️ Tidak ada akun yang tersimpan di database."

        mode_label = f"PARALEL ({parallel_batch} akun/batch)" if parallel_batch > 1 else "SEKUENSIAL"
        is_bulk = len(targets) > 1

        hasil = []
        hasil.append(f"📊 *Joining {len(akun_list)} akun ke {len(targets)} grup/channel...*\n"
                     if is_bulk else f"📊 *Joining {len(akun_list)} akun ke grup/channel...*\n")
        if is_bulk:
            hasil.append(f"👥 Total target: *{len(targets)}*")
            preview = ", ".join([f"`{t['display']}`" for t in targets[:5]])
            if len(targets) > 5:
                preview += f", … (+{len(targets) - 5})"
            hasil.append(f"🎯 Targets: {preview}")
        else:
            hasil.append(f"👥 Target: `{targets[0]['display']}`")
        if invalid_targets:
            hasil.append(f"⚠️ {len(invalid_targets)} target di-skip (format tidak valid)")
        hasil.append(f"⚡ Mode: {mode_label}\n")
        hasil.append("⏳ *Mohon tunggu, sedang diproses...*\n")

        # Pisahkan akun aktif dan yang di-skip
        akun_aktif = []
        akun_skip_info = []
        for idx, akun in enumerate(akun_list, 1):
            akun_status = akun.get('status', 'aktif')
            if akun_status in SKIP_STATUSES:
                alasan_skip = akun.get('status_alasan', akun_status)
                akun_skip_info.append((idx, akun, alasan_skip))
            else:
                akun_aktif.append((idx, akun))

        total_tasks = len(targets) * len(akun_aktif)
        total_tasks_incl_skip = len(targets) * len(akun_list)

        # Statistik global
        total_sukses = 0
        total_gagal = 0
        total_dilewati = len(akun_skip_info) * len(targets)
        detail_errors = {}
        cancelled = False
        processed_global = 0
        per_target_stats = []

        for t_idx, parsed_target in enumerate(targets, 1):
            if cancel_event and cancel_event.is_set():
                cancelled = True
                break

            target_display = parsed_target["display"]
            hasil.append(f"\n━━ 🎯 Target {t_idx}/{len(targets)}: `{target_display}` ━━")

            # Laporkan akun skip per target (sekali saja untuk target pertama, agar tidak redundant kalau bulk)
            if t_idx == 1:
                for idx, akun, alasan_skip in akun_skip_info:
                    nama_akun = akun.get('name', 'Unknown')
                    nomor = akun.get('nomor_telepon', 'N/A')
                    hasil.append(
                        f"{idx}. ⏭️ {nomor} ({nama_akun}) — SKIP akun: "
                        f"{akun.get('status', 'aktif')} ({shorten_text(alasan_skip, 60)})"
                    )
                    log_action(
                        "gabung_grup",
                        {"nomor_telepon": nomor, "nama": nama_akun,
                         "target": parsed_target["original"], "status": "dilewati",
                         "alasan": f"status akun: {akun.get('status', 'aktif')}"},
                    )

            target_sukses = 0
            target_gagal = 0
            target_already = 0

            # Proses akun aktif dalam batch paralel (per target)
            for batch_start in range(0, len(akun_aktif), parallel_batch):
                if cancel_event and cancel_event.is_set():
                    cancelled = True
                    break

                batch = akun_aktif[batch_start:batch_start + parallel_batch]

                async def _join_satu(idx_akun_tuple, _target=parsed_target):
                    idx, akun = idx_akun_tuple
                    nama_akun = akun.get('name', 'Unknown')
                    return idx, akun, await join_grup_async(nama_akun, akun, _target)

                tasks = [_join_satu(item) for item in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in batch_results:
                    processed_global += 1
                    if isinstance(result, Exception):
                        idx, akun = batch[batch_results.index(result)]
                        nama_akun = akun.get('name', 'Unknown')
                        nomor = akun.get('nomor_telepon', 'N/A')
                        target_gagal += 1
                        total_gagal += 1
                        err_str = str(result)
                        err_category = type(result).__name__
                        detail_errors[err_category] = detail_errors.get(err_category, 0) + 1
                        hasil.append(f"{idx}. ❌ {nomor} ({nama_akun}) — {shorten_text(err_str, 120)}")
                        log_action("gabung_grup", {"nomor_telepon": nomor, "nama": nama_akun,
                                                    "target": parsed_target["original"], "status": "gagal",
                                                    "error": err_str})
                    else:
                        idx, akun, (success, err) = result
                        nama_akun = akun.get('name', 'Unknown')
                        nomor = akun.get('nomor_telepon', 'N/A')
                        if success:
                            target_sukses += 1
                            total_sukses += 1
                            if err == "ALREADY_MEMBER":
                                target_already += 1
                                hasil.append(f"{idx}. ✅ {nomor} ({nama_akun}) — sudah member")
                            elif err == "REQUEST_SENT":
                                hasil.append(f"{idx}. ✅ {nomor} ({nama_akun}) — request sent (menunggu approval)")
                            else:
                                hasil.append(f"{idx}. ✅ {nomor} ({nama_akun})")
                        else:
                            target_gagal += 1
                            total_gagal += 1
                            err_category = (err or "unknown").split(":")[0].strip()
                            detail_errors[err_category] = detail_errors.get(err_category, 0) + 1
                            hasil.append(f"{idx}. ❌ {nomor} ({nama_akun}) — {shorten_text(err, 120)}")
                        log_action("gabung_grup", {"nomor_telepon": nomor, "nama": nama_akun,
                                                    "target": parsed_target["original"],
                                                    "status": "sukses" if success else "gagal",
                                                    "error": err if (not success or err in ("ALREADY_MEMBER", "REQUEST_SENT")) else None})

                if progress_hook:
                    await progress_hook(processed_global + (t_idx - 1) * len(akun_skip_info), total_tasks_incl_skip, True)

                # Stats hook realtime untuk LiveMessage dashboard
                if stats_hook:
                    try:
                        await stats_hook({
                            "done": processed_global,
                            "total": total_tasks,
                            "sukses": total_sukses,
                            "gagal": total_gagal,
                            "skip": total_dilewati,
                            "current_target": parsed_target["display"],
                            "current_target_idx": t_idx,
                            "total_targets": len(targets),
                            "target_sukses": target_sukses,
                            "target_gagal": target_gagal,
                        })
                    except Exception:
                        pass

                # Pause support: block batch loop selama pause_event di-set
                if pause_event is not None:
                    while pause_event.is_set():
                        if cancel_event and cancel_event.is_set():
                            break
                        await asyncio.sleep(0.5)

                if batch_start + parallel_batch < len(akun_aktif):
                    await asyncio.sleep(delay_detik)

            per_target_stats.append({
                "display": target_display,
                "sukses": target_sukses,
                "gagal": target_gagal,
                "already": target_already,
            })

            # Delay antar target (pakai delay_detik juga, agar tidak flood)
            if not cancelled and t_idx < len(targets):
                await asyncio.sleep(delay_detik)

        hasil.append(f"\n{'='*40}")
        if cancelled:
            hasil.append("⚠️ *Join DIBATALKAN oleh user!*")
            hasil.append(f"• Target selesai: {len(per_target_stats)}/{len(targets)}")
        else:
            hasil.append("✅ *Proses Selesai!*")

        if is_bulk:
            hasil.append("\n📋 *Ringkasan per Target:*")
            for st in per_target_stats:
                extra = f" (sudah-member: {st['already']})" if st['already'] else ""
                hasil.append(f"  • `{st['display']}` — ✅ {st['sukses']} / ❌ {st['gagal']}{extra}")

        hasil.append("\n📊 *Total:*")
        hasil.append(f"• Berhasil: {total_sukses}")
        hasil.append(f"• Gagal: {total_gagal}")
        if total_dilewati > 0:
            hasil.append(f"• Dilewati (akun bermasalah × target): {total_dilewati}")
        if invalid_targets:
            hasil.append(f"• Target invalid (skip): {len(invalid_targets)}")
            for inv in invalid_targets[:5]:
                hasil.append(f"    - `{shorten_text(inv['original'], 40)}` — {inv.get('error', '')}")
        hasil.append(f"• Mode: {mode_label}")

        if detail_errors:
            hasil.append("\n📋 *Rincian Error:*")
            for err_type, count in detail_errors.items():
                hasil.append(f"  • {err_type}: {count} akun")

        hasil.append(f"{'='*40}")

        return join_lines_truncate(hasil)
        
    except Exception as e:
        return f"❌ Error saat memproses: {e}"

async def q_bot_gabung_scope(update, context): return await bot_inline_opt_bridge(update, context, bot_gabung_scope)

async def q_bot_gabung_confirm(update, context): return await bot_inline_opt_bridge(update, context, bot_gabung_confirm)

def join_lines_truncate(lines: list[str], max_chars: int = 3800):
    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text
    head_count = 25
    tail_count = 20
    head = lines[:head_count]
    tail = lines[-tail_count:] if len(lines) > head_count else []
    merged = head + ["", "(⚠️ Detail dipotong)", ""] + tail
    text2 = "\n".join(merged)
    if len(text2) <= max_chars:
        return text2
    return text2[:max_chars] + "\n\n(⚠️ Dipotong)"

async def bot_gabung_grup(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """
    Handler input target join grup/channel — dukung:
    - Teks multi-baris (1 target per baris, bisa dipisah koma juga)
    - Upload file .txt (via handler bot_gabung_grup_document)
    Target bisa berupa:
    - @username / username / https://t.me/username (publik)
    - https://t.me/+hash / https://t.me/joinchat/hash (private/invite)
    """
    pesan = (update.message.text or "").strip()

    # Check untuk cancel
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    # Kalau user tidak ketik apapun, coba pakai last_group (backward compat)
    last_group = context.user_data.get("last_group")
    if not pesan and last_group:
        pesan = last_group

    if not pesan:
        await update.message.reply_text(
            "❌ Target tidak boleh kosong.\n"
            "Ketik 1 atau lebih target (satu per baris), atau upload file .txt:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_GABUNG_GROUP

    # Parse multi-line / multi-target
    valid_targets, invalid_targets, truncated = parse_join_targets_text(pesan)
    return await _bot_gabung_after_parse(
        update, context, valid_targets, invalid_targets, truncated, source_label="teks"
    )

async def bot_gabung_grup_document(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """Handler upload file .txt berisi daftar target join grup/channel."""
    if update.message is None or update.message.document is None:
        await update.message.reply_text(
            "❌ Tidak ada file terdeteksi. Coba kirim ulang sebagai dokumen .txt:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_GABUNG_GROUP

    doc = update.message.document
    fname = (doc.file_name or "").lower()
    if not fname.endswith(".txt"):
        await update.message.reply_text(
            "❌ File harus berekstensi .txt. Kirim ulang:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_GABUNG_GROUP

    try:
        file = await doc.get_file()
        buf = await file.download_as_bytearray()
        try:
            text = bytes(buf).decode("utf-8")
        except UnicodeDecodeError:
            text = bytes(buf).decode("utf-8", errors="ignore")
    except Exception as e:
        await update.message.reply_text(
            f"❌ Gagal membaca file: {e}",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_GABUNG_GROUP

    valid_targets, invalid_targets, truncated = parse_join_targets_text(text)
    return await _bot_gabung_after_parse(
        update, context, valid_targets, invalid_targets, truncated, source_label=f"file `{doc.file_name}`"
    )

async def _bot_gabung_after_parse(
    update, context, valid_targets, invalid_targets, truncated, source_label
):
    """Shared flow setelah parsing target — validasi ringan & lanjut ke pemilihan akun."""
    if not valid_targets:
        # Tidak ada target valid
        msg_lines = [
            f"❌ *Tidak ada target valid* dari {source_label}.\n",
        ]
        if invalid_targets:
            msg_lines.append("⚠️ Contoh yang tidak dikenali:")
            for inv in invalid_targets[:5]:
                msg_lines.append(f"  • `{shorten_text(inv['original'], 50)}` — {inv.get('error', '')}")
        msg_lines.append("\nCoba lagi dengan format yang benar, atau tekan 🔙.")
        await update.message.reply_text(
            "\n".join(msg_lines),
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_GABUNG_GROUP

    try:
        akun_list = await db_find(collection, {})
    except Exception as e:
        await update.message.reply_text(f"❌ Error saat membaca database: {e}")
        return STATE_MAIN_MENU

    if not akun_list:
        await bot_send_main_menu(update, context, "⚠️ Tidak ada akun yang tersimpan.")
        return STATE_MAIN_MENU

    # Validasi ringan: kalau hanya 1 target, pre-validate via API supaya user tahu cepat
    # Kalau bulk (>1), skip pre-validate (lambat) — biarkan runtime yang report.
    lines = [f"✅ *{len(valid_targets)} target valid* dari {source_label}"]
    if truncated:
        lines.append(
            f"⚠️ Dibatasi hingga {MAX_BULK_JOIN_TARGETS} target pertama "
            f"(sisanya dipotong)."
        )
    if invalid_targets:
        lines.append(f"⚠️ {len(invalid_targets)} target di-skip (format tidak dikenali):")
        for inv in invalid_targets[:3]:
            lines.append(f"  • `{shorten_text(inv['original'], 50)}` — {inv.get('error', '')}")
        if len(invalid_targets) > 3:
            lines.append(f"  • … (+{len(invalid_targets) - 3} lainnya)")
    lines.append("")
    lines.append("🎯 *Preview target:*")
    for i, t in enumerate(valid_targets[:10], 1):
        tipe = "🔒 private" if t["type"] == "private" else "🌐 public"
        lines.append(f"  {i}. `{t['display']}` ({tipe})")
    if len(valid_targets) > 10:
        lines.append(f"  … (+{len(valid_targets) - 10} lainnya)")

    if len(valid_targets) == 1:
        # Single target: coba pre-validate via akun aktif pertama (dengan spinner animasi)
        first_akun = next((a for a in akun_list if a.get('status', 'aktif') not in SKIP_STATUSES), None)
        if first_akun:
            spinner_msg = await update.message.reply_text(
                f"{SPINNER_FRAMES[0]} Memvalidasi target...",
            )
            # Background spinner task
            stop_spin = asyncio.Event()

            async def _animate_spinner():
                idx = 0
                while not stop_spin.is_set():
                    idx = (idx + 1) % len(SPINNER_FRAMES)
                    try:
                        await context.bot.edit_message_text(
                            chat_id=spinner_msg.chat_id,
                            message_id=spinner_msg.message_id,
                            text=f"{SPINNER_FRAMES[idx]} Memvalidasi target...",
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(1.3)

            spin_task = asyncio.create_task(_animate_spinner())
            try:
                valid, err, info = await validasi_join_target(
                    first_akun['api_id'], first_akun['api_hash'],
                    first_akun['string_sesi'], valid_targets[0],
                )
            finally:
                stop_spin.set()
                spin_task.cancel()
                try:
                    await context.bot.delete_message(
                        chat_id=spinner_msg.chat_id,
                        message_id=spinner_msg.message_id,
                    )
                except Exception:
                    pass

            if not valid:
                await bot_send_main_menu(
                    update, context,
                    f"{ICON['error']} *VALIDASI GAGAL*\n\n{err}\n\n"
                    f"💡 Periksa kembali format/target, lalu ulangi.",
                )
                return STATE_MAIN_MENU
            if info and info.get("title"):
                lines.append(f"\n{ICON['info']} Info: *{info['title']}*")

    # Simpan list target parsed
    context.user_data["gabung_targets"] = valid_targets
    # Backward-compat dengan scheduler/repeat — simpan juga "first_target" sebagai string
    context.user_data["gabung_group"] = valid_targets[0]["original"]

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    await update.message.reply_text(
        "📊 Pilih akun untuk join:",
        reply_markup=get_akun_scope_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_GABUNG_SCOPE

async def bot_gabung_scope(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    def _fmt_targets_summary(targets):
        """Format list target parsed untuk ringkasan (Markdown-safe)."""
        if not targets:
            return "(tidak ada)"
        if len(targets) == 1:
            t = targets[0]
            tipe = "🔒 private" if t["type"] == "private" else "🌐 public"
            return f"`{t['display']}` ({tipe})"
        # Bulk: tampilkan count + preview
        preview = ", ".join([f"`{t['display']}`" for t in targets[:3]])
        if len(targets) > 3:
            preview += f", … (+{len(targets) - 3})"
        return f"*{len(targets)} target* — {preview}"

    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    targets = context.user_data.get("gabung_targets") or []

    if pesan == "📋 Semua Akun":
        akun_list = await db_find(collection, {})
        context.user_data["gabung_akun_list"] = akun_list
        settings = get_user_settings(context)
        estimasi = estimate_time(len(akun_list) * max(1, len(targets)), settings["join_delay"])
        await update.message.reply_text(
            f"📦 *RINGKASAN JOIN*\n\n"
            f"👥 Target: {_fmt_targets_summary(targets)}\n"
            f"📊 Jumlah akun: {len(akun_list)}\n"
            f"⏱️ Estimasi: {estimasi}\n\n"
            f"Konfirmasi untuk melanjutkan.",
            reply_markup=get_confirm_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_GABUNG_CONFIRM

    if pesan == "🔢 Jumlah Tertentu":
        akun_list = await db_find(collection, {})
        context.user_data["gabung_all_akun_list"] = akun_list
        await update.message.reply_text(
            f"🔢 Masukkan jumlah akun untuk join (1-{len(akun_list)}):",
            reply_markup=get_cancel_keyboard(),
        )
        context.user_data["gabung_waiting_jumlah"] = True
        return STATE_GABUNG_SCOPE

    if pesan == "🏷️ Berdasarkan Tag":
        await update.message.reply_text(
            "🏷️ Masukkan nama tag (contoh: marketing):",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_GABUNG_TAG

    # Handle jumlah input jika sedang menunggu
    if context.user_data.get("gabung_waiting_jumlah"):
        akun_list = context.user_data.get("gabung_all_akun_list") or await db_find(collection, {})
        try:
            jumlah = int(pesan)
        except ValueError:
            await update.message.reply_text(
                "❌ Input harus berupa angka. Coba lagi:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_GABUNG_SCOPE
        if jumlah < 1 or jumlah > len(akun_list):
            await update.message.reply_text(
                f"❌ Jumlah harus antara 1-{len(akun_list)}. Coba lagi:",
                reply_markup=get_cancel_keyboard(),
            )
            return STATE_GABUNG_SCOPE
        context.user_data.pop("gabung_waiting_jumlah", None)
        akun_terpilih = akun_list[:jumlah]
        context.user_data["gabung_akun_list"] = akun_terpilih
        settings = get_user_settings(context)
        estimasi = estimate_time(len(akun_terpilih) * max(1, len(targets)), settings["join_delay"])
        await update.message.reply_text(
            f"📦 *RINGKASAN JOIN*\n\n"
            f"👥 Target: {_fmt_targets_summary(targets)}\n"
            f"📊 Jumlah akun: {len(akun_terpilih)}\n"
            f"⏱️ Estimasi: {estimasi}\n\n"
            f"Konfirmasi untuk melanjutkan.",
            reply_markup=get_confirm_keyboard(),
            parse_mode="Markdown",
        )
        return STATE_GABUNG_CONFIRM

    await update.message.reply_text(
        "❌ Pilihan tidak valid. Gunakan tombol di bawah:",
        reply_markup=get_akun_scope_keyboard(),
    )
    return STATE_GABUNG_SCOPE

async def bot_gabung_tag(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    tag = pesan.strip().lower()
    if not tag:
        await update.message.reply_text(
            "❌ Tag tidak boleh kosong. Masukkan tag lagi:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_GABUNG_TAG

    akun_list = await db_find(collection, {})
    akun_terpilih = [
        a for a in akun_list if tag in [t.lower() for t in (a.get("tags", []) or [])]
    ]
    if not akun_terpilih:
        await update.message.reply_text(
            "⚠️ Tidak ada akun dengan tag tersebut. Masukkan tag lain:",
            reply_markup=get_cancel_keyboard(),
        )
        return STATE_GABUNG_TAG

    context.user_data["gabung_akun_list"] = akun_terpilih
    settings = get_user_settings(context)
    targets = context.user_data.get("gabung_targets") or []
    estimasi = estimate_time(len(akun_terpilih) * max(1, len(targets)), settings["join_delay"])

    # Reuse formatter dari bot_gabung_scope (inline di sini agar self-contained)
    if len(targets) <= 1:
        t = targets[0] if targets else {"display": "(tidak ada)", "type": "public"}
        tipe = "🔒 private" if t.get("type") == "private" else "🌐 public"
        target_summary = f"`{t['display']}` ({tipe})"
    else:
        preview = ", ".join([f"`{t['display']}`" for t in targets[:3]])
        if len(targets) > 3:
            preview += f", … (+{len(targets) - 3})"
        target_summary = f"*{len(targets)} target* — {preview}"

    await update.message.reply_text(
        f"📦 *RINGKASAN JOIN*\n\n"
        f"👥 Target: {target_summary}\n"
        f"📊 Jumlah akun: {len(akun_terpilih)}\n"
        f"🏷️ Tag: {tag}\n"
        f"⏱️ Estimasi: {estimasi}\n\n"
        f"Konfirmasi untuk melanjutkan.",
        reply_markup=get_confirm_keyboard(),
        parse_mode="Markdown",
    )
    return STATE_GABUNG_CONFIRM

async def bot_gabung_confirm(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    pesan = (update.message.text or "").strip()
    if pesan.startswith("🔙"):
        return await handle_cancel(update, context)

    targets = context.user_data.get("gabung_targets") or []
    akun_list = context.user_data.get("gabung_akun_list") or []
    if not targets or not akun_list:
        await bot_send_main_menu(update, context, "⚠️ Data tidak lengkap. Silakan ulangi.")
        return STATE_MAIN_MENU

    settings = get_user_settings(context)

    chat_id = update.effective_chat.id
    total_tasks = len(akun_list) * len(targets)

    cancel_event = asyncio.Event()
    pause_event = asyncio.Event()
    context.user_data["repeat_cancel_event"] = cancel_event
    context.user_data["repeat_done"] = False

    # Ringkasan target untuk dashboard
    if len(targets) <= 1:
        t = targets[0]
        tipe = ICON["locked"] + " private" if t.get("type") == "private" else ICON["public"] + " public"
        target_summary = f"`{t['display']}` ({tipe})"
    else:
        target_summary = f"*{len(targets)} target* (bulk)"

    # Generate run_id untuk registry runtime control
    run_id = _uuid.uuid4().hex[:10]
    register_runtime_control("gabung", run_id, cancel_event, pause_event, update.effective_user.id)

    # Live dashboard
    start_ts = _now_ts()
    initial_text = render_live_dashboard(
        title="BULK JOIN BERJALAN", icon=ICON["running"],
        target_summary=target_summary, accounts_count=len(akun_list),
        done=0, total=total_tasks, sukses=0, gagal=0, skip=0,
        start_ts=start_ts, current_line="Mempersiapkan batch pertama...",
    )
    live = await LiveMessage.create(
        context.bot, chat_id, initial_text=initial_text,
        reply_markup=build_runtime_inline_keyboard(run_id, kind="gabung"),
    )

    async def _stats_hook(stats):
        paused = pause_event.is_set()
        frame = SPINNER_FRAMES[(int(_now_ts() * 2) % len(SPINNER_FRAMES))]
        current_line = (
            f"{frame} Target {stats.get('current_target_idx', 1)}/{stats.get('total_targets', 1)}: "
            f"{stats.get('current_target', '-')}"
        )
        if paused:
            current_line = "⏸ PAUSED — tekan Resume untuk lanjut"
        txt = render_live_dashboard(
            title="BULK JOIN BERJALAN" + (" ⏸" if paused else ""),
            icon=ICON["running"],
            target_summary=target_summary,
            accounts_count=len(akun_list),
            done=stats["done"], total=total_tasks,
            sukses=stats["sukses"], gagal=stats["gagal"], skip=stats.get("skip", 0),
            start_ts=start_ts, current_line=current_line,
        )
        await live.update(txt, reply_markup=build_runtime_inline_keyboard(run_id, kind="gabung", paused=paused))

    async def run_gabung_task():
        try:
            hasil = await proses_join_semua_akun_async(
                targets,
                akun_list=akun_list,
                delay_detik=settings["join_delay"],
                parallel_batch=settings["parallel_batch"],
                cancel_event=cancel_event,
                stats_hook=_stats_hook,
                pause_event=pause_event,
            )
            # last_group & repeat data
            context.user_data["last_group"] = targets[0]["original"]
            context.user_data["last_gabung_targets"] = targets
            set_last_action(
                context, "gabung_grup",
                {"grup_username": targets[0]["original"],
                 "targets": targets, "akun_list": akun_list},
            )
            context.user_data["repeat_done"] = True
            # Finalize dashboard → ringkasan final
            final_txt = (
                f"{ICON['done']} *BULK JOIN SELESAI*\n\n"
                f"{ICON['timer']} Durasi: *{fmt_duration(_now_ts() - start_ts)}*\n\n"
                + hasil[:3600]
            )
            await live.finalize(final_txt)
            await send_toast(
                context.bot, chat_id,
                f"{ICON['success']} Bulk join selesai ({fmt_duration(_now_ts() - start_ts)})",
                duration=8,
            )
        except Exception as e:
            context.user_data["repeat_done"] = True
            await live.finalize(f"{ICON['error']} *Error:* {e}")
        finally:
            unregister_runtime_control("gabung", run_id)

    task = asyncio.create_task(run_gabung_task())
    context.user_data["repeat_task"] = task
    return STATE_REPEAT_RUNNING

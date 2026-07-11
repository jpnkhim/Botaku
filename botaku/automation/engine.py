from __future__ import annotations
from ..states import *
from ..keyboards import *
from ..database import *
from ..telegram_client import *
from ..ux import *
from ..config import *
import asyncio, uuid
from ..database import automation_collection, db_count, db_find, db_find_one
from ..telegram_client import get_telegram_client, safe_disconnect, safe_connect_and_check
def automation_create_index():
    """Buat index untuk automation_tasks (dipanggil sekali saat startup)."""
    try:
        if automation_collection is not None:
            automation_collection.create_index(
                [("owner_user_id", ASCENDING), ("name", ASCENDING)],
                unique=True,
            )
            automation_collection.create_index([("id", ASCENDING)], unique=True)
    except Exception:
        pass

def automation_save(owner_user_id: int, name: str, steps: list) -> tuple[bool, str]:
    """Simpan automation baru ke database. Return (sukses, id_atau_error)."""
    if automation_collection is None:
        return False, "Database tidak tersedia"
    if not name:
        return False, "Nama automation tidak boleh kosong"
    if not steps:
        return False, "Automation harus memiliki minimal 1 step"
    # Validasi step
    for i, step in enumerate(steps, 1):
        if step.get("type") not in AUTO_STEP_TYPES:
            return False, f"Step {i} tidak valid: {step.get('type')}"
    auto_id = _uuid.uuid4().hex[:12]
    doc = {
        "id": auto_id,
        "owner_user_id": owner_user_id,
        "name": name.strip(),
        "steps": steps,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        automation_collection.insert_one(doc)
        return True, auto_id
    except DuplicateKeyError:
        return False, f"Automation dengan nama '{name}' sudah ada"
    except Exception as e:
        return False, f"Error simpan: {e}"

def automation_list(owner_user_id: int) -> list:
    """Ambil daftar automation milik user. Exclude _id."""
    if automation_collection is None:
        return []
    try:
        return list(
            automation_collection.find(
                {"owner_user_id": owner_user_id}, {"_id": 0}
            ).sort("created_at", 1)
        )
    except Exception:
        return []

def automation_get(owner_user_id: int, auto_id: str) -> dict | None:
    if automation_collection is None:
        return None
    try:
        return automation_collection.find_one(
            {"owner_user_id": owner_user_id, "id": auto_id}, {"_id": 0}
        )
    except Exception:
        return None

def automation_delete(owner_user_id: int, auto_id: str) -> bool:
    if automation_collection is None:
        return False
    try:
        result = automation_collection.delete_one(
            {"owner_user_id": owner_user_id, "id": auto_id}
        )
        return result.deleted_count > 0
    except Exception:
        return False

def format_step_summary(step: dict) -> str:
    """Format 1 step jadi teks singkat untuk preview."""
    t = step.get("type")
    if t == "send_message":
        return f"✉️ Kirim: {shorten_text(step.get('text', ''), 60)}"
    if t == "click_button":
        return f"🔘 Klik Tombol ID: `{shorten_text(step.get('button_id', ''), 60)}`"
    if t == "delay":
        return f"⏱️ Delay {step.get('seconds', 0)} detik"
    if t == "wait_reply":
        return f"⏳ Tunggu Balasan (timeout {step.get('timeout', 30)}s)"
    if t == "send_txt_line":
        lines = step.get("lines", []) or []
        mode = "round-robin" if step.get("round_robin", True) else "skip-jika-habis"
        preview = shorten_text(lines[0], 40) if lines else "(kosong)"
        return f"📄 Kirim TXT/Akun ({len(lines)} baris, {mode}): {preview}…"
    if t == "send_txt_random":
        lines = step.get("lines", []) or []
        preview = shorten_text(lines[0], 40) if lines else "(kosong)"
        return f"🎲 Kirim TXT Random ({len(lines)} baris): {preview}…"
    return f"❓ {t}"

def format_automation_preview(auto: dict) -> str:
    """Format automation untuk preview lengkap."""
    lines = [f"🤖 *{auto.get('name', 'Unnamed')}*"]
    lines.append(f"🆔 `{auto.get('id', '')}`")
    steps = auto.get("steps", [])
    lines.append(f"📋 Total step: {len(steps)}")
    for i, step in enumerate(steps, 1):
        lines.append(f"  {i}. {format_step_summary(step)}")
    return "\n".join(lines)

async def _find_message_with_button_id(client, entity, button_id: str, limit: int = 20):
    """
    Scan pesan terbaru di chat untuk cari inline button berdasarkan:
      1. Exact match pada decoded callback_data
      2. Whitespace-trimmed match (handle trailing/leading space tersembunyi)
      3. Match berdasarkan teks tombol (fallback, berguna ketika user
         men-copy teks label alih-alih callback_data)
    Return: (message, button_data_bytes) atau (None, None)
    """
    try:
        messages = await safe_telegram_operation(
            client.get_messages(entity, limit=limit), timeout=TELEGRAM_OP_TIMEOUT
        )
    except Exception:
        return None, None

    target = (button_id or "").strip()
    if not target:
        return None, None

    # Pass 1: exact match pada callback_data (persis seperti di-input user)
    # Pass 2: trimmed match (ignore whitespace di kiri/kanan)
    trimmed_candidate = None
    for msg in messages:
        if not msg.buttons:
            continue
        for row in msg.buttons:
            for btn in row:
                raw = getattr(btn, "data", None)
                if not raw:
                    continue
                try:
                    decoded = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                except Exception:
                    decoded = str(raw)
                if decoded == button_id:
                    return msg, raw
                if trimmed_candidate is None and decoded.strip() == target:
                    trimmed_candidate = (msg, raw)
    if trimmed_candidate is not None:
        return trimmed_candidate

    # Pass 3: fallback match berdasarkan teks tombol (case-insensitive).
    # Hanya untuk tombol yang memiliki callback_data (bukan URL button).
    # Urutan: exact text → substring match
    target_lower = target.lower()
    substring_candidate = None
    for msg in messages:
        if not msg.buttons:
            continue
        for row in msg.buttons:
            for btn in row:
                raw = getattr(btn, "data", None)
                if not raw:
                    continue
                btn_text = (btn.text or "").strip().lower()
                if not btn_text:
                    continue
                if btn_text == target_lower:
                    return msg, raw
                if substring_candidate is None and (
                    target_lower in btn_text or btn_text in target_lower
                ):
                    substring_candidate = (msg, raw)
    if substring_candidate is not None:
        return substring_candidate
    return None, None

async def _wait_for_new_reply(client, entity, last_msg_id: int, timeout: int):
    """
    Tunggu pesan baru dari entity melebihi last_msg_id sampai timeout detik.
    Return: (success, new_msg_id_or_none).
    """
    start = asyncio.get_event_loop().time()
    poll_interval = 2
    while True:
        elapsed = asyncio.get_event_loop().time() - start
        if elapsed >= timeout:
            return False, None
        try:
            msgs = await safe_telegram_operation(
                client.get_messages(entity, limit=1), timeout=TELEGRAM_OP_TIMEOUT
            )
            if msgs and msgs[0].id > last_msg_id:
                return True, msgs[0].id
        except Exception:
            pass
        await asyncio.sleep(poll_interval)

async def execute_automation_for_account(
    automation: dict,
    akun: dict,
    target: str,
    loop_count: int,
    loop_delay: int,
    cancel_event: asyncio.Event,
    log_lines: list,
    stats: dict | None = None,
    account_index: int = 0,
):
    """
    Eksekusi 1 automation untuk 1 akun.
    loop_count: 0 = infinite, else jumlah iterasi.
    stats: dict opsional yang akan dipopulasi dengan statistik hasil eksekusi.
    account_index: urutan akun dalam daftar (dipakai untuk step send_txt_line
                   agar masing-masing akun dapat baris berbeda dari TXT).
    """
    nama_akun = akun.get("name", "Unknown")
    nomor = akun.get("nomor_telepon", "N/A")
    if stats is None:
        stats = {}
    stats.setdefault("nomor", nomor)
    stats.setdefault("name", nama_akun)
    stats.update({
        "loops_done": 0,
        "steps_success": 0,
        "steps_failed": 0,
        "dropped_reason": None,
        "status_change": None,
    })

    # Batas error berturut-turut sebelum akun di-drop (circuit breaker)
    MAX_CONSECUTIVE_ERRORS = 3

    client = None
    try:
        client = get_telegram_client(
            akun["string_sesi"],
            akun["api_id"],
            akun["api_hash"],
            connection_retries=1,
            retry_delay=1,
            timeout=TELEGRAM_CONNECT_TIMEOUT,
        )
        ok, err = await safe_connect_and_check(client, timeout=TELEGRAM_CONNECT_TIMEOUT)
        if not ok:
            # Mark status akun berdasarkan jenis error (konsisten dengan kirim_pesan_ke_bot_async)
            err_up = str(err or "").upper()
            if "SESSION" in err_up or "EXPIRED" in err_up or "AUTH_KEY" in err_up:
                update_account_status(nomor, "expired", str(err)[:200])
                stats["status_change"] = "expired"
            elif "TIMEOUT" in err_up:
                update_account_status(nomor, "timeout", str(err)[:200])
                stats["status_change"] = "timeout"
            elif "BANNED" in err_up or "DEACTIVATED" in err_up:
                update_account_status(nomor, "terblokir", str(err)[:200])
                stats["status_change"] = "terblokir"
            # else: connection error biasa, tidak mark status
            log_lines.append(f"❌ [{nomor}] Gagal connect: {shorten_text(str(err), 100)}")
            stats["dropped_reason"] = "connect_fail"
            return stats

        # Resolve target entity — cek restriction
        try:
            entity = await safe_telegram_operation(
                client.get_entity(target), timeout=TELEGRAM_OP_TIMEOUT
            )
        except Exception as e:
            is_restricted, status_r, alasan_r = is_account_restricted_error(e)
            if is_restricted:
                update_account_status(nomor, status_r, alasan_r)
                stats["status_change"] = status_r
                log_lines.append(
                    f"❌ [{nomor}] {status_r.upper()} saat resolve target: {shorten_text(alasan_r, 80)}"
                )
                stats["dropped_reason"] = f"target_restricted:{status_r}"
            else:
                log_lines.append(f"❌ [{nomor}] Target tidak ditemukan/diakses: {shorten_text(str(e), 100)}")
                stats["dropped_reason"] = "target_unreachable"
            return stats

        steps = automation.get("steps", [])
        iteration = 0
        infinite = (loop_count == 0)
        consecutive_errors = 0  # circuit breaker antar step dalam 1 iteration

        while infinite or iteration < loop_count:
            if cancel_event.is_set():
                log_lines.append(f"⏹️ [{nomor}] Dihentikan (loop {iteration + 1})")
                stats["dropped_reason"] = "cancelled"
                return stats

            # Pause support — block iteration loop while pause_event is set
            pause_event = stats.get("_pause_event")
            if pause_event is not None:
                while pause_event.is_set():
                    if cancel_event.is_set():
                        stats["dropped_reason"] = "cancelled"
                        return stats
                    await asyncio.sleep(0.5)

            # Re-check status dari DB antar loop (hanya mulai loop ke-2)
            # Supaya akun yang di-mark bermasalah di sisi lain (mis. kirim_pesan paralel)
            # tidak tetap dicoba ulang di loop berikutnya.
            if iteration > 0:
                try:
                    fresh = await db_find_one(collection, 
                        {"nomor_telepon": nomor},
                        {"_id": 0, "status": 1, "status_alasan": 1},
                    )
                    if fresh:
                        fresh_status = fresh.get("status", "aktif")
                        if fresh_status in SKIP_STATUSES:
                            log_lines.append(
                                f"⏹️ [{nomor}] Status berubah jadi `{fresh_status}` di tengah run — stop loop"
                            )
                            stats["dropped_reason"] = f"status_changed:{fresh_status}"
                            return stats
                except Exception:
                    pass  # tidak critical, lanjut saja

            iteration += 1
            stats["loops_done"] = iteration
            consecutive_errors = 0  # reset per loop
            log_lines.append(f"🔁 [{nomor}] Mulai loop ke-{iteration}")

            # Track last_msg_id untuk wait_reply baseline
            last_msg_id = 0
            try:
                recent = await safe_telegram_operation(
                    client.get_messages(entity, limit=1), timeout=TELEGRAM_OP_TIMEOUT
                )
                if recent:
                    last_msg_id = recent[0].id
            except Exception:
                pass

            for step_idx, step in enumerate(steps, 1):
                if cancel_event.is_set():
                    log_lines.append(f"⏹️ [{nomor}] Dihentikan di step {step_idx}")
                    stats["dropped_reason"] = "cancelled"
                    return stats
                t = step.get("type")
                step_success = False
                try:
                    if t == "send_message":
                        text = step.get("text", "")
                        sent = await safe_telegram_operation(
                            client.send_message(entity, text), timeout=TELEGRAM_OP_TIMEOUT
                        )
                        if sent:
                            last_msg_id = max(last_msg_id, sent.id)
                        log_lines.append(f"✅ [{nomor}] Step {step_idx}: Kirim pesan")
                        step_success = True
                    elif t == "send_txt_line":
                        lines = step.get("lines", []) or []
                        round_robin = step.get("round_robin", True)
                        if not lines:
                            log_lines.append(
                                f"⚠️ [{nomor}] Step {step_idx}: TXT kosong, di-skip"
                            )
                            step_success = True
                        else:
                            if round_robin:
                                line_idx = account_index % len(lines)
                            else:
                                line_idx = account_index
                            if line_idx >= len(lines):
                                log_lines.append(
                                    f"⚠️ [{nomor}] Step {step_idx}: Tidak ada baris "
                                    f"untuk akun ke-{account_index + 1} (skip)"
                                )
                                step_success = True
                            else:
                                text = lines[line_idx]
                                sent = await safe_telegram_operation(
                                    client.send_message(entity, text),
                                    timeout=TELEGRAM_OP_TIMEOUT,
                                )
                                if sent:
                                    last_msg_id = max(last_msg_id, sent.id)
                                log_lines.append(
                                    f"✅ [{nomor}] Step {step_idx}: Kirim TXT baris "
                                    f"{line_idx + 1}/{len(lines)}"
                                )
                                step_success = True
                    elif t == "send_txt_random":
                        lines = step.get("lines", []) or []
                        if not lines:
                            log_lines.append(
                                f"⚠️ [{nomor}] Step {step_idx}: TXT random kosong, di-skip"
                            )
                            step_success = True
                        else:
                            line_idx = random.randrange(len(lines))
                            text = lines[line_idx]
                            sent = await safe_telegram_operation(
                                client.send_message(entity, text),
                                timeout=TELEGRAM_OP_TIMEOUT,
                            )
                            if sent:
                                last_msg_id = max(last_msg_id, sent.id)
                            log_lines.append(
                                f"✅ [{nomor}] Step {step_idx}: Kirim TXT random baris "
                                f"{line_idx + 1}/{len(lines)}"
                            )
                            step_success = True
                    elif t == "delay":
                        sec = int(step.get("seconds", 0))
                        for _ in range(sec):
                            if cancel_event.is_set():
                                log_lines.append(f"⏹️ [{nomor}] Dihentikan saat delay")
                                stats["dropped_reason"] = "cancelled"
                                return stats
                            await asyncio.sleep(1)
                        log_lines.append(f"✅ [{nomor}] Step {step_idx}: Delay {sec}s")
                        step_success = True
                    elif t == "click_button":
                        btn_id = step.get("button_id", "")
                        scan_limit = int(step.get("scan_limit", 20))
                        msg, raw_data = await _find_message_with_button_id(
                            client, entity, btn_id, limit=scan_limit
                        )
                        if msg is None:
                            log_lines.append(
                                f"⚠️ [{nomor}] Step {step_idx}: Button ID '{shorten_text(btn_id, 40)}' tidak ditemukan"
                            )
                            # Tidak dianggap error fatal, juga tidak sukses
                            step_success = True  # continue ke step lain
                        else:
                            try:
                                await safe_telegram_operation(
                                    msg.click(data=raw_data), timeout=TELEGRAM_OP_TIMEOUT
                                )
                                log_lines.append(
                                    f"✅ [{nomor}] Step {step_idx}: Klik button '{shorten_text(btn_id, 40)}'"
                                )
                                step_success = True
                            except Exception as e_click:
                                # Click failure bisa jadi restriction, cek
                                raise e_click
                    elif t == "wait_reply":
                        timeout_sec = int(step.get("timeout", 30))
                        ok_reply, new_id = await _wait_for_new_reply(
                            client, entity, last_msg_id, timeout_sec
                        )
                        if ok_reply:
                            last_msg_id = new_id
                            log_lines.append(f"✅ [{nomor}] Step {step_idx}: Dapat balasan")
                        else:
                            log_lines.append(
                                f"⚠️ [{nomor}] Step {step_idx}: Timeout tunggu balasan ({timeout_sec}s)"
                            )
                        step_success = True
                    else:
                        log_lines.append(f"⚠️ [{nomor}] Step {step_idx}: Tipe tidak dikenal ({t})")
                        step_success = True

                    if step_success:
                        stats["steps_success"] += 1
                        consecutive_errors = 0  # reset saat step sukses
                except FloodWaitError as e:
                    update_account_status(nomor, "flood_wait", f"FloodWait {e.seconds}s")
                    stats["status_change"] = "flood_wait"
                    stats["steps_failed"] += 1
                    log_lines.append(
                        f"❌ [{nomor}] Step {step_idx}: FLOOD_WAIT {e.seconds}s — stop untuk akun ini"
                    )
                    stats["dropped_reason"] = f"flood_wait:{e.seconds}s"
                    return stats
                except asyncio.TimeoutError:
                    # Timeout Telegram operation — bisa indikasi akun dibatasi
                    consecutive_errors += 1
                    stats["steps_failed"] += 1
                    log_lines.append(
                        f"⌛ [{nomor}] Step {step_idx}: TIMEOUT ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS} error berturut)"
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        update_account_status(nomor, "timeout", "Consecutive timeout di automation")
                        stats["status_change"] = "timeout"
                        stats["dropped_reason"] = f"consecutive_timeout:{consecutive_errors}"
                        log_lines.append(
                            f"🛑 [{nomor}] Drop akun — {consecutive_errors} timeout berturut (akun kemungkinan bermasalah)"
                        )
                        return stats
                except (ConnectionError, OSError, ConnectionResetError) as e:
                    consecutive_errors += 1
                    stats["steps_failed"] += 1
                    log_lines.append(
                        f"🔌 [{nomor}] Step {step_idx}: Connection error ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {shorten_text(str(e), 60)}"
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        update_account_status(nomor, "timeout", f"Connection instability: {shorten_text(str(e), 80)}")
                        stats["status_change"] = "timeout"
                        stats["dropped_reason"] = f"consecutive_connection_error:{consecutive_errors}"
                        log_lines.append(
                            f"🛑 [{nomor}] Drop akun — {consecutive_errors} connection error berturut"
                        )
                        return stats
                except Exception as e:
                    is_restricted, status_r, alasan_r = is_account_restricted_error(e)
                    if is_restricted:
                        update_account_status(nomor, status_r, alasan_r)
                        stats["status_change"] = status_r
                        stats["steps_failed"] += 1
                        log_lines.append(
                            f"❌ [{nomor}] Step {step_idx}: {status_r.upper()} — {shorten_text(alasan_r, 60)} — stop"
                        )
                        stats["dropped_reason"] = f"restricted:{status_r}"
                        return stats
                    # Error non-restricted biasa: lanjut step berikutnya, tapi hitung
                    consecutive_errors += 1
                    stats["steps_failed"] += 1
                    log_lines.append(
                        f"❌ [{nomor}] Step {step_idx} error ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {shorten_text(str(e), 100)}"
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        stats["dropped_reason"] = f"consecutive_errors:{consecutive_errors}"
                        log_lines.append(
                            f"🛑 [{nomor}] Drop akun — {consecutive_errors} error berturut (akun kemungkinan bermasalah, tidak di-mark status)"
                        )
                        return stats
                    # else: lanjut step berikutnya
            # End of steps loop
            if not infinite and iteration >= loop_count:
                break
            # Delay antar loop
            if loop_delay > 0:
                for _ in range(loop_delay):
                    if cancel_event.is_set():
                        stats["dropped_reason"] = "cancelled"
                        return stats
                    await asyncio.sleep(1)
        log_lines.append(f"🏁 [{nomor}] Selesai ({iteration} loop, {stats['steps_success']} sukses, {stats['steps_failed']} fail)")
        return stats
    except asyncio.CancelledError:
        log_lines.append(f"⏹️ [{nomor}] Task di-cancel")
        stats["dropped_reason"] = "task_cancelled"
        raise
    except Exception as e:
        log_lines.append(f"❌ [{nomor}] Error fatal: {shorten_text(str(e), 120)}")
        stats["dropped_reason"] = f"fatal:{shorten_text(str(e), 80)}"
        return stats
    finally:
        await safe_disconnect(client)

def start_automation_run(
    automation: dict,
    akun_list: list,
    target: str,
    loop_count: int,
    loop_delay: int,
    owner_user_id: int,
    completion_callback=None,
    parallel_batch: int = 0,
    account_delay: int = 0,
):
    """
    Daftar ke registry lalu buat task asyncio per akun.
    parallel_batch: 0 = semua akun serentak (unlimited); N>0 = max N akun aktif bersamaan (semaphore).
    account_delay: detik delay antar akun saat start (akun ke-N start di detik N*account_delay).
    Return: (run_id, log_lines_list, cancel_event)
    """
    run_id = f"{automation['id']}_{_uuid.uuid4().hex[:6]}"
    cancel_event = asyncio.Event()
    pause_event = asyncio.Event()
    log_lines: list = []
    stats_list: list = []  # statistik per-akun

    # Semaphore untuk batasi jumlah akun aktif bersamaan.
    # parallel_batch = 0 → tanpa batas (semua serentak).
    semaphore = asyncio.Semaphore(parallel_batch) if parallel_batch and parallel_batch > 0 else None

    async def _wrapped_task(idx, akun, akun_stats):
        # Stagger start antar akun
        if account_delay and account_delay > 0 and idx > 0:
            try:
                for _ in range(idx * account_delay):
                    if cancel_event.is_set():
                        akun_stats["dropped_reason"] = "cancelled_before_start"
                        return akun_stats
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
        if cancel_event.is_set():
            akun_stats["dropped_reason"] = "cancelled_before_start"
            return akun_stats
        if semaphore is not None:
            async with semaphore:
                return await execute_automation_for_account(
                    automation, akun, target, loop_count, loop_delay,
                    cancel_event, log_lines, akun_stats, idx,
                )
        return await execute_automation_for_account(
            automation, akun, target, loop_count, loop_delay,
            cancel_event, log_lines, akun_stats, idx,
        )

    tasks = []
    for idx, akun in enumerate(akun_list):
        akun_stats = {
            "nomor": akun.get("nomor_telepon", "N/A"),
            "name": akun.get("name", "Unknown"),
            "_pause_event": pause_event,  # dibaca oleh execute_automation_for_account
        }
        stats_list.append(akun_stats)
        task = asyncio.create_task(_wrapped_task(idx, akun, akun_stats))
        tasks.append(task)

    running_automations[run_id] = {
        "run_id": run_id,
        "automation_id": automation["id"],
        "name": automation["name"],
        "owner_user_id": owner_user_id,
        "tasks": tasks,
        "cancel_event": cancel_event,
        "pause_event": pause_event,
        "started_at": _now_iso(),
        "started_ts": _now_ts(),
        "target": target,
        "accounts_count": len(akun_list),
        "loop_count": loop_count,
        "loop_delay": loop_delay,
        "log_lines": log_lines,
        "stats_list": stats_list,
        "parallel_batch": parallel_batch,
        "account_delay": account_delay,
    }

    # Auto-cleanup task ketika semua selesai
    async def _watcher():
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            info = running_automations.pop(run_id, None)
            if completion_callback and info is not None:
                try:
                    await completion_callback(info)
                except Exception:
                    pass

    asyncio.create_task(_watcher())
    return run_id, log_lines, cancel_event

def stop_automation_run(run_id: str, owner_user_id: int) -> bool:
    """Stop automation run yang sedang jalan. Return True jika ditemukan & dihentikan."""
    info = running_automations.get(run_id)
    if not info:
        return False
    if info.get("owner_user_id") != owner_user_id:
        return False
    info["cancel_event"].set()
    for t in info.get("tasks", []):
        if not t.done():
            t.cancel()
    return True

def list_running_automations(owner_user_id: int) -> list:
    """Daftar automation yang sedang jalan milik user."""
    return [
        info for info in running_automations.values()
        if info.get("owner_user_id") == owner_user_id
    ]

def get_submenu_automation_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ Buat Automation", callback_data="sub_auto_create"),
         InlineKeyboardButton("📋 Daftar Automation", callback_data="sub_auto_list")],
        [InlineKeyboardButton("▶️ Jalankan Automation", callback_data="sub_auto_run"),
         InlineKeyboardButton("⏹️ Stop Automation", callback_data="sub_auto_stop")],
        [InlineKeyboardButton("🗑️ Hapus Automation", callback_data="sub_auto_delete"),
         InlineKeyboardButton("📅 Jadwal", callback_data="sub_auto_schedule")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="sub_back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_submenu_automation_keyboard():
    return _make_keyboard(SUBMENU_AUTOMATION)

def get_auto_step_menu_keyboard():
    return _make_keyboard(AUTO_STEP_MENU_BUTTONS)

def get_auto_loop_keyboard():
    return _make_keyboard(AUTO_LOOP_BUTTONS)

def build_next_steps(items):
    if not items:
        return ""
    lines = ["", "Langkah selanjutnya:"]
    for item in items:
        lines.append(f"• {item}")
    return "\n".join(lines)

def _stats_automation_count(user_id):
    try:
        return automation_collection.count_documents({"owner_user_id": user_id}) if automation_collection is not None else 0
    except Exception:
        return 0

def get_automation_list_keyboard(items, action_prefix="aut_view"):
    """Membuat inline keyboard untuk daftar script automation."""
    buttons = []
    for a in items:
        name = a.get("name", "Unnamed")
        id_ = a.get("id", "")
        steps_count = len(a.get("steps", []))
        label = f"🤖 {name} ({steps_count} step)"
        buttons.append([InlineKeyboardButton(label, callback_data=f"{action_prefix}:{id_}")])
        
    if action_prefix == "aut_view":
        buttons.append([
            InlineKeyboardButton("➕ Buat Baru", callback_data="sub_auto_create"),
            InlineKeyboardButton("📅 Jadwal", callback_data="sub_auto_schedule")
        ])
    buttons.append([InlineKeyboardButton("🔙 Kembali ke Menu", callback_data="sub_back_automation")])
    return InlineKeyboardMarkup(buttons)

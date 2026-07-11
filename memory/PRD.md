# PRD - TeleKu Bot (Botaku Final Modular)

## Original Problem
User memiliki bot Telegram (Botaku Final Modular) yang tidak dapat berfungsi 100%. Diminta perbaikan semua fitur agar berjalan, penyederhanaan UX (hapus tombol menu reply karena sudah pakai inline button), dan penambahan pencarian pada daftar akun (paginated slide page). Target deploy: Koyeb Free Web Service.

## Architecture
- **Runtime**: Python 3.11, python-telegram-bot 20.7 (long-polling), Telethon 1.34
- **Storage**: MongoDB (Firestore compatible) via pymongo
- **Deployment**: Docker + Koyeb Free (port 8000 health check)
- **Bot state**: ConversationHandler dengan 75 state

## User Personas
- Admin utama: menjalankan operasi kirim pesan massal, kelola multi-akun Telegram, jadwalkan automation

## Core Requirements
1. Kirim pesan multi-akun (paralel batch, delay, cancel/pause)
2. Bulk join grup/channel (public + private invite)
3. Kirim TXT round-robin
4. Ambil OTP & inline button ID
5. Kelola akun: login OTP / manual, list, info, test, hapus, reset status, tag, cari
6. Automation multi-step (kirim/klik/delay/tunggu/TXT random)
7. Scheduler harian + interval + jitter
8. Import/Export JSON
9. Inline-only interactive UI

## Fixes Applied (Jan 2026)
- `config.py`: tambah import `asyncio`, `random`, `uuid`, `io`, `json`, `datetime`, `timedelta`
- `other.py`: tambah `simpan_data()`, `validasi_akun_telegram()`, `update_account_status()`; hapus import circular ke `handlers.common`
- `handlers/common.py`: import `other` + `automation.engine` + `automation.scheduler` via `import *` supaya semua handler dapat mengakses `log_action`, `set_last_action`, `build_next_steps`, dll
- `ux.py`: tambah `shorten_text`, `join_lines_truncate`, `render_live_dashboard`, `register_runtime_control`, `unregister_runtime_control`, `build_runtime_inline_keyboard`, `bot_runtime_callback`, `send_toast`, dan `LiveMessage.finalize()` / `close()`
- `keyboards.py`: import konstanta button dari `config.py` (`SUBMENU_EXPORT`, `AUTO_LOOP_BUTTONS`, `CANCEL_BUTTON`, `AKUN_SCOPE_BUTTONS`, dst)
- `start.py` + `common.py`: hilangkan physical menu reply keyboard, semua interaktif via inline button
- `accounts.py` + `keyboards.py`: tambah tombol **🔎 Cari Akun** di paginated keyboard + handler `bot_accounts_search_callback`, `bot_accounts_search_input`, `bot_accounts_search_cancel_callback`
- `bot.py`: daftarkan handler callback baru untuk `acc_search:` dan `acc_search_cancel:`
- `menu.py::bot_menu_router`: deteksi flag `awaiting_acc_search` supaya text input pencarian dirouting ke handler yang tepat
- `requirements.txt`: hapus Flask (tidak dipakai)
- `Dockerfile`: pakai `python -u main.py` untuk unbuffered logs
- `README.md`: instruksi deploy ke Koyeb lengkap

## Verified
- `python main.py` → bot connect ke Telegram + MongoDB, scheduler start, polling aktif ✅
- Semua modul import tanpa NameError ✅
- Search flow paginated akun bekerja (verified via mock test) ✅
- Callback handler runtime (Pause/Resume/Stop) registered ✅

## Backlog / Future
- Statistik chart per-akun (kirim/ban/success rate)
- Multi-user (bukan single admin)
- Auto-detect akun expired setiap X jam
- Web dashboard companion

## Deployment
Push repo ke GitHub → Create service di Koyeb dengan Docker builder → set env `TELEKU_BOT_TOKEN`, `TELEKU_MONGO_URL`, `ADMIN_USER_IDS`, `PORT=8000` → scaling min=1 max=1.

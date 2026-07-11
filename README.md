# TeleKu Bot - Versi Modular (Fix Mudah)

Struktur modular untuk memudahkan fix seperti yang diminta.

## Struktur
```
botaku_modular/
├── main.py                 # Entry point Koyeb (health check + singleton lock)
├── botaku/
│   ├── __init__.py
│   ├── config.py           # BOT_TOKEN, MONGO_URL, ADMIN_USER_IDS, timeouts
│   ├── database.py         # init_database + async wrappers db_find, db_count (fix blocking)
│   ├── ux.py               # ICON, pbar, LiveMessage
│   ├── telegram_client.py  # get_telegram_client + safe_* (fix sync vs async)
│   ├── bot.py              # build_application + ConversationHandler (per_message=True fix)
│   └── handlers/
│       ├── __init__.py
│       ├── common.py       # is_admin, keyboards, safe_edit_query_message (fix inline button mati)
│       ├── start.py        # /start & /help
│       ├── menu.py         # cat_ & sub_ callbacks (fix Kirim Pesan tidak respon)
│       └── kirim.py        # kirim pesan stubs (mudah di-expand)
├── requirements.txt
├── Dockerfile
```

## Kenapa Modular Memudahkan Fix?

1. **Inline button mati?** → Cek `botaku/handlers/menu.py` & `common.py` saja, tidak perlu scroll 10k baris
2. **Conflict di Koyeb?** → Cek `main.py` (singleton lock + health check)
3. **DB blocking?** → Cek `database.py` (async wrappers)
4. **Token Bocor?** → Cek `config.py` (env only, no hardcoded)
5. **/start tidak respon?** → Cek `bot.py` (fallback handlers outside ConversationHandler)

## Cara Pakai
```bash
pip install -r requirements.txt
export TELEKU_BOT_TOKEN=...
export TELEKU_MONGO_URL=...
export ADMIN_USER_IDS=...
python main.py
```

Untuk Koyeb, sama seperti sebelumnya, tapi CMD sekarang `python main.py` (lebih ringan dan modular).

## Next Step
Versi ini adalah skeleton modular. Untuk migrasi full 10k baris:
- Copy fungsi dari `telekuq_fixed.py` ke modul yang sesuai (sudah ada contoh untuk start & kirim)
- Ganti `from botaku.handlers...` di `bot.py` untuk include semua states
- Tes dengan `python -m py_compile`

Keuntungan: Kalau besok ada tombol baru yang error, cukup edit 1 file di `handlers/`, tidak perlu takut merusak 10k baris lain.

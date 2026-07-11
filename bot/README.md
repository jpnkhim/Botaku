# 🤖 TeleKu Bot - Multi-Account Telegram Automation

Bot Telegram multi-akun untuk otomasi pesan, join grup, OTP, dan automation
scripting. Full-modular, siap deploy ke Koyeb Free Web Service.

---

## 🚀 Deploy ke Koyeb (Free Tier)

### 1. Push ke GitHub
Push seluruh folder `/app/bot` ke repository GitHub Anda.

### 2. Buat App di Koyeb
1. Login ke [https://app.koyeb.com](https://app.koyeb.com)
2. **Create Service** → **GitHub** → pilih repo & branch
3. **Builder**: pilih **Dockerfile**
4. **Instance type**: `Free` (Nano)
5. **Region**: `sin` (Singapore) atau region terdekat
6. **Ports**: HTTP `8000` (health check di path `/`)
7. **Scaling**: Min 1, Max 1 (WAJIB untuk hindari 409 Conflict)

### 3. Environment Variables (WAJIB)
Tambahkan di section **Environment variables** Koyeb:

| Key                | Value                                                                 |
|--------------------|-----------------------------------------------------------------------|
| `TELEKU_BOT_TOKEN` | Token bot dari @BotFather                                             |
| `TELEKU_MONGO_URL` | Connection string MongoDB (Firestore/Atlas)                           |
| `ADMIN_USER_IDS`   | User ID Telegram admin (pisahkan koma jika lebih dari satu)           |
| `PORT`             | `8000` (default, sudah di-expose di Dockerfile)                       |
| `PYTHONUNBUFFERED` | `1`                                                                   |

### 4. Deploy
Klik **Deploy**. Setelah build sukses, buka log Koyeb, tunggu sampai muncul:

```
✅ Bot Telegram berjalan (FINAL MODULAR - full features)
```

Lalu chat `/start` ke bot Anda di Telegram.

---

## 🖥️ Menjalankan Secara Lokal (Dev)

```bash
cd /app/bot
cp .env.example .env
# Edit .env dengan token & MongoDB URL Anda
pip install -r requirements.txt
python main.py
```

⚠️ **Penting:** Jangan menjalankan bot di 2 tempat sekaligus (lokal + Koyeb),
Telegram akan memberi error `409 Conflict`. Matikan salah satu.

---

## ✨ Fitur Utama

### 📨 Kirim Pesan
- **Kirim Pesan**: kirim pesan ke target dari multi-akun (paralel batch)
- **Kirim Cepat**: workflow ringkas tanpa validasi target
- **Kirim File TXT**: 1 baris per pesan, round-robin ke semua akun
- **OTP**: baca pesan OTP terbaru per akun
- **Ulangi Aksi Terakhir**: replay 1-klik

### 👤 Kelola Akun
- Tambah akun via **Login OTP** (API ID/hash + nomor + OTP)
- Tambah akun **Manual** (paste string session)
- **Paginated list** + **🔎 Cari Akun** (nama/nomor/username/tag)
- Info detail, test koneksi, hapus, reset status
- **Tag** akun untuk pengelompokan (marketing, VIP, dll)

### 👥 Gabung Grup / Channel (Bulk Join)
- Support public (`@username`, `t.me/username`) & private invite (`t.me/+xxx`)
- Multi-target: paste multi-baris atau upload file `.txt`
- Live dashboard progress dengan Pause/Resume/Stop

### 🤖 Automation & 📅 Scheduler
- Buat automation multi-step (kirim pesan, klik button, delay, wait reply,
  kirim TXT per-akun, kirim TXT random)
- Loop N-kali atau infinite
- Jadwal harian `HH:MM` atau interval detik
- Randomize time (jitter ±X menit) supaya jadwal tidak kaku
- Live dashboard + notif otomatis saat selesai

### 📦 Import & Export
- Export semua akun ke JSON (backup)
- Import dari JSON
- Export ringkasan ke chat

### 🛠️ Tools & Pengaturan
- Ambil ID Button interaktif (untuk step Klik Tombol)
- Test koneksi database
- Pengaturan delay, batch paralel, dll

---

## 🎨 UI/UX

- **Inline button 100%** — tidak ada physical reply keyboard yang mengganggu
- **Paginated list** dengan tombol **🔎 Cari Akun** untuk filter cepat
- **Live dashboard** dengan progress bar, ETA, sparkline trend, dan tombol
  Pause / Resume / Stop
- **Toast notification** setelah proses selesai

---

## 📁 Struktur Kode

```
bot/
├── main.py                      # entry point
├── botaku/
│   ├── config.py                # env, constants, buttons
│   ├── database.py              # MongoDB init + async wrappers
│   ├── telegram_client.py       # Telethon helpers + safe wrappers
│   ├── ux.py                    # LiveMessage, dashboard, runtime control
│   ├── keyboards.py             # inline + reply keyboards
│   ├── states.py                # 75 ConversationHandler states
│   ├── other.py                 # simpan_data, log, validasi_target, dll
│   ├── bot.py                   # build_application()
│   ├── automation/
│   │   ├── engine.py            # save/list/run automation
│   │   └── scheduler.py         # schedule save/toggle/trigger loop
│   └── handlers/
│       ├── start.py             # /start & /help
│       ├── common.py            # helper umum (send_main_menu, cancel)
│       ├── menu.py              # category & submenu callback router
│       ├── accounts.py          # tambah/login/hapus/test/tag/search
│       ├── kirim.py             # kirim pesan + kirim cepat
│       ├── kirim_file.py        # kirim TXT round-robin
│       ├── join.py              # bulk join grup/channel
│       ├── otp.py               # ambil OTP
│       ├── export.py            # export/import JSON, repeat action
│       ├── settings.py          # settings + btnid
│       ├── automation.py        # buat/kelola/run automation
│       └── schedule.py          # buat/kelola jadwal
└── Dockerfile
```

---

## 🐛 Troubleshooting

| Gejala                                                    | Solusi                                                                 |
|-----------------------------------------------------------|------------------------------------------------------------------------|
| `Conflict: terminated by other getUpdates`                | Ada 2 instance bot jalan. Matikan salah satu (lokal atau Koyeb).       |
| `Address already in use` di Koyeb                         | Sudah di-handle otomatis (skip health server bila port kepakai).       |
| Bot tidak jawab / diam                                    | Cek log Koyeb. Pastikan `TELEKU_BOT_TOKEN` valid.                      |
| `ADMIN_USER_IDS` kosong                                   | User pertama yang chat `/start` otomatis jadi admin.                   |
| Import JSON gagal                                         | Pastikan format JSON adalah list of object dengan field `api_id`, `api_hash`, `nomor_telepon`, `string_sesi`. |

---

## 📜 License
MIT

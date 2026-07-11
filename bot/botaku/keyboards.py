from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from .config import (
    MAIN_MENU_BUTTONS as _CONF_MAIN_MENU_BUTTONS,
    SUBMENU_KIRIM as _CONF_SUBMENU_KIRIM,
    SUBMENU_AKUN as _CONF_SUBMENU_AKUN,
    SUBMENU_EXPORT,
    SUBMENU_SETTINGS,
    SUBMENU_AUTOMATION,
    SUBMENU_SCHEDULE,
    SCH_MODE_BUTTONS,
    AUTO_STEP_MENU_BUTTONS,
    AUTO_LOOP_BUTTONS,
    AUTO_RUN_AKUN_SCOPE_BUTTONS,
    CANCEL_BUTTON,
    AKUN_SCOPE_BUTTONS,
    CANCEL_REPEAT_BUTTONS,
    CANCEL_SENDING_BUTTONS,
    SETTINGS_MENU_BUTTONS as _CONF_SETTINGS_MENU_BUTTONS,
    RESET_STATUS_BUTTONS as _CONF_RESET_STATUS_BUTTONS,
    SELESAI_BUTTONS as _CONF_SELESAI_BUTTONS,
    CONFIRM_BUTTONS as _CONF_CONFIRM_BUTTONS,
    DEFAULT_SETTINGS as _CONF_DEFAULT_SETTINGS,
)
# Constants for menus (from original)
MAIN_MENU_BUTTONS = [
    ["📨 Kirim Pesan", "👤 Kelola Akun"],
    ["👥 Gabung Grup", "📦 Import & Export"],
    ["🤖 Automation", "🛠️ Tools & Pengaturan"],
    ["❓ Bantuan"]
]
SUBMENU_KIRIM = [["⚡ Kirim Cepat", "📤 Kirim Pesan"], ["📄 Kirim File TXT"], ["🔐 Ambil Pesan OTP", "🔁 Ulangi Aksi Terakhir"], ["🔙 Kembali"]]
SUBMENU_AKUN = []
# ... (simplified, actual keyboards will be defined in functions below)

def _make_keyboard(buttons):
    return ReplyKeyboardMarkup([[KeyboardButton(t) for t in row] for row in buttons], resize_keyboard=True)

def get_categories_inline_keyboard():
    """Membuat keyboard inline untuk kategori menu utama."""
    keyboard = [
        [InlineKeyboardButton("📨 Kirim Pesan", callback_data="cat_kirim"),
         InlineKeyboardButton("👤 Kelola Akun", callback_data="cat_akun")],
        [InlineKeyboardButton("👥 Gabung Grup", callback_data="cat_join"),
         InlineKeyboardButton("📦 Import & Export", callback_data="cat_export")],
        [InlineKeyboardButton("🤖 Automation", callback_data="cat_automation"),
         InlineKeyboardButton("🛠️ Tools & Pengaturan", callback_data="cat_settings")],
        [InlineKeyboardButton("❓ Bantuan", callback_data="cat_help")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_submenu_kirim_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("⚡ Kirim Cepat", callback_data="sub_kirim_cepat"),
         InlineKeyboardButton("📤 Kirim Pesan", callback_data="sub_kirim_pesan")],
        [InlineKeyboardButton("📄 Kirim File TXT", callback_data="sub_kirim_file")],
        [InlineKeyboardButton("🔐 Ambil Pesan OTP", callback_data="sub_kirim_otp"),
         InlineKeyboardButton("🔁 Ulangi Aksi Terakhir", callback_data="sub_kirim_repeat")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="sub_back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


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


def get_submenu_export_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("📥 Export JSON", callback_data="sub_export_json"),
         InlineKeyboardButton("🧾 Export Ringkasan", callback_data="sub_export_ringkasan")],
        [InlineKeyboardButton("⬆️ Import JSON", callback_data="sub_import_json")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="sub_back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_submenu_settings_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("⚙️ Pengaturan", callback_data="sub_settings_opt"),
         InlineKeyboardButton("🔍 Test Database", callback_data="sub_settings_testdb")],
        [InlineKeyboardButton("🔘 Ambil ID Button", callback_data="sub_settings_btnid")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="sub_back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


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


def get_submenu_schedule_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ Buat Jadwal", callback_data="sub_sch_create"),
         InlineKeyboardButton("📋 Daftar Jadwal", callback_data="sub_sch_list")],
        [InlineKeyboardButton("🔀 Toggle ON/OFF", callback_data="sub_sch_toggle"),
         InlineKeyboardButton("🗑️ Hapus Jadwal", callback_data="sub_sch_delete")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="sub_back_automation")]
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

    # Tombol cari akun (khusus action yang butuh)
    if show_search:
        buttons.append([
            InlineKeyboardButton("🔎 Cari Akun", callback_data=f"acc_search:{action}"),
        ])

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


def get_main_menu_keyboard():
    """Membuat keyboard utama untuk bot Telegram."""
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in MAIN_MENU_BUTTONS],
        resize_keyboard=True,
    )



def get_submenu_kirim_keyboard():
    return _make_keyboard(SUBMENU_KIRIM)



def get_submenu_akun_keyboard():
    return _make_keyboard(SUBMENU_AKUN)



def get_submenu_export_keyboard():
    return _make_keyboard(SUBMENU_EXPORT)



def get_submenu_settings_keyboard():
    return _make_keyboard(SUBMENU_SETTINGS)



def get_submenu_automation_keyboard():
    return _make_keyboard(SUBMENU_AUTOMATION)



def get_submenu_schedule_keyboard():
    return _make_keyboard(SUBMENU_SCHEDULE)



def get_sch_mode_keyboard():
    return _make_keyboard(SCH_MODE_BUTTONS)



def get_auto_step_menu_keyboard():
    return _make_keyboard(AUTO_STEP_MENU_BUTTONS)



def get_auto_loop_keyboard():
    return _make_keyboard(AUTO_LOOP_BUTTONS)



def get_auto_run_akun_scope_keyboard():
    return _make_keyboard(AUTO_RUN_AKUN_SCOPE_BUTTONS)



def get_cancel_keyboard():
    """Membuat keyboard dengan tombol cancel."""
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in CANCEL_BUTTON],
        resize_keyboard=True,
    )


CONFIRM_BUTTONS = [["✅ Ya, lanjutkan"], ["🔙 Kembali ke Menu Utama"]]

SETTINGS_MENU_BUTTONS = [
    ["1️⃣ Default OTP", "2️⃣ Delay Kirim Pesan"],
    ["3️⃣ Delay Join Grup", "4️⃣ Interval Progres"],
    ["5️⃣ Batch Paralel"],
    ["6️⃣ Auto: Batch Paralel", "7️⃣ Auto: Delay antar Akun"],
    ["🔙 Kembali ke Menu Utama"],
]

RESET_STATUS_BUTTONS = [
    ["1️⃣ Reset Semua"],
    ["2️⃣ Timeout & Flood", "3️⃣ Dibatasi"],
    ["4️⃣ Expired", "5️⃣ Terblokir"],
    ["6️⃣ Nomor Tertentu"],
    ["🔙 Kembali ke Menu Utama"],
]



def get_settings_menu_keyboard():
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in SETTINGS_MENU_BUTTONS],
        resize_keyboard=True,
    )



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



def get_cancel_repeat_keyboard():
    """Membuat keyboard dengan tombol cancel untuk proses repeat."""
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in CANCEL_REPEAT_BUTTONS],
        resize_keyboard=True,
    )



def get_confirm_keyboard():
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in CONFIRM_BUTTONS],
        resize_keyboard=True,
    )


DEFAULT_SETTINGS = {
    "otp_default": 5,
    "kirim_delay": 2,
    "join_delay": 3,
    "progress_step": 5,
    "parallel_batch": 3,
    "auto_parallel_batch": 0,   # 0 = semua akun serentak (unlimited)
    "auto_account_delay": 0,    # detik delay antar akun saat start automation
}



def get_cancel_sending_keyboard():
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in CANCEL_SENDING_BUTTONS],
        resize_keyboard=True,
    )


SELESAI_BUTTONS = [["🔀 Acak & Kirim Ulang"], ["🔙 Kembali ke Menu Utama"]]



def get_selesai_keyboard():
    if ReplyKeyboardMarkup is None:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text) for text in row] for row in SELESAI_BUTTONS],
        resize_keyboard=True,
    )



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

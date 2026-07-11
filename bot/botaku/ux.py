"""
botaku.ux - UX Infrastructure: icons, pbar, LiveMessage, dashboard, runtime control
"""
from __future__ import annotations
import asyncio
import logging
import time as _t
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger("telekubot")

ICON = {
    "running": "⚡", "success": "✅", "error": "❌", "pending": "⏳",
    "skip": "⏭️", "warn": "⚠️", "info": "ℹ️",
    "locked": "🔒", "public": "🌐", "bot": "🤖",
    "queue": "🪣", "timer": "⏱️", "stats": "📊", "target": "🎯",
    "users": "👥", "loop": "🔁", "done": "🏁", "stopped": "⏹",
    "pause": "⏸", "play": "▶️", "fire": "🔥", "spark": "✨",
    "trend": "📈", "down": "📉", "clock": "🕐", "sent": "📤",
}

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"

def pbar(done: int, total: int, width: int = 12) -> str:
    if total <= 0:
        return "▱" * width + "   0%"
    done = max(0, min(done, total))
    filled = int(width * done / total)
    pct = int(100 * done / total)
    return f"{'▰' * filled}{'▱' * (width - filled)}  {pct:3d}%  ({done}/{total})"

def fmt_duration(secs: float) -> str:
    if secs is None or secs < 0:
        return "--:--"
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60:02d}m {secs % 60:02d}s"
    if secs < 86400:
        return f"{secs // 3600}h {(secs % 3600) // 60}m"
    return f"{secs // 86400}d {(secs % 86400) // 3600}h"

def _now_ts() -> float:
    return _t.monotonic()

def fmt_eta(done: int, total: int, start_ts: float) -> str:
    if done <= 0 or total <= 0 or start_ts <= 0:
        return "--"
    elapsed = max(0.1, _now_ts() - start_ts)
    rate = done / elapsed
    if rate <= 0:
        return "--"
    remaining = max(0, (total - done) / rate)
    return fmt_duration(remaining)

def sparkline(values, width: int = 12) -> str:
    vals = [v for v in (values or []) if v is not None]
    if not vals:
        return "—"
    vals = vals[-width:]
    vmin, vmax = min(vals), max(vals)
    if vmax == vmin:
        return _SPARK_BLOCKS[3] * len(vals)
    span = vmax - vmin
    out = []
    for v in vals:
        idx = int((v - vmin) / span * (len(_SPARK_BLOCKS) - 1))
        out.append(_SPARK_BLOCKS[idx])
    return "".join(out)

def section_box(title: str, rows: list, icon: str = "", width: int = 36) -> str:
    sep = "━" * width
    out = [sep]
    header = f"{icon}  *{title}*" if icon else f"*{title}*"
    out.append(header)
    out.append(sep)
    for k, v in rows:
        dot_count = max(1, width - len(str(k)) - len(str(v)) - 4)
        out.append(f"  {k} {'.' * dot_count} {v}")
    out.append(sep)
    return "\n".join(out)

def render_banner() -> str:
    return (
        "```\n"
        "╔═══════════════════════════════════╗\n"
        "║    ⚡  T E L E K U   B O T  ⚡    ║\n"
        "║      Multi-Account Automation     ║\n"
        "╚═══════════════════════════════════╝\n"
        "```"
    )

# LiveMessage - sticky message dengan throttled edit
class LiveMessage:
    MIN_INTERVAL = 1.2

    def __init__(self, bot, chat_id, message_id, parse_mode="Markdown"):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.parse_mode = parse_mode
        self._pending_text = None
        self._pending_kb = None
        self._last_sent_text = None
        self._last_edit_ts = 0.0
        self._flush_task: asyncio.Task | None = None
        self._spinner_task: asyncio.Task | None = None
        self._spinner_idx = 0
        self._closed = False
        self._lock = asyncio.Lock()

    @classmethod
    async def create(cls, bot, chat_id, initial_text="⏳ Initializing...", parse_mode="Markdown", reply_markup=None):
        try:
            msg = await bot.send_message(
                chat_id=chat_id, text=initial_text,
                parse_mode=parse_mode, reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        except Exception:
            msg = await bot.send_message(
                chat_id=chat_id, text=initial_text, reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            parse_mode = None
        lm = cls(bot, chat_id, msg.message_id, parse_mode=parse_mode)
        lm._last_sent_text = initial_text
        return lm

    async def _do_edit(self, text, reply_markup=None):
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=text,
                parse_mode=self.parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            self._last_sent_text = text
            self._last_edit_ts = _now_ts()
        except Exception as e:
            msg = str(e).lower()
            if "not modified" in msg:
                self._last_edit_ts = _now_ts()
                return
            try:
                await self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=self.message_id,
                    text=text,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
                self._last_sent_text = text
                self._last_edit_ts = _now_ts()
            except Exception:
                pass

    async def update(self, text, reply_markup=None, force: bool = False):
        if self._closed:
            return
        async with self._lock:
            self._pending_text = text
            if reply_markup is not None:
                self._pending_kb = reply_markup
            now = _now_ts()
            elapsed = now - self._last_edit_ts
            if force or elapsed >= self.MIN_INTERVAL:
                if self._pending_text != self._last_sent_text:
                    await self._do_edit(self._pending_text, self._pending_kb)
                self._pending_text = None
                return
            if self._flush_task is None or self._flush_task.done():
                self._flush_task = asyncio.create_task(
                    self._delayed_flush(self.MIN_INTERVAL - elapsed)
                )

    async def _delayed_flush(self, delay: float):
        await asyncio.sleep(max(0, delay))
        async with self._lock:
            if self._pending_text and self._pending_text != self._last_sent_text:
                await self._do_edit(self._pending_text, self._pending_kb)
            self._pending_text = None

    async def finalize(self, final_text: str, reply_markup=None):
        """Kirim update terakhir (force, ignore throttle) lalu tutup."""
        if self._closed:
            return
        self._closed = True
        try:
            async with self._lock:
                if self._flush_task and not self._flush_task.done():
                    self._flush_task.cancel()
                await self._do_edit(final_text, reply_markup)
        except Exception:
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id, text=final_text,
                    reply_markup=reply_markup, parse_mode=self.parse_mode,
                    disable_web_page_preview=True,
                )
            except Exception:
                pass

    async def close(self):
        self._closed = True
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()


# ======================= Helpers text/format =======================

def shorten_text(value, max_len: int = 80):
    text = str(value or "").strip()
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return text[:max_len]
    return text[: max_len - 1] + "…"


def join_lines_truncate(lines, max_chars: int = 3800):
    """Gabungkan list of str ke satu string, potong bila > max_chars."""
    if isinstance(lines, str):
        text = lines
    else:
        text = "\n".join(lines)
    if len(text) <= max_chars:
        return text
    head = text[: max_chars - 40]
    return head + "\n\n(⚠️ Output dipotong…)"


# ======================= Dashboard =======================

def render_live_dashboard(
    title: str,
    icon: str = "",
    target_summary: str = "",
    accounts_count: int = 0,
    done: int = 0,
    total: int = 0,
    sukses: int = 0,
    gagal: int = 0,
    skip: int = 0,
    start_ts: float = 0.0,
    loop_info: str = "",
    current_line: str = "",
    trend_values=None,
) -> str:
    """Render dashboard live untuk kirim/join/automation."""
    elapsed = fmt_duration(_now_ts() - start_ts) if start_ts else "--"
    eta = fmt_eta(done, total, start_ts)
    lines = []
    header = f"{icon}  *{title}*" if icon else f"*{title}*"
    lines.append(header)
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    if target_summary:
        lines.append(f"{ICON['target']} Target : {target_summary}")
    if accounts_count:
        lines.append(f"{ICON['users']} Akun   : *{accounts_count}*")
    if loop_info:
        lines.append(f"{ICON['loop']} Loop   : {loop_info}")
    lines.append("")
    lines.append(f"📈 {pbar(done, total)}")
    lines.append("")
    lines.append(f"✅ Sukses : *{sukses}*    ❌ Gagal : *{gagal}*    ⏭ Skip : *{skip}*")
    lines.append(f"⏱ Elapsed : *{elapsed}*    ⏳ ETA : *{eta}*")
    if trend_values:
        lines.append(f"📊 Trend  : `{sparkline(trend_values)}`")
    if current_line:
        lines.append("")
        lines.append(current_line)
    return "\n".join(lines)


# ======================= Runtime Control (Pause/Resume/Stop) =======================
# Registry: run_id -> {kind, cancel_event, pause_event, owner_user_id}
_runtime_registry: dict = {}


def register_runtime_control(kind: str, run_id: str, cancel_event, pause_event, owner_user_id: int):
    _runtime_registry[run_id] = {
        "kind": kind,
        "cancel_event": cancel_event,
        "pause_event": pause_event,
        "owner_user_id": owner_user_id,
    }


def unregister_runtime_control(kind: str, run_id: str):
    _runtime_registry.pop(run_id, None)


def build_runtime_inline_keyboard(run_id: str, kind: str = "kirim", paused: bool = False):
    """Inline keyboard Pause/Resume + Stop untuk proses live."""
    if paused:
        toggle_label = f"{ICON['play']} Resume"
        toggle_cb = f"rt:resume:{kind}:{run_id}"
    else:
        toggle_label = f"{ICON['pause']} Pause"
        toggle_cb = f"rt:pause:{kind}:{run_id}"
    stop_cb = f"rt:stop:{kind}:{run_id}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(toggle_label, callback_data=toggle_cb),
        InlineKeyboardButton(f"{ICON['stopped']} Stop", callback_data=stop_cb),
    ]])


async def bot_runtime_callback(update, context):
    """Handler tombol Pause/Resume/Stop di dashboard live."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    data = query.data or ""
    # Format: rt:action:kind:run_id
    parts = data.split(":", 3)
    if len(parts) < 4:
        return
    _, action, kind, run_id = parts
    entry = _runtime_registry.get(run_id)
    if not entry:
        try:
            await query.answer("⚠️ Proses sudah selesai/hilang.", show_alert=False)
        except Exception:
            pass
        return
    if entry.get("owner_user_id") and update.effective_user.id != entry["owner_user_id"]:
        try:
            await query.answer("⛔️ Bukan milik Anda.", show_alert=True)
        except Exception:
            pass
        return
    cancel_event = entry.get("cancel_event")
    pause_event = entry.get("pause_event")
    if action == "pause" and pause_event is not None:
        pause_event.set()
        try:
            await query.answer("⏸ Pause diaktifkan.")
        except Exception:
            pass
    elif action == "resume" and pause_event is not None:
        pause_event.clear()
        try:
            await query.answer("▶️ Resume, proses dilanjutkan.")
        except Exception:
            pass
    elif action == "stop" and cancel_event is not None:
        cancel_event.set()
        if pause_event is not None:
            pause_event.clear()
        try:
            await query.answer("⏹ Stop dikirim, tunggu batch selesai.")
        except Exception:
            pass


# ======================= Toast notification =======================

async def send_toast(bot, chat_id, text: str, duration: int = 6):
    """Kirim pesan singkat lalu hapus setelah `duration` detik (best-effort)."""
    try:
        msg = await bot.send_message(chat_id=chat_id, text=text, disable_notification=True, parse_mode="Markdown")
    except Exception:
        try:
            msg = await bot.send_message(chat_id=chat_id, text=text, disable_notification=True)
        except Exception:
            return

    async def _delete_later():
        await asyncio.sleep(max(1, duration))
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
        except Exception:
            pass

    try:
        asyncio.create_task(_delete_later())
    except Exception:
        pass

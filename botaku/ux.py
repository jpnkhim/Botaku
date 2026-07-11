"""
botaku.ux - UX Infrastructure: icons, pbar, LiveMessage, dashboard
"""
from __future__ import annotations
import asyncio
import time as _t

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

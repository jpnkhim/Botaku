"""
botaku.telegram_client - Telethon client helpers + safe wrappers
Fix CRITICAL-01 (sync vs async) dan CRITICAL-03 (private API)
"""
from __future__ import annotations
import asyncio
import logging
import random
from .config import TELEGRAM_CONNECT_TIMEOUT, TELEGRAM_DISCONNECT_TIMEOUT, TELEGRAM_OP_TIMEOUT, SKIP_STATUSES

logger = logging.getLogger("telekubot")

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.errors import (
        SessionPasswordNeededError,
        PhoneCodeInvalidError,
        PhoneCodeExpiredError,
        PhoneNumberInvalidError,
        FloodWaitError,
        UserBannedInChannelError,
        ChatWriteForbiddenError,
        UserDeactivatedBanError,
        AuthKeyUnregisteredError,
        PeerFloodError,
        ChannelPrivateError,
        ChatAdminRequiredError,
        InputUserDeactivatedError,
        UserAlreadyParticipantError,
        InviteHashInvalidError,
        InviteHashExpiredError,
        InviteRequestSentError,
        ChannelsTooMuchError,
    )
except ImportError:
    TelegramClient = None
    StringSession = None
    FloodWaitError = Exception

TELEGRAM_CLIENT_SEMAPHORE = asyncio.Semaphore(5)

def get_telegram_client(session_obj, api_id, api_hash, **kwargs):
    if TelegramClient is None:
        raise RuntimeError("telethon not installed")
    try:
        api_id_int = int(str(api_id).strip())
    except (ValueError, TypeError):
        raise ValueError(f"API ID tidak valid: '{api_id}'")
    api_hash_str = str(api_hash).strip()
    if isinstance(session_obj, str):
        session_obj = StringSession(session_obj)
    elif session_obj is None:
        session_obj = StringSession()
    return TelegramClient(session_obj, api_id_int, api_hash_str, **kwargs)

async def safe_telegram_operation(coro, timeout=TELEGRAM_OP_TIMEOUT):
    return await asyncio.wait_for(coro, timeout=timeout)

async def safe_disconnect(client, timeout=TELEGRAM_DISCONNECT_TIMEOUT):
    if client is None:
        return
    try:
        await asyncio.wait_for(client.disconnect(), timeout=timeout)
    except (asyncio.TimeoutError, Exception):
        try:
            if hasattr(client, 'session'):
                try:
                    client.session.close()
                except Exception:
                    pass
        except Exception:
            pass

async def safe_connect_and_check(client, timeout=TELEGRAM_CONNECT_TIMEOUT):
    try:
        await asyncio.wait_for(client.connect(), timeout=timeout)
        authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=timeout)
        if not authorized:
            return False, "Session tidak valid atau sudah expired"
        return True, None
    except asyncio.TimeoutError:
        return False, "TIMEOUT saat connect (akun mungkin diblokir)"
    except (ConnectionError, OSError) as e:
        return False, f"CONNECTION_ERROR: {e}"
    except Exception as e:
        is_restricted, status, alasan = is_account_restricted_error(e)
        if is_restricted:
            return False, f"{status.upper()}: {alasan}"
        return False, str(e)

def is_account_restricted_error(error):
    err_str = str(error).upper()
    if isinstance(error, FloodWaitError):
        wait_seconds = getattr(error, 'seconds', 0)
        return True, "flood_wait", f"Rate limited, harus tunggu {wait_seconds} detik"
    banned_keywords = [
        "PHONE_NUMBER_BANNED", "USER_DEACTIVATED", "USER_DEACTIVATED_BAN",
        "AUTH_KEY_UNREGISTERED", "AUTH_KEY_DUPLICATED", "SESSION_REVOKED",
        "SESSION_EXPIRED", "USER_BANNED_IN_CHANNEL", "PEER_FLOOD",
        "USER_RESTRICTED", "CHAT_WRITE_FORBIDDEN",
    ]
    for keyword in banned_keywords:
        if keyword in err_str:
            if "BANNED" in keyword or "DEACTIVATED" in keyword:
                return True, "terblokir", f"Akun terblokir: {keyword}"
            elif "SESSION" in keyword or "AUTH_KEY" in keyword:
                return True, "expired", f"Session bermasalah: {keyword}"
            else:
                return True, "dibatasi", f"Akun dibatasi: {keyword}"
    return False, "", ""

async def handle_flood_wait(e, nomor: str):
    wait = getattr(e, 'seconds', 0)
    jitter = random.uniform(0.5, 2.0)
    total_wait = wait + jitter
    logger.warning(f"[FLOOD] Akun {nomor} kena FloodWait {wait}s")
    return total_wait

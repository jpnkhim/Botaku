"""
botaku.handlers.kirim - kirim pesan handlers (modular)
"""
from __future__ import annotations
from telegram import Update
from telegram.ext import ContextTypes

STATE_MAIN_MENU = 0

async def bot_kirim_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎯 Target diterima, lanjut pilih akun (modular stub)")
    return STATE_MAIN_MENU

async def bot_kirim_pilih_akun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👤 Pilih akun (modular stub)")
    return STATE_MAIN_MENU

async def bot_kirim_pesan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✉️ Pesan diterima (modular stub)")
    return STATE_MAIN_MENU

async def bot_kirim_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Konfirmasi (modular stub)")
    return STATE_MAIN_MENU

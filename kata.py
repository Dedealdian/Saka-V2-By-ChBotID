import sys
import logging
from datetime import time
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ChatMemberHandler,
    ContextTypes
)
from telegram.constants import ParseMode

# --- IMPORT PONDASI ---
from config import TOKEN, LOG_GROUP_ID, setup_logging
from database import init_db, db_query
from core import load_dictionary, rooms

# --- IMPORT UTILITIES & HANDLERS ---
from utils import error_handler, update_group_link
from utils_game import handle_all

# --- IMPORT PLUGINS ---
from plugins.game import (
    mulai_cmd, gabung_cmd, keluar_cmd, 
    id_cmd, stop_cmd, usir_cmd, ganti_cmd
)
from plugins.economy import top_cmd, spin_cmd, edit_point_cmd
from plugins.admin import broadcast_cmd, stats_cmd, settings_cmd, reset_cmd
from plugins.help import help_command
from plugins.callback import cb_logic

# --- 1. LOGGING SYSTEM (PENGGUNA & GRUP BARU) ---

async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mencatat dan melaporkan ketika bot masuk ke grup baru."""
    res = update.my_chat_member
    if not res: return
    
    if res.new_chat_member.status in ["member", "administrator"]:
        chat = res.chat
        # Simpan ke Database
        db_query(
            "INSERT INTO groups (id, title) VALUES (?, ?) ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title", 
            (chat.id, chat.title), 
            commit=True
        )
        await update_group_link(chat, context)
        
        # Kirim Log ke Grup Log
        log_msg = (f"📥 <b>BOT MASUK GRUP BARU</b>\n"
                   f"━━━━━━━━━━━━━━━━━━━━\n"
                   f"<b>Nama:</b> {chat.title}\n"
                   f"<b>ID:</b> <code>{chat.id}</code>\n"
                   f"<b>Username:</b> @{chat.username if chat.username else '-'}\n"
                   f"<b>Tipe:</b> {chat.type.upper()}")
        try:
            await context.bot.send_message(LOG_GROUP_ID, log_msg, parse_mode=ParseMode.HTML)
            
            # Pesan Sambutan di Grup tersebut
            welcome = (f"👋 <b>Halo Anggota {chat.title}!</b>\n\n"
                       f"Saya adalah Bot Sambung Kata yang akan menemani waktu luang kalian.\n\n"
                       f"• Gunakan /mulai untuk bermain\n"
                       f"• Gunakan /help untuk bantuan\n\n"
                       f"<i>Mohon jadikan saya Admin agar fitur Ranking Grup aktif.</i>")
            await context.bot.send_message(chat.id, welcome, parse_mode=ParseMode.HTML)
        except: pass

async def track_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mencatat pengguna baru yang pertama kali menekan /start."""
    user = update.effective_user
    if not user: return
    
    # Cek apakah user sudah ada di database
    check = db_query("SELECT id FROM users WHERE id = ?", (user.id,), fetchone=True)
    if not check:
        # Simpan user baru
        username = user.username if user.username else "User"
        db_query("INSERT INTO users (id, username) VALUES (?, ?)", (user.id, username), commit=True)
        
        # Kirim Log ke Grup Log
        log_msg = (f"👤 <b>PENGGUNA BARU TERDETEKSI</b>\n"
                   f"━━━━━━━━━━━━━━━━━━━━\n"
                   f"<b>Nama:</b> {user.first_name}\n"
                   f"<b>ID:</b> <code>{user.id}</code>\n"
                   f"<b>Username:</b> @{user.username if user.username else '-'}")
        try:
            await context.bot.send_message(LOG_GROUP_ID, log_msg, parse_mode=ParseMode.HTML)
        except: pass
    
    # Jalankan perintah start yang asli
    from config import START_TEXT
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = [[InlineKeyboardButton("➕ MASUKKAN KE GRUP", url=f"https://t.me/{context.bot.username}?startgroup=start")]]
    await update.message.reply_text(START_TEXT, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# --- 2. SCHEDULER TASKS ---

async def daily_clear_cache(context: ContextTypes.DEFAULT_TYPE):
    """Membersihkan memory setiap malam agar bot tetap ringan."""
    rooms.clear()
    load_dictionary()
    log_text = "🧹 <b>Auto Clear Cache:</b> Berhasil dilakukan (Memory dikosongkan & Kamus dimuat ulang)."
    try: await context.bot.send_message(LOG_GROUP_ID, log_text, parse_mode=ParseMode.HTML)
    except: pass

# --- 3. MAIN RUNNER ---

def main():
    # Inisialisasi Logging ke Terminal
    setup_logging()
    
    # Inisialisasi Database (Create tables & Migration)
    print(">>> Menginisialisasi Database...")
    init_db()

    # Membangun Aplikasi Telegram
    app = Application.builder().token(TOKEN).build()

    # --- PENDAFTARAN HANDLER ---

    # Perintah Dasar & Tracking
    app.add_handler(CommandHandler("start", track_users))
    app.add_handler(CommandHandler("help", help_command))

    # Perintah Game (Modular)
    app.add_handler(CommandHandler("mulai", mulai_cmd))
    app.add_handler(CommandHandler("gabung", gabung_cmd))
    app.add_handler(CommandHandler("keluar", keluar_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("usir", usir_cmd))
    app.add_handler(CommandHandler("ganti", ganti_cmd))

    # Perintah Ekonomi & Admin
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("spin", spin_cmd))
    app.add_handler(CommandHandler("e", edit_point_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler(["bcuser", "bcgroup"], broadcast_cmd))

    # Handler Callback (Tombol)
    app.add_handler(CallbackQueryHandler(cb_logic))

    # Handler Pesan (Jawaban Game & Filter Teks)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all))
    
    # Handler Deteksi Grup Baru
    app.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))

    # Error Handler Global
    app.add_error_handler(error_handler)

    # --- PENGATURAN JADWAL (JOB QUEUE) ---
    if app.job_queue:
        # Bersihkan cache otomatis setiap jam 00:00 malam
        app.job_queue.run_daily(daily_clear_cache, time=time(hour=0, minute=0, second=0))

    # --- START BOT ---
    print(">>> BOT SAMBUNG KATA MODULAR ONLINE (24/7 PM2 READY) <<<")
    
    # drop_pending_updates=True sangat penting agar saat bot restart,
    # bot tidak banjir pesan lama yang menumpuk.
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

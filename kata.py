import sys
import logging
import asyncio
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
from telegram.constants import ParseMode, ChatType

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

# --- 1. SYSTEM LOG HANDLER (PENGALIH KE TELEGRAM) ---

class TelegramLogHandler(logging.Handler):
    """Memindahkan log dari VPS ke Telegram agar VPS dingin dan hemat resource."""
    def __init__(self, application: Application, chat_id: int):
        super().__init__()
        self.application = application
        self.chat_id = chat_id

    def emit(self, record):
        # Abaikan log internal library agar tidak loop/spam
        if record.name.startswith(('telegram', 'httpx', 'apscheduler')):
            return
        
        if not self.application.bot: return
        log_entry = self.format(record)
        
        try:
            # Kirim log secara asinkron (Mendukung HTML dari logging.info)
            loop = asyncio.get_running_loop()
            loop.create_task(self.send_log(log_entry))
        except RuntimeError:
            pass

    async def send_log(self, message):
        try:
            # Kirim pesan log apa adanya (formatting diatur di pengirimnya)
            await self.application.bot.send_message(
                self.chat_id, 
                message, 
                parse_mode=ParseMode.HTML
            )
        except:
            pass

# --- 2. TRACKING FUNCTIONS ---

async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = update.my_chat_member
    if not res or not res.new_chat_member: return
    if res.new_chat_member.status in ["member", "administrator"]:
        chat = res.chat
        db_query("INSERT INTO groups (id, title) VALUES (?, ?) ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title", (chat.id, chat.title), commit=True)
        await update_group_link(chat, context)
        # Log masuk grup (Bold sebelum titik dua)
        logging.info(f"<b>📥 Bot Masuk Grup</b>: {chat.title} (<code>{chat.id}</code>)")

async def track_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user: return
    
    check = db_query("SELECT id FROM users WHERE id = ?", (user.id,), fetchone=True)
    if not check:
        db_query("INSERT INTO users (id, username) VALUES (?, ?)", (user.id, user.username or "User"), commit=True)
        # Log user baru (Bold sebelum titik dua)
        logging.info(f"<b>👤 User Baru</b>: {user.first_name} (<code>{user.id}</code>)")
    
    if chat.type == ChatType.PRIVATE:
        from config import START_TEXT
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = [[InlineKeyboardButton("➕ MASUKKAN KE GRUP", url=f"https://t.me/{context.bot.username}?startgroup=start")]]
        try: await update.message.reply_text(START_TEXT, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        except: pass

async def daily_maintenance(context: ContextTypes.DEFAULT_TYPE):
    """Pembersihan rutin setiap malam."""
    rooms.clear()
    total = load_dictionary()
    logging.info(f"<b>🧹 Maintenance</b>: Kamus dimuat ulang ({total} kata).")

# --- 3. MAIN RUNNER ---

def main():
    # --- PENGATURAN LOGGING (SENYAPKAN TERMINAL VPS) ---
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Hapus output terminal bawaan agar tidak spam di VPS
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Tambahkan pencatat terminal HANYA untuk ERROR agar VPS tetap senyap
    vps_handler = logging.StreamHandler(sys.stdout)
    vps_handler.setLevel(logging.ERROR)
    root_logger.addHandler(vps_handler)

    # Membangun Aplikasi
    app = Application.builder().token(TOKEN).build()

    # PASANG PIPA LOG KE TELEGRAM UNTUK INFO+
    tg_handler = TelegramLogHandler(app, LOG_GROUP_ID)
    tg_handler.setLevel(logging.INFO)
    root_logger.addHandler(tg_handler)

    # Senyapkan library internal agar tidak mengganggu logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    # Inisialisasi Database & Dictionary
    init_db()
    load_dictionary()

    # --- PENDAFTARAN HANDLER (100% UTUH) ---
    app.add_handler(CommandHandler("start", track_users))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("mulai", mulai_cmd))
    app.add_handler(CommandHandler("gabung", gabung_cmd))
    app.add_handler(CommandHandler("keluar", keluar_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("usir", usir_cmd))
    app.add_handler(CommandHandler("ganti", ganti_cmd))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("spin", spin_cmd))
    app.add_handler(CommandHandler("e", edit_point_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler(["bcuser", "bcgroup"], broadcast_cmd))
    
    app.add_handler(CallbackQueryHandler(cb_logic))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all))
    app.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))

    # Error Handler Global
    app.add_error_handler(error_handler)

    # Maintenance Harian (00:00)
    if app.job_queue:
        app.job_queue.run_daily(daily_maintenance, time=time(hour=0, minute=0, second=0))

    # Output terminal terakhir sebagai penanda bot jalan
    print(">>> BOT RUNNING (VPS SILENT MODE) <<<")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

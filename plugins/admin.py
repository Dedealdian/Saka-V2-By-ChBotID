import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import RetryAfter, Forbidden, BadRequest

from config import OWNER_ID, LOG_GROUP_ID
from database import db_query, get_setting, set_setting

# --- BACKGROUND BROADCAST TASK ---

async def run_safe_broadcast(context, admin_id, target_ids, message, is_group=False):
    """Fungsi internal untuk mengirim pesan secara aman di layar belakang."""
    success = 0
    fail = 0
    total = len(target_ids)
    
    # Kirim notifikasi awal ke admin
    status_msg = await context.bot.send_message(
        chat_id=admin_id,
        text=f"🚀 <b>Memulai Broadcast...</b>\nTarget: {total} {'Grup' if is_group else 'User'}"
    )

    for i, target in enumerate(target_ids):
        t_id = target[0] # Ambil ID dari hasil fetchall database
        try:
            # Menggunakan copy_message agar format (caption, button, dll) tetap sama
            await context.bot.copy_message(
                chat_id=t_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id
            )
            success += 1
        except RetryAfter as e:
            # Jika terkena limit Telegram, tunggu sesuai instruksi server
            await asyncio.sleep(e.retry_after)
            await context.bot.copy_message(chat_id=t_id, from_chat_id=message.chat_id, message_id=message.message_id)
            success += 1
        except (Forbidden, BadRequest):
            # User memblokir bot atau grup sudah dihapus
            fail += 1
        except Exception:
            fail += 1

        # Jeda aman (0.05 detik = ~20 pesan per detik) agar tidak dianggap spam
        await asyncio.sleep(0.05)

        # Update status setiap 50 pesan agar admin tahu progresnya
        if (i + 1) % 50 == 0:
            try:
                await status_msg.edit_text(
                    f"🚀 <b>Broadcast Berjalan...</b>\n"
                    f"Progres: {i+1}/{total}\n"
                    f"✅ Sukses: {success}\n"
                    f"🔴 Gagal: {fail}"
                )
            except: pass

    # Laporan Akhir
    await context.bot.send_message(
        chat_id=admin_id,
        text=(f"✅ <b>Broadcast Selesai!</b>\n\n"
              f"Tipe: {'Grup' if is_group else 'User'}\n"
              f"🟢 Sukses: {success}\n"
              f"🔴 Gagal: {fail}\n"
              f"📊 Total: {total}"),
        parse_mode=ParseMode.HTML
    )

# --- COMMAND HANDLERS ---

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler perintah /bcuser dan /bcgroup."""
    u = update.effective_user
    if u.id != OWNER_ID: return

    # Cek apakah admin me-reply pesan yang ingin di-broadcast
    if not update.effective_message.reply_to_message:
        return await update.message.reply_text("❌ Balas (reply) ke sebuah pesan untuk melakukan broadcast!")

    cmd = update.effective_message.text
    is_group = "bcgroup" in cmd
    
    # Ambil target dari database
    table = "groups" if is_group else "users"
    targets = db_query(f"SELECT id FROM {table}", fetchall=True)

    if not targets:
        return await update.message.reply_text("❌ Tidak ada target di database.")

    # Jalankan broadcast di layar belakang (Background Task)
    asyncio.create_task(
        run_safe_broadcast(
            context, 
            u.id, 
            targets, 
            update.effective_message.reply_to_message, 
            is_group
        )
    )
    
    await update.message.reply_text(f"⏳ Sedang memproses broadcast ke {len(targets)} target...")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cek statistik jumlah user dan grup."""
    if update.effective_user.id != OWNER_ID: return
    
    u_count = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    g_count = db_query("SELECT COUNT(*) FROM groups", fetchone=True)[0]
    
    txt = (f"📊 <b>STATISTIK BOT</b>\n\n"
           f"👤 <b>Total User:</b> {u_count}\n"
           f"🏢 <b>Total Grup:</b> {g_count}")
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML)

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Panel pengaturan Force Subscribe (Fsub)."""
    if update.effective_user.id != OWNER_ID: return
    
    status = get_setting('fsub_status')
    btn_toggle = "🟢 AKTIF" if status == "on" else "🔴 MATI"
    
    kb = [
        [InlineKeyboardButton(f"Fsub Status: {btn_toggle}", callback_data="set_toggle")],
        [InlineKeyboardButton("🆔 Set Channel ID", callback_data="set_id"), InlineKeyboardButton("🔗 Set Link", callback_data="set_link")],
        [InlineKeyboardButton("📝 Set Pesan", callback_data="set_msg"), InlineKeyboardButton("🏷️ Set Tombol", callback_data="set_btn")],
        [InlineKeyboardButton("❌ Tutup", callback_data="set_close")]
    ]
    
    await update.message.reply_text(
        "⚙️ <b>FSUB SETTINGS PANEL</b>\n\nSilakan pilih menu di bawah untuk mengatur kewajiban join channel.",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML
    )

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset poin global (Hati-hati!)."""
    if update.effective_user.id != OWNER_ID: return
    
    kb = [[InlineKeyboardButton("✅ YA, RESET SEMUA", callback_data="reset_acc"), 
           InlineKeyboardButton("❌ BATAL", callback_data="set_close")]]
    
    await update.message.reply_text(
        "⚠️ <b>PERINGATAN!</b>\n\nApakah Anda yakin ingin me-reset SEMUA poin pemain menjadi 0?",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML
    )

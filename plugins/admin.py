import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes
from telegram.error import RetryAfter, Forbidden, BadRequest

from config import OWNER_ID
from database import db_query, get_setting, set_setting

# --- WORKER BROADCAST (BACKGROUND TASK) ---
async def run_safe_broadcast(context, admin_id, target_ids, message, is_group=False):
    """Pengirim pesan massal yang berjalan di background dengan delay aman."""
    success = 0
    fail = 0
    total = len(target_ids)
    label = "Grup" if is_group else "User"
    
    # Notifikasi awal ke admin
    status_msg = await context.bot.send_message(
        chat_id=admin_id,
        text=f"🚀 <b>BROADCAST DIMULAI</b>\nTarget: {total:,} {label}\nStatus: Memproses..."
    )

    for i, target in enumerate(target_ids):
        t_id = target[0]
        try:
            # Jika broadcast grup, pastikan target bukan channel
            if is_group:
                try:
                    chat_info = await context.bot.get_chat(t_id)
                    if chat_info.type == ChatType.CHANNEL:
                        fail += 1
                        continue
                except: pass

            # Menggunakan copy_message (mendukung teks, foto, video, stiker, dll)
            await context.bot.copy_message(
                chat_id=t_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id
            )
            success += 1
            
        except RetryAfter as e:
            # Flood control: Tunggu sesuai instruksi Telegram
            await asyncio.sleep(e.retry_after)
            await context.bot.copy_message(chat_id=t_id, from_chat_id=message.chat_id, message_id=message.message_id)
            success += 1
        except (Forbidden, BadRequest):
            fail += 1
        except Exception:
            fail += 1

        # JEDA AMAN (0.05 detik = ~20 pesan per detik)
        await asyncio.sleep(0.05)

        # Update status pesan admin setiap 100 pesan
        if (i + 1) % 100 == 0:
            try:
                await status_msg.edit_text(
                    f"🚀 <b>BROADCAST SEDANG BERJALAN</b>\n"
                    f"Target: {total:,} {label}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ Sukses: {success:,}\n"
                    f"🔴 Gagal: {fail:,}\n"
                    f"⌛ Progres: {i+1:,}/{total:,}",
                    parse_mode=ParseMode.HTML
                )
            except: pass

    # Laporan Akhir setelah selesai
    await context.bot.send_message(
        chat_id=admin_id,
        text=(f"✅ <b>BROADCAST SELESAI</b>\n\n"
              f"📊 <b>Hasil Akhir {label}:</b>\n"
              f"🟢 Sukses: {success:,}\n"
              f"🔴 Gagal: {fail:,}\n"
              f"🏁 Total Target: {total:,}"),
        parse_mode=ParseMode.HTML
    )

# --- COMMAND HANDLERS ---

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Panel pengaturan Force Subscribe (Fsub)."""
    u = update.effective_user
    if u.id != OWNER_ID: return
    
    status = get_setting('fsub_status')
    btn_toggle = "🟢 AKTIF" if status == "on" else "🔴 MATI"
    
    kb = [
        [InlineKeyboardButton(f"Fsub Status: {btn_toggle}", callback_data="set_toggle")],
        [InlineKeyboardButton("🆔 Set ID", callback_data="set_id"), InlineKeyboardButton("🔗 Set Link", callback_data="set_link")],
        [InlineKeyboardButton("📝 Set Pesan", callback_data="set_msg"), InlineKeyboardButton("🏷️ Set Tombol", callback_data="set_btn")],
        [InlineKeyboardButton("❌ Tutup", callback_data="set_close")]
    ]
    
    text = "⚙️ <b>FSUB SETTINGS PANEL</b>\n\nSilakan pilih menu di bawah untuk mengkonfigurasi kewajiban join channel bagi seluruh pemain."
    
    # Deteksi apakah dipanggil via ketikan (/settings) atau via tombol (callback)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else:
        await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler perintah /bcuser dan /bcgroup (PM2 24/7 Ready)."""
    u = update.effective_user
    if u.id != OWNER_ID: return

    # Pastikan admin membalas ke pesan yang ingin disebar
    if not update.effective_message.reply_to_message:
        return await update.effective_message.reply_text("❌ <b>Gagal:</b> Balas (reply) ke pesan yang ingin di-broadcast!")

    cmd = update.effective_message.text
    is_group = "bcgroup" in cmd
    
    # Ambil data dari tabel yang sesuai
    table = "groups" if is_group else "users"
    targets = db_query(f"SELECT id FROM {table}", fetchall=True)

    if not targets:
        return await update.effective_message.reply_text("❌ Database kosong, tidak ada target ditemukan.")

    # Jalankan proses pengiriman di layar belakang menggunakan asyncio.create_task
    asyncio.create_task(
        run_safe_broadcast(
            context, 
            u.id, 
            targets, 
            update.effective_message.reply_to_message, 
            is_group
        )
    )
    
    target_name = "Grup" if is_group else "User"
    await update.effective_message.reply_text(f"⏳ Mengirim broadcast ke {len(targets):,} {target_name} di layar belakang...")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cek statistik database."""
    if update.effective_user.id != OWNER_ID: return
    
    u_count = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    g_count = db_query("SELECT COUNT(*) FROM groups", fetchone=True)[0]
    
    txt = (f"📊 <b>STATISTIK BOT SAKA</b>\n\n"
           f"👤 <b>Total User:</b> {u_count:,}\n"
           f"🏢 <b>Total Grup:</b> {g_count:,}")
    await update.effective_message.reply_text(txt, parse_mode=ParseMode.HTML)

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Perintah untuk reset poin global (Hati-hati)."""
    if update.effective_user.id != OWNER_ID: return
    
    kb = [[InlineKeyboardButton("✅ YA, RESET SEMUA", callback_data="reset_acc"), 
           InlineKeyboardButton("❌ BATAL", callback_data="set_close")]]
    
    await update.effective_message.reply_text(
        "⚠️ <b>KONFIRMASI RESET POIN</b>\n\nApakah Anda yakin ingin me-reset poin seluruh pemain menjadi 0?\nTindakan ini tidak dapat dibatalkan.",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.HTML
    )

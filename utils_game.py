import re
import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import OWNER_ID, BANNED_NAMES, TIMEOUT_GAME
from database import db_query, set_setting
from core import (
    rooms, dictionary, valid_prefixes, 
    get_level_info, update_points
)

async def timeout_handler(context: ContextTypes.DEFAULT_TYPE):
    """Menangani pemain yang tidak menjawab dalam batas waktu 45 detik."""
    from utils import broadcast_to_room, next_turn_msg, finish_game
    
    host_cid = context.job.chat_id
    if host_cid in rooms and rooms[host_cid]['active']:
        room = rooms[host_cid]
        if not room['players']: 
            return await finish_game(context, host_cid)

        room['turn'] %= (len(room['players']) or 1)
        p_id = room['players'][room['turn']]
        p_name = room['player_names'].get(p_id, "Pemain")

        # Catat pemain ke all_names agar tetap muncul di tabel akhir meskipun AFK
        room['all_names'][p_id] = p_name

        # Tambah hitungan timeout (AFK)
        room['timeout_count'][p_id] = room['timeout_count'].get(p_id, 0) + 1

        if room['timeout_count'][p_id] >= 3:
            msg = f"💀 <a href='tg://user?id={p_id}'>{p_name}</a> Telah Gugur\n✍️ Alasan: Tidak menjawab selama 3×"
            await broadcast_to_room(context, room, msg)

            room['players'].pop(room['turn'])
            if (len(room['players']) or 1) < 2: 
                return await finish_game(context, host_cid)
            room['turn'] %= (len(room['players']) or 1)
        else:
            msg = f"⏰ <b>Waktu Habis!</b>\n<a href='tg://user?id={p_id}'>{p_name}</a> dilewati karena tidak menjawab!"
            await broadcast_to_room(context, room, msg)
            room['turn'] = (room['turn'] + 1) % (len(room['players']) or 1)

        await next_turn_msg(context, host_cid)

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pusat untuk memproses input teks (Settings, Withdraw, dan Jawaban Game)."""
    from utils import broadcast_to_room, next_turn_msg, finish_game, update_group_link
    
    msg_obj = update.effective_message
    if not msg_obj or not msg_obj.text: return
    
    u = update.effective_user
    if not u: return
    cid = update.effective_chat.id

    # --- 1. LOGIKA MENYIMPAN SETTING FSUB (KHUSUS OWNER) ---
    if 'editing_setting' in context.user_data and u.id == OWNER_ID:
        setting_key = context.user_data['editing_setting']
        new_val = msg_obj.text
        
        set_setting(setting_key, new_val)
        context.user_data.pop('editing_setting')
        
        kb = [[InlineKeyboardButton("🔙 Kembali ke Settings", callback_data="back_to_settings")]]
        return await msg_obj.reply_text(
            f"✅ Berhasil memperbarui data <b>{setting_key}</b>",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.HTML
        )

    # --- 2. LOGIKA PROSES WITHDRAW SALDO ---
    if context.user_data.get('state') == 'wd_input':
        text_input = msg_obj.text
        requested_amount = 0
        # Mencari angka di dalam teks input
        match = re.search(r"Total Withdraw:\D*(\d+[\d\.]*)", text_input, re.IGNORECASE)
        if match:
            raw_amount = match.group(1).replace(".", "").replace(",", "")
            if raw_amount.isdigit(): requested_amount = int(raw_amount)
        
        res = db_query("SELECT balance FROM users WHERE id=%s", (u.id,), fetchone=True)
        current_balance = res[0] if res else 0
        
        if requested_amount < 50000:
            return await msg_obj.reply_text("❌ <b>Gagal:</b> Minimal penarikan saldo adalah Rp50.000!")
        if requested_amount > current_balance:
            return await msg_obj.reply_text(f"❌ <b>Gagal:</b> Saldo Anda tidak cukup (Tersedia: Rp{current_balance:,})")
        
        # Potong Saldo di DB & Kirim Notifikasi ke Admin
        db_query("UPDATE users SET balance = balance - %s WHERE id = %s", (requested_amount, u.id), commit=True)
        report = f"💰 <b>PENGAJUAN WITHDRAW SAKA</b>\nUser: {u.mention_html()}\nID: <code>{u.id}</code>\n\nData:\n{text_input}"
        await context.bot.send_message(OWNER_ID, report, parse_mode=ParseMode.HTML)
        
        context.user_data.pop('state', None)
        return await msg_obj.reply_text("✅ <b>Berhasil!</b> Format pengajuan telah terkirim. Admin akan memproses penarikan Anda segera.")

    # --- 3. LOGIKA PERMAINAN SAMBUNG KATA (ENGINE UTAMA) ---
    # Mencari room aktif di mana user terlibat sebagai pemain
    host_cid = next((c for c, r in rooms.items() if r.get('active') and u.id in r.get('players', [])), None)
    if not host_cid: return

    room = rooms[host_cid]
    room['turn'] %= (len(room['players']) or 1)

    # Validasi: Pastikan memang giliran user ini
    if u.id != room['players'][room['turn']]: return

    # Validasi Group: Wajib reply ke pesan bot
    if update.effective_chat.type in ["group", "supergroup"]:
        if not msg_obj.reply_to_message or msg_obj.reply_to_message.from_user.id != context.bot.id: 
            return

    # Sanitasi Kata: Hanya ambil huruf a-z
    raw_word = msg_obj.text.strip().lower()
    word = re.sub(r'[^a-z]', '', raw_word)
    if not word: return

    tc = room['turn_count']
    lvl_name, min_l, lvl_emo = get_level_info(tc + 1)

    # --- PROSES VALIDASI KATA ---
    reason = ""
    if word in room['used_words'] and datetime.now() < room['used_words'][word]:
        reason = "Kata sudah pernah digunakan sebelumnya dalam sesi ini."
    elif word in BANNED_NAMES:
        reason = "Kata dilarang (Terdeteksi Nama Orang/Manusia)."
    elif room['suffix'] and not word.startswith(room['suffix']):
        reason = f"Awalan huruf salah (Harus diawali: <b>{room['suffix'].upper()}</b>)."
    elif len(word) < min_l:
        reason = f"Jumlah huruf kurang (Level ini minimal {min_l} huruf)."
    elif word not in dictionary:
        reason = "Kata tidak ditemukan dalam Kamus Besar Bahasa Indonesia (KBBI)."

    # --- JAWABAN SALAH ---
    if reason:
        # Rekam interaksi ke all_names agar muncul di tabel skor
        room['all_names'][u.id] = u.first_name
        
        is_solo = str(room.get('room_id', '')).startswith("SK-")
        penalty = -1 if is_solo else -5
        
        # Update poin global (DB) dan memori lokal room
        update_points(u.id, u.first_name, penalty, tc)
        room['mistakes'][u.id] = room['mistakes'].get(u.id, 0) + 1

        if room['mistakes'][u.id] >= 3:
            msg = f"💀 <a href='tg://user?id={u.id}'>{u.first_name}</a> Gugur\n✍️ Alasan: Salah menjawab 3× berturut-turut"
            await broadcast_to_room(context, room, msg)
            room['players'].pop(room['turn'])
            if len(room['players']) < 2: 
                return await finish_game(context, host_cid)
        else:
            # Lewati giliran
            room['turn'] = (room['turn'] + 1) % (len(room['players']) or 1)
            msg = (f"❌ Jawaban <a href='tg://user?id={u.id}'>{u.first_name}</a> Salah❗({penalty})\n"
                   f"✍️ Alasan: {reason}\n\n"
                   f"📛 Lanjutkan dari kata: <b>{room['suffix'].upper()}</b>")
            await broadcast_to_room(context, room, msg)

        await next_turn_msg(context, host_cid)
        return

    # --- JAWABAN BENAR ---
    # Rekam interaksi secara permanen
    room['all_names'][u.id] = u.first_name
    room['corrects'][u.id] = room['corrects'].get(u.id, 0) + 1
    
    # Blokir kata agar tidak dipakai selama 30 menit
    room['used_words'][word] = datetime.now() + timedelta(minutes=30)
    
    # Generate Suffix baru (3 huruf jika kata panjang, 2 jika pendek)
    s_len = 3 if len(word) >= 5 else 2
    room['suffix'] = word[-s_len:]
    room['turn_count'] += 1
    room['turn'] = (room['turn'] + 1) % (len(room['players']) or 1)
    
    # Reward Poin Global
    is_solo = str(room.get('room_id', '')).startswith("SK-")
    reward = 1 if is_solo else 10
    update_points(u.id, u.first_name, reward, room['turn_count'])
    
    # Auto-Update Link Grup (Jika di Grup)
    if update.effective_chat.type in ["group", "supergroup"]:
        asyncio.create_task(update_group_link(update.effective_chat, context))

    # Data untuk tampilan pesan
    sisa_nyawa = "❤️" * (3 - room['mistakes'].get(u.id, 0))
    time_taken = int((datetime.now() - room.get('turn_start_time', datetime.now())).total_seconds())
    promo_text = "\n\n⚡Channel: @ChBotID"

    # Logika Anti-Stuck (Cek apakah suffix baru punya pasangan di kamus)
    playable = room['suffix'] in valid_prefixes

    if not playable:
        # Jika suffix "mati", ganti dengan kata baru secara acak dari kamus
        kata_baru = random.choice(list(dictionary))
        old_suffix = room['suffix']
        room['suffix'] = kata_baru[-(3 if len(kata_baru) >= 5 else 2):]
        
        msg_benar = (f"✅Benar +{reward}\n"
                     f"⏰ Waktu: {time_taken}s\n"
                     f"💀 Nyawa {u.first_name}: {sisa_nyawa}\n\n"
                     f"💡 <b>Akhiran {old_suffix.upper()} Mentok!</b>\n"
                     f"🗯️ Kata Ganti Otomatis: {kata_baru.upper()}" + promo_text)
    else:
        msg_benar = (f"✅Benar +{reward}\n"
                     f"⏰ Waktu: {time_taken}s\n"
                     f"💀 Nyawa {u.first_name}: {sisa_nyawa}" + promo_text)

    await broadcast_to_room(context, room, msg_benar)
    await next_turn_msg(context, host_cid)

import re
import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update, Chat
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import OWNER_ID, BANNED_NAMES, TIMEOUT_GAME
from database import db_query
from core import (
    rooms, dictionary, valid_prefixes, 
    get_level_info, update_points
)

# Catatan: Fungsi-fungsi dari utils.py diimpor di dalam fungsi 
# untuk menghindari Circular Import Error.

async def timeout_handler(context: ContextTypes.DEFAULT_TYPE):
    """Menangani kejadian ketika pemain tidak menjawab tepat waktu."""
    from utils import broadcast_to_room, next_turn_msg, finish_game
    
    host_cid = context.job.chat_id
    if host_cid in rooms and rooms[host_cid]['active']:
        room = rooms[host_cid]
        if not room['players']: 
            return await finish_game(context, host_cid)

        room['turn'] %= (len(room['players']) or 1)
        p_id = room['players'][room['turn']]
        p_name = room['player_names'].get(p_id, "Pemain")

        # Tambah hitungan tidak menjawab (AFK)
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
    """Handler utama untuk memproses jawaban kata atau input teks lainnya (Withdraw/Game)."""
    from utils import (
        broadcast_to_room, next_turn_msg, finish_game, 
        update_group_link
    )
    
    msg_obj = update.effective_message
    if not msg_obj: return
    u = update.effective_user
    if not u: return
    cid = update.effective_chat.id

    # 1. LOGIKA WITHDRAW (Input Saldo)
    if context.user_data.get('state') == 'wd_input':
        text_input = msg_obj.text or ""
        requested_amount = 0
        match = re.search(r"Total Withdraw:\D*(\d+[\d\.]*)", text_input, re.IGNORECASE)
        if match:
            raw_amount = match.group(1).replace(".", "").replace(",", "")
            if raw_amount.isdigit(): requested_amount = int(raw_amount)
        
        res = db_query("SELECT balance FROM users WHERE id=?", (u.id,), fetchone=True)
        current_balance = res[0] if res else 0
        
        if requested_amount < 50000:
            return await context.bot.send_message(chat_id=cid, text="❌ Minimal penarikan Rp50.000!", parse_mode=ParseMode.HTML)
        if requested_amount > current_balance:
            return await context.bot.send_message(chat_id=cid, text="❌ Saldo tidak cukup!", parse_mode=ParseMode.HTML)
        
        db_query("UPDATE users SET balance = balance - ? WHERE id = ?", (requested_amount, u.id), commit=True)
        report = f"💰 <b>PENGAJUAN WITHDRAW</b>\nUser: {u.mention_html()}\nWD_ID: {u.id}\nData:\n{text_input}"
        await context.bot.send_message(OWNER_ID, report, parse_mode=ParseMode.HTML)
        context.user_data.clear()
        return await context.bot.send_message(chat_id=cid, text="✅ Berhasil! Penarikan diajukan.", parse_mode=ParseMode.HTML)

    # 2. LOGIKA PERMAINAN (SAMBUNG KATA)
    # Cari di mana user sedang aktif bermain
    host_cid = next((c for c, r in rooms.items() if r.get('active') and u.id in r.get('players', [])), None)
    if not host_cid: return

    room = rooms[host_cid]
    room['turn'] %= (len(room['players']) or 1)

    # Cek apakah ini giliran user tersebut
    if u.id != room['players'][room['turn']]: 
        return

    # Di grup wajib Reply pesan bot (menghindari bot saling chat)
    if update.effective_chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        if not msg_obj.reply_to_message or msg_obj.reply_to_message.from_user.id != context.bot.id: 
            return

    if not msg_obj.text: return
    
    # Sanitasi Kata: Hanya ambil huruf a-z
    raw_word = msg_obj.text.strip().lower()
    word = re.sub(r'[^a-z]', '', raw_word) 
    if not word: return

    tc = room['turn_count']
    lvl_name, min_l, lvl_emo = get_level_info(tc + 1)

    # --- VALIDASI KATA ---
    reason = ""
    if word in room['used_words'] and datetime.now() < room['used_words'][word]: 
        reason = "Sudah pernah disebutkan"
    elif word in BANNED_NAMES: 
        reason = "Dilarang (Nama Orang/Manusia)"
    elif room['suffix'] and not word.startswith(room['suffix']): 
        reason = f"Awalan huruf tidak sesuai (Bukan {room['suffix'].upper()})"
    elif len(word) < min_l: 
        reason = f"Jumlah huruf kurang (Min {min_l} huruf)"
    elif word not in dictionary: 
        reason = "Kata tidak ditemukan dalam kamus baku"

    # --- PENANGANAN JAWABAN SALAH ---
    if reason:
        is_solo = str(room.get('room_id', '')).startswith("SK-")
        penalty = -1 if is_solo else -5
        update_points(u.id, u.first_name, penalty, tc)
        room['mistakes'][u.id] = room['mistakes'].get(u.id, 0) + 1

        if room['mistakes'][u.id] >= 3:
            msg = f"💀 <a href='tg://user?id={u.id}'>{u.first_name}</a> Gugur\n✍️ Alasan: Salah menjawab 3×"
            await broadcast_to_room(context, room, msg)
            room['players'].pop(room['turn'])
            if len(room['players']) < 2: 
                return await finish_game(context, host_cid)
        else:
            room['turn'] = (room['turn'] + 1) % (len(room['players']) or 1)
            msg = (f"❌ Jawaban <a href='tg://user?id={u.id}'>{u.first_name}</a> Salah ({penalty})\n"
                   f"✍️ Alasan: {reason}\n"
                   f"📛 Lanjutkan dari: <b>{room['suffix'].upper()}</b>")
            await broadcast_to_room(context, room, msg)

        await next_turn_msg(context, host_cid)
        return

    # --- PENANGANAN JAWABAN BENAR ---
    room['used_words'][word] = datetime.now() + timedelta(minutes=30)
    
    # Ambil suffix (akhiran) 2 atau 3 huruf
    s_len = 3 if len(word) >= 5 else 2
    room['suffix'] = word[-s_len:]
    room['turn_count'] += 1
    room['corrects'][u.id] = room['corrects'].get(u.id, 0) + 1
    room['turn'] = (room['turn'] + 1) % (len(room['players']) or 1)
    
    # Reward Poin
    is_solo = str(room.get('room_id', '')).startswith("SK-")
    reward = 1 if is_solo else 10
    update_points(u.id, u.first_name, reward, room['turn_count'])
    
    if update.effective_chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        asyncio.create_task(update_group_link(update.effective_chat, context))

    # Variabel untuk tampilan pesan
    p_name = u.first_name
    sisa_nyawa = "❤️" * (3 - room['mistakes'].get(u.id, 0))
    time_taken = int((datetime.now() - room.get('turn_start_time', datetime.now())).total_seconds())
    promo_text = "\n\n⚡Channel: @ChBotID"

    # Cek apakah akhiran baru "mentok" (tidak ada pasangan kata di kamus)
    playable = room['suffix'] in valid_prefixes

    if not playable:
        # Cari kata baru dari kamus agar game tidak berhenti total
        kata_baru = random.choice(list(dictionary))
        old_suffix = room['suffix']
        room['suffix'] = kata_baru[-(3 if len(kata_baru) >= 5 else 2):]
        
        msg_benar = (f"✅Benar +{reward}\n"
                     f"⏰ Waktu: {time_taken}s\n"
                     f"💀 Nyawa {p_name}: {sisa_nyawa}\n\n"
                     f"💡 <b>Akhiran {old_suffix.upper()} Mentok!</b>\n"
                     f"🗯️ Kata Ganti: {kata_baru.upper()}" + promo_text)
    else:
        msg_benar = (f"✅Benar +{reward}\n"
                     f"⏰ Waktu: {time_taken}s\n"
                     f"💀 Nyawa {p_name}: {sisa_nyawa}" + promo_text)

    await broadcast_to_room(context, room, msg_benar)
    await next_turn_msg(context, host_cid)

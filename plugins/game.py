import random
import importlib
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.ext import ContextTypes

from config import OWNER_ID
from database import db_query
from core import (
    rooms, generate_solo_id, load_dictionary, 
    is_owner, update_points
)
from utils import (
    check_fsub, send_fsub_msg, broadcast_to_room, 
    next_turn_msg, finish_game
)

async def mulai_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk memulai pendaftaran game di grup atau mode Solo di Private Chat."""
    u = update.effective_user
    if not u: return
    uid, cid = u.id, update.effective_chat.id
    
    # --- 1. LOG GABUNGAN (Sesuai Permintaan: Satu Pesan Saja & Estetik) ---
    # Fungsi load_dictionary() di core.py sekarang mengembalikan angka (return len)
    total_kata = load_dictionary() 
    chat_title = update.effective_chat.title if update.effective_chat.type != Chat.PRIVATE else "Private Chat"
    
    # Menggabungkan log menjadi satu pesan agar tidak spam
    log_gabungan = (
        f"<b>👨‍💻System Logs Dev Bot ID</b>:\n\n"
        f"<b>▶️ Game Dimainkan</b>: {total_kata} kata berhasil dimuat.\n"
        f"<b>🎮 Game Dimainkan di</b>: {chat_title}\n"
        f"<b>IDs Group</b>: {cid}"
    )
    # Dikirim ke TelegramLogHandler di kata.py
    logging.info(log_gabungan) 

    # Reload data nama jika tersedia
    try:
        import nama
        importlib.reload(nama)
    except: pass

    # Cek Force Subscribe
    if not await check_fsub(uid, context):
        return await send_fsub_msg(update, context)

    # --- LOGIKA MODE SOLO / CROSS-CHAT (Private Chat) ---
    if update.effective_chat.type == Chat.PRIVATE:
        # Cek apakah user sudah punya room aktif di mana saja
        existing_room = next((r for r in rooms.values() if uid in r.get('players', [])), None)
        if existing_room:
            return await context.bot.send_message(
                chat_id=cid, 
                text=f"❌ Anda sedang berada dalam Room <code>{existing_room['room_id']}</code>!", 
                parse_mode=ParseMode.HTML
            )
        
        room_id = generate_solo_id()
        start_char = random.choice("abcdefghijklmnopqrstuvwxyz")
        
        # Buat room mode Solo
        rooms[uid] = {
            'creator': uid, 
            'players': [uid],
            'player_names': {uid: u.first_name}, 
            'all_names': {uid: u.first_name},
            'player_chats': {uid: cid}, 
            'active': True,
            'suffix': start_char, 
            'turn': 0, 
            'turn_count': 0,
            'used_words': {}, 
            'mistakes': {uid: 0}, 
            'corrects': {uid: 0},
            'timeout_count': {uid: 0}, 
            'ganti_limit': {}, 
            'usir_limit': 1,
            'room_id': room_id, 
            'turn_start_time': datetime.now()
        }
        
        text = (f"🎮 <b>SOLO MODE: AKTIF</b>\n"
                f"📛 Game ID: <code>{room_id}</code>\n\n"
                f"Game ini bisa digabung orang lain via:\n<code>/gabung {room_id}</code>\n\n"
                f"Sambung kata dari: <b>{start_char.upper()}</b>")
        return await context.bot.send_message(chat_id=cid, text=text, parse_mode=ParseMode.HTML)

    # --- LOGIKA MODE GRUP ---
    if cid in rooms:
        return await context.bot.send_message(chat_id=cid, text="❌ Game sudah berjalan di grup ini!", parse_mode=ParseMode.HTML)

    # Generate ID angka untuk grup
    room_id = random.randint(10000, 99999)
    rooms[cid] = {
        'creator': uid, 'players': [uid],
        'player_names': {uid: u.first_name}, 'all_names': {uid: u.first_name},
        'player_chats': {uid: cid}, 'active': False,
        'suffix': '', 'turn': 0, 'turn_count': 0,
        'used_words': {}, 'mistakes': {uid: 0}, 'corrects': {uid: 0},
        'timeout_count': {uid: 0}, 'ganti_limit': {}, 'usir_limit': 1,
        'room_id': room_id, 'turn_start_time': datetime.now()
    }

    leader_mention = f"<a href='tg://user?id={uid}'>{u.first_name}</a>"
    text = (f"<u><b>🎮ROOM DIBUKA</b></u>\n"
            f"📛Game ID: <code>{room_id}</code>\n"
            f"👮‍♂️Leader: {leader_mention}\n\n"
            f"👤Pemain Bersiap:\n1. {u.first_name}")

    kb = [[InlineKeyboardButton("🚪 Gabung", callback_data="join"), InlineKeyboardButton("🏃 Keluar", callback_data="leave")],
          [InlineKeyboardButton("▶️ Play", callback_data="play")]]
    await context.bot.send_message(chat_id=cid, text=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def gabung_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /gabung baik lokal di grup atau lintas chat via ID."""
    u = update.effective_user
    if not u: return
    uid, cid = u.id, update.effective_chat.id
    args = context.args

    # 1. Gabung lintas chat via ID
    if args:
        room_id_str = args[0].upper()
        target_host_cid = next((c for c, r in rooms.items() if str(r.get('room_id')) == room_id_str), None)
        
        if not target_host_cid:
            return await context.bot.send_message(chat_id=cid, text="❌ <b>Room tidak ditemukan atau sudah berakhir!</b>", parse_mode=ParseMode.HTML)

        room = rooms[target_host_cid]
        if uid in room['players']:
            return await context.bot.send_message(chat_id=cid, text="❌ Anda sudah berada di dalam room tersebut!", parse_mode=ParseMode.HTML)

        if not await check_fsub(uid, context): return

        room['players'].append(uid)
        room['player_names'][uid] = u.first_name
        room['all_names'][uid] = u.first_name
        room['mistakes'][uid] = 0
        room['corrects'][uid] = 0
        room['timeout_count'][uid] = 0
        room['player_chats'][uid] = cid

        await context.bot.send_message(chat_id=cid, text=f"✅ <b>Berhasil bergabung ke Game ID: {room_id_str}</b>\nSilakan tunggu giliran Anda!", parse_mode=ParseMode.HTML)
        await broadcast_to_room(context, room, f"✅ <b>{u.first_name}</b> ikut bergabung!")
        return

    # 2. Gabung lokal
    room = rooms.get(cid)
    if not room: 
        return await context.bot.send_message(chat_id=cid, text="❌ Tidak ada pendaftaran aktif di grup ini.", parse_mode=ParseMode.HTML)
    if uid in room['players']: 
        return await context.bot.send_message(chat_id=cid, text="❌ Anda sudah masuk pendaftaran.", parse_mode=ParseMode.HTML)
    
    if not await check_fsub(uid, context): return

    room['players'].append(uid)
    room['player_names'][uid] = u.first_name
    room['all_names'][uid] = u.first_name
    room['mistakes'][uid] = 0
    room['corrects'][uid] = 0
    room['timeout_count'][uid] = 0
    room['player_chats'][uid] = cid
    await broadcast_to_room(context, room, f"✅ <b>{u.first_name}</b> masuk!")

async def keluar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /keluar dari permainan."""
    u = update.effective_user
    if not u: return
    uid, cid = u.id, update.effective_chat.id
    
    host_cid = next((c for c, r in rooms.items() if uid in r.get('players', [])), None)
    
    if not host_cid:
        return await context.bot.send_message(chat_id=cid, text="❌ Anda tidak sedang dalam permainan.", parse_mode=ParseMode.HTML)

    room = rooms[host_cid]
    idx = room['players'].index(uid)
    is_turn = (room['active'] and room['turn'] == idx)
    
    room['players'].pop(idx)
    room['player_names'].pop(uid, None)
    room['player_chats'].pop(uid, None)

    await context.bot.send_message(chat_id=cid, text="✅ Anda telah keluar.", parse_mode=ParseMode.HTML)
    await broadcast_to_room(context, room, f"🏃 <b>{u.first_name}</b> keluar.")

    if not room['players'] or ((len(room['players']) or 1) < 2 and room['active']):
        await finish_game(context, host_cid)
    elif room['active'] and is_turn:
        room['turn'] %= (len(room['players']) or 1)
        await next_turn_msg(context, host_cid)

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan daftar ID room yang sedang aktif."""
    cid = update.effective_chat.id
    group_rooms = []
    solo_rooms_list = []
    
    for r in rooms.values():
        rid = str(r.get('room_id', ''))
        if rid.startswith("SK-"):
            solo_rooms_list.append(r)
        else:
            group_rooms.append(r)

    pesan_balasan = "<b>📝 ID ROOM AKTIF</b>\n\n"

    pesan_balasan += "<b>🏢 Mode Grup:</b>\n"
    if not group_rooms:
        pesan_balasan += "<i>- Tidak ada room grup aktif.</i>\n"
    else:
        for index, r in enumerate(group_rooms[:5], start=1):
            emoji = "🟢" if r.get('active') else "🔴"
            pesan_balasan += f"{index}. <code>{r['room_id']}</code> {emoji}\n"

    pesan_balasan += "\n<b>👤 Mode Solo/Cross:</b>\n"
    if not solo_rooms_list:
        pesan_balasan += "<i>- Tidak ada room solo aktif.</i>\n"
    else:
        for index, r in enumerate(solo_rooms_list[:5], start=1):
            emoji = "🟢" if r.get('active') else "🔴"
            pesan_balasan += f"{index}. <code>{r['room_id']}</code> {emoji}\n"

    pesan_balasan += "\n<blockquote><b>Keterangan Status:</b>\n🔴 : Menunggu\n🟢 : Berjalan</blockquote>"
    kb = [[InlineKeyboardButton("🔁 Muat Ulang", callback_data="muat_ulang_room")]]
    try:
        await context.bot.send_message(chat_id=cid, text=pesan_balasan, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    except: pass

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memaksa permainan berhenti."""
    u = update.effective_user
    uid, cid = u.id, update.effective_chat.id
    
    is_admin = False
    if update.effective_chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        try:
            m = await context.bot.get_chat_member(cid, uid)
            if m.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]: is_admin = True
        except: pass

    target_host = next((c for c, r in rooms.items() if uid in r.get('players', []) and (uid == r['creator'] or is_owner(uid) or (is_admin and c == cid))), None)
    if not target_host and cid in rooms:
        if is_admin or is_owner(uid): target_host = cid

    if target_host:
        await finish_game(context, target_host)
    else:
        await context.bot.send_message(chat_id=cid, text="❌ <b>Ditolak:</b> Hanya Admin atau Leader game yang bisa menghentikan.", parse_mode=ParseMode.HTML)

async def usir_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengeluarkan pemain pasif (AFK)."""
    uid, cid = update.effective_user.id, update.effective_chat.id
    host_cid = next((c for c, r in rooms.items() if r.get('active') and uid in r.get('players', [])), cid)
    
    room = rooms.get(host_cid)
    if not room or not room['active']: 
        return await context.bot.send_message(chat_id=cid, text="❌ Tidak ada game berjalan.", parse_mode=ParseMode.HTML)

    if room['usir_limit'] <= 0:
        return await context.bot.send_message(chat_id=cid, text="❌ Jatah /usir habis!", parse_mode=ParseMode.HTML)

    kicked = [p for p in room['players'] if room['timeout_count'].get(p, 0) > 0]
    if not kicked:
        return await context.bot.send_message(chat_id=cid, text="⏰ Tidak ada pemain pasif.", parse_mode=ParseMode.HTML)

    room['usir_limit'] -= 1
    for p in kicked:
        if p in room['players']: room['players'].remove(p)
        room['player_names'].pop(p, None)
        room['player_chats'].pop(p, None)
    
    await broadcast_to_room(context, room, f"👋 Pemain pasif berhasil dikeluarkan!")
    if len(room['players']) < 2: 
        await finish_game(context, host_cid)
    else: 
        room['turn'] %= (len(room['players']) or 1)
        await next_turn_msg(context, host_cid)

async def ganti_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengganti huruf awal sambungan."""
    uid, cid = update.effective_user.id, update.effective_chat.id
    host_cid = next((c for c, r in rooms.items() if r.get('active') and uid in r.get('players', [])), None)
    if host_cid:
        room = rooms[host_cid]
        room['turn'] %= len(room['players'])
        if uid == room['players'][room['turn']]:
            if room['ganti_limit'].get(uid, 0) >= 3:
                return await context.bot.send_message(chat_id=cid, text="❌ Limit ganti huruf habis!", parse_mode=ParseMode.HTML)
            
            room['ganti_limit'][uid] = room['ganti_limit'].get(uid, 0) + 1
            room['suffix'] = random.choice("abcdefghijklmnopqrstuvwxyz")
            await broadcast_to_room(context, room, f"🔄 HURUF BARU: <b>{room['suffix'].upper()}</b>")
            await next_turn_msg(context, host_cid)

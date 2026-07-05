import traceback
import asyncio
import httpx
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.ext import ContextTypes
from telegram.error import BadRequest, Forbidden, TimedOut, NetworkError

from config import TOKEN, OWNER_ID, LOG_GROUP_ID, TIMEOUT_GAME
from database import db_query, get_setting
from core import rooms, get_level_info, update_points

# --- 1. GLOBAL ERROR HANDLER ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani error sistem dan mengabaikan error jaringan agar tidak spam log."""
    err_str = str(context.error)
    
    # Abaikan error jaringan/server Telegram yang umum
    ignore_messages = [
        "Bad Gateway", "Timed out", "Network is unreachable", 
        "Internal Server Error", "Message is not modified", "query is too old"
    ]
    if any(x in err_str for x in ignore_messages) or isinstance(context.error, Forbidden):
        return

    # Kirim log detail untuk error kode ke Log Group
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    log_msg = (f"⚠️ <b>DETEKSI ERROR SISTEM</b>\n\n"
               f"<b>Error:</b> <code>{context.error}</code>\n\n"
               f"<b>Traceback:</b>\n<code>{tb_string[-2000:]}</code>")
    try:
        await context.bot.send_message(LOG_GROUP_ID, log_msg, parse_mode=ParseMode.HTML)
    except:
        pass

# --- 2. FORCE SUBSCRIBE HELPERS ---
async def check_fsub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Mengecek status bergabung user di channel wajib."""
    if user_id == OWNER_ID or get_setting('fsub_status') == 'off':
        return True
    
    ids_str = get_setting('fsub_id')
    if not ids_str: return True
    
    for chat_id in ids_str.split():
        try:
            member = await context.bot.get_chat_member(chat_id=int(chat_id), user_id=user_id)
            if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                return False
        except:
            return False
    return True

async def send_fsub_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengirim pesan perintah join channel."""
    mention = update.effective_user.mention_html()
    text = get_setting('fsub_msg').replace("{mention}", mention)
    kb = [
        [InlineKeyboardButton(get_setting('fsub_btn'), url=get_setting('fsub_link'))],
        [InlineKeyboardButton("✅ Saya Sudah Join", url=f"https://t.me/{context.bot.username}?start=mulai")]
    ]
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=text, 
            reply_markup=InlineKeyboardMarkup(kb), 
            parse_mode=ParseMode.HTML
        )
    except:
        pass

# --- 3. GAME LOGIC HELPERS ---
async def broadcast_to_room(context, room, text, reply_markup=None):
    """Mengirim pesan ke seluruh pemain (Support Cross-chat)."""
    unique_chats = set(room.get('player_chats', {}).values())
    for target_cid in unique_chats:
        try:
            await context.bot.send_message(
                chat_id=target_cid,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        except:
            pass

async def finish_game(context, host_cid):
    """Mengakhiri permainan dengan kalkulasi skor akurat dan Tabel Rich 10.1."""
    if host_cid not in rooms: return
    room = rooms[host_cid]
    game_id = room.get('room_id', 'Unknown')
    
    table_rows = ""
    # 1. Gabungkan seluruh ID unik yang terlibat agar tidak ada pemain yang hilang
    all_player_ids = set(room['all_names'].keys()) | set(room['corrects'].keys()) | set(room['mistakes'].keys())
    
    player_results = []
    for p_id in all_player_ids:
        # Prioritaskan nama dari interaksi terakhir
        name = room['all_names'].get(p_id) or room['player_names'].get(p_id, f"User_{p_id}")
        
        corrects = room['corrects'].get(p_id, 0)
        mistakes = room['mistakes'].get(p_id, 0)
        
        # HITUNG POIN BERSIH: (Benar * 10) - (Salah * 5)
        clean_score = (corrects * 10) - (mistakes * 5)
        
        # Ambil level berdasarkan total Benar
        _, _, lvl_emo = get_level_info(corrects)
        
        player_results.append({
            'id': p_id,
            'name': name,
            'score': clean_score,
            'emo': lvl_emo
        })
    
    # 2. SORTING: Poin tertinggi di posisi 1 (Juara)
    player_results.sort(key=lambda x: x['score'], reverse=True)
    
    # 3. SUSUN BARIS TABEL HTML
    for i, p in enumerate(player_results, 1):
        if i == 1: note = "🥇 Juara Utama"
        elif i == 2: note = "🥈 Hebat"
        elif i == 3: note = "🥉 Keren"
        else: note = "🏅 Pejuang"

        # Sanitasi nama agar tidak merusak tag HTML
        safe_name = p['name'].replace("<", "&lt;").replace(">", "&gt;")
        if len(safe_name) > 10: safe_name = safe_name[:10] + ".."

        table_rows += (
            f"<tr>"
            f"<td>{i}</td>"
            f"<td>{safe_name}</td>"
            f"<td>{p['score']}</td>"
            f"<td>{p['emo']}</td>"
            f"<td>{note}</td>"
            f"</tr>"
        )

    # 4. KONSTRUKSI RICH HTML
    rich_html = (
        f"🏁 ID: <b>{game_id}</b><br>"
        f"☠️<b>TELAH BERAKHIR</b>☠️<br><br>"
        f"💡<b>Penetapan Point Global</b>💡<br>"
        f"<table>"
        f"<thead><tr><th>Pos</th><th>Nama</th><th>Poin</th><th>Lvl</th><th>Info</th></tr></thead>"
        f"<tbody>{table_rows}</tbody>"
        f"</table><br>"
        f"<i>Cek kenaikan poin anda ketik /top</i>"
    )

    # Kirim Pengumuman & Tabel via HTTPX
    await broadcast_to_room(context, room, "<b>🏁 PERMAINAN BERAKHIR</b>")
    
    kb = [[{"text": "🎮 Game Lain", "url": "https://t.me/KataIDbot?startgroup=true&admin=delete_messages+restrict_members+pin_messages+invite_users"}]]
    
    async with httpx.AsyncClient() as client:
        url = f"https://api.telegram.org/bot{TOKEN}/sendRichMessage"
        # Gunakan host_cid (grup utama) untuk pengiriman rekap
        payload = {"chat_id": host_cid, "rich_message": {"html": rich_html}, "reply_markup": {"inline_keyboard": kb}}
        try:
            await client.post(url, json=payload, timeout=12.0)
        except:
            pass

    # 5. BERSIHKAN MEMORI & STOP TIMER
    rooms.pop(host_cid, None)
    if context.job_queue:
        for j in context.job_queue.get_jobs_by_name(f"timer_{host_cid}"):
            j.schedule_removal()

async def next_turn_msg(context, host_cid):
    """Menampilkan giliran berikutnya dengan format vertikal rapi."""
    if host_cid not in rooms: return
    room = rooms[host_cid]
    if not room['players']: return await finish_game(context, host_cid)

    room['turn'] %= (len(room['players']) or 1)
    next_p = room['players'][room['turn']]
    mention = f"<a href='tg://user?id={next_p}'>{room['player_names'].get(next_p, 'Pemain')}</a>"
    suffix = room['suffix']
    lvl_name, min_h, lvl_emo = get_level_info(room['turn_count'] + 1)

    room['turn_start_time'] = datetime.now()

    # FORMAT PESAN VERTIKAL DENGAN PROMOSI SUPPORT
    msg = (f"📊 Level: {lvl_emo} <b>{lvl_name}</b> (Min {min_h} Huruf)\n"
           f"🔄 Giliran: {mention}\n"
           f"⏱ Waktu: {TIMEOUT_GAME} Detik!\n"
           f"⚡Support: @OfficialSambungKata\n\n"
           f"🤔Sambung kata dari: <b>{suffix.upper()}</b>")

    await broadcast_to_room(context, room, msg)

    if context.job_queue:
        for j in context.job_queue.get_jobs_by_name(f"timer_{host_cid}"):
            j.schedule_removal()
        
        from utils_game import timeout_handler
        context.job_queue.run_once(timeout_handler, TIMEOUT_GAME, chat_id=host_cid, name=f"timer_{host_cid}")

async def update_group_link(chat: Chat, context: ContextTypes.DEFAULT_TYPE):
    """Memperbarui informasi grup di database."""
    if chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        link = f"https://t.me/{chat.username}" if chat.username else "(Privasi)"
        db_query("UPDATE groups SET title = ?, invite_link = ? WHERE id = ?", (chat.title, link, chat.id), commit=True)


import traceback
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.ext import ContextTypes
from telegram.error import BadRequest, Forbidden, TimedOut

from config import OWNER_ID, LOG_GROUP_ID, TIMEOUT_GAME
from database import db_query, get_setting
from core import rooms, get_level_info, update_points

# --- 1. ERROR HANDLER ---

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani error sistem dan mengirim log detail ke grup log admin."""
    if isinstance(context.error, BadRequest):
        err_str = str(context.error).lower()
        if "message is not modified" in err_str: return
        if "not enough rights" in err_str or "admin" in err_str: return
        if "query is too old" in err_str: return

    if isinstance(context.error, Forbidden): return
    if isinstance(context.error, TimedOut): return

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
    """Mengecek apakah user sudah join channel wajib."""
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
    """Kirim pesan perintah join channel."""
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
    """Kirim pesan ke seluruh chat di dalam room."""
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
    """Mengakhiri permainan dengan format pesan Pemenang Utama & Level Akhir."""
    if host_cid not in rooms: return
    room = rooms[host_cid]
    
    summary_msg = ""
    # Link Game Lain (Deep Link Izin Admin)
    game_lain_url = "https://t.me/KataIDbot?startgroup=true&admin=delete_messages+restrict_members+pin_messages+invite_users"
    kb_game_over = InlineKeyboardMarkup([[InlineKeyboardButton("🎮Game Lain", url=game_lain_url)]])

    if room.get('all_names'):
        # 1. Kalkulasi Skor Seluruh Pemain
        player_list = []
        for p_id, p_name in room['all_names'].items():
            c_count = room['corrects'].get(p_id, 0)
            m_count = room['mistakes'].get(p_id, 0)
            total_poin = (c_count * 10) - (m_count * 5)
            player_list.append({'id': p_id, 'name': p_name, 'score': total_poin})
        
        # Urutkan berdasarkan skor tertinggi
        player_list.sort(key=lambda x: x['score'], reverse=True)
        
        if player_list:
            winner = player_list[0]
            game_id = room.get('room_id', 'Unknown')
            # Ambil Info Level Terakhir (berdasarkan turn_count saat game berhenti)
            lvl_name, _, lvl_emo = get_level_info(room['turn_count'])
            
            # Format Pesan Sesuai Request
            summary_msg = (
                f"☠️Game ID <b>{game_id}</b> Berakhir\n\n"
                f"🎉<b>Pemenang Utama:</b>\n"
                f"<a href='tg://user?id={winner['id']}'>{winner['name']}</a>\n\n"
                f"⏫<b>Point Di Peroleh:</b>\n"
                f"<b>{winner['score']}</b>\n\n"
                f"🎚️<b>Level Akhir:</b>\n"
                f"{lvl_emo} {lvl_name}"
            )

    # Kirim Pengumuman Game Over
    await broadcast_to_room(context, room, "<b>🏁 PERMAINAN BERAKHIR</b>")
    
    if summary_msg:
        await broadcast_to_room(context, room, summary_msg, reply_markup=kb_game_over)
        
    # Bersihkan Memory
    rooms.pop(host_cid, None)
    if context.job_queue:
        for j in context.job_queue.get_jobs_by_name(f"timer_{host_cid}"):
            j.schedule_removal()

async def next_turn_msg(context, host_cid):
    """Menampilkan giliran berikutnya."""
    if host_cid not in rooms: return
    room = rooms[host_cid]
    if not room['players']: return await finish_game(context, host_cid)

    room['turn'] %= (len(room['players']) or 1)
    next_p = room['players'][room['turn']]
    mention = f"<a href='tg://user?id={next_p}'>{room['player_names'].get(next_p, 'Pemain')}</a>"
    suffix = room['suffix']
    lvl_name, min_h, lvl_emo = get_level_info(room['turn_count'] + 1)

    room['turn_start_time'] = datetime.now()

    # Format Pesan Giliran
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
    """Update link invite grup di database."""
    if chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        link = "(Privasi)"
        if chat.username:
            link = f"https://t.me/{chat.username}"
        else:
            try:
                link = await context.bot.export_chat_invite_link(chat.id)
            except:
                link = "(Privasi)"
        db_query("UPDATE groups SET title = ?, invite_link = ? WHERE id = ?", (chat.title, link, chat.id), commit=True)

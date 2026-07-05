import asyncio
import random
import httpx
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from config import OWNER_ID, QRIS_DATA, QR_URL_API, START_TEXT, TOKEN
from database import db_query, get_setting, set_setting
from core import rooms, get_level_info, load_dictionary, update_points
from utils import check_fsub, next_turn_msg, finish_game

# --- FUNGSI HELPER: GENERATE TABEL TOP 20 (4 KOLOM) ---
def get_top20_html():
    res = db_query("SELECT username, points, max_tc FROM users ORDER BY points DESC LIMIT 20", fetchall=True)
    html = "<h2>🏆 TOP 20 GLOBAL PLAYER SAKA</h2>"
    html += "<table><thead><tr><th>Rank</th><th>Pemain</th><th>Level</th><th>Poin</th></tr></thead><tbody>"
    
    if not res:
        html += "<tr><td colspan='4'>Belum ada data pemain tersedia.</td></tr>"
    else:
        for i, r in enumerate(res, 1):
            name = (r[0][:10] + '..') if r[0] and len(r[0]) > 10 else (r[0] or "Anon")
            max_tc = r[2] if r[2] else 0
            # Ambil emoji & nama level asli SAKA
            _, _, lvl_emo = get_level_info(max_tc)
            
            # Penentuan teks level singkat agar tabel rapi
            if max_tc <= 20: ld = f"{lvl_emo} Easy"
            elif max_tc <= 40: ld = f"{lvl_emo} Med"
            elif max_tc <= 60: ld = f"{lvl_emo} Hard"
            elif max_tc <= 80: ld = f"{lvl_emo} HR 3"
            elif max_tc <= 100: ld = f"{lvl_emo} HR 2"
            elif max_tc <= 120: ld = f"{lvl_emo} JWR"
            elif max_tc <= 140: ld = f"{lvl_emo} LGD"
            else: ld = f"{lvl_emo} WNI"
            
            html += f"<tr><td>{i}</td><td>{name}</td><td>{ld}</td><td>{r[1]:,}</td></tr>"
    
    html += "</tbody></table><p><br/><i>Poin dihitung otomatis setiap akhir permainan.</i></p>"
    return html

async def cb_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    u = q.from_user
    uid, cid, data = u.id, q.message.chat_id, q.data
    room = rooms.get(cid)

    # --- 1. TRANSISI KEMBALI KE TOP 20 (EDIT TOTAL) ---
    if data == "back_top":
        html_content = get_top20_html()
        kb = [[{"text": "📈 Score Saya", "callback_data": "my_score"}]]
        
        async with httpx.AsyncClient() as client:
            url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
            payload = {
                "chat_id": cid,
                "message_id": q.message.message_id,
                "rich_message": {"html": html_content},
                "reply_markup": {"inline_keyboard": kb}
            }
            try:
                await client.post(url, json=payload)
                await q.answer("💫 Papan Peringkat Diperbarui")
            except:
                await q.answer()
        return

    # --- 2. SCORE SAYA (STATISTIK PERSONAL - EDIT KE TABEL) ---
    if data == "my_score":
        # Pastikan user sudah ada di database
        update_points(uid, u.first_name, 0)
        
        res = db_query("SELECT points, max_tc FROM users WHERE id=%s", (uid,), fetchone=True)
        pts, mtc = (res[0], res[1]) if res else (0, 0)
        lvl_name, _, emo = get_level_info(mtc)

        html_score = "<h2>📈 STATISTIK SAKA</h2>"
        html_score += "<table><thead><tr><th>Kategori</th><th>Detail</th></tr></thead>"
        html_score += f"<tbody><tr><td>Pemain</td><td>{u.first_name}</td></tr>"
        html_score += f"<tr><td>Score</td><td>{pts:,}</td></tr>"
        html_score += f"<tr><td>Level</td><td>{emo} {lvl_name}</td></tr>"
        html_score += f"<tr><td>Record</td><td>{mtc} Kali</td></tr></tbody></table>"
        
        kb = [[{"text": "🔙 Kembali", "callback_data": "back_top"}]]
        
        async with httpx.AsyncClient() as client:
            url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
            payload = {
                "chat_id": cid,
                "message_id": q.message.message_id,
                "rich_message": {"html": html_score},
                "reply_markup": {"inline_keyboard": kb}
            }
            try:
                await client.post(url, json=payload)
                await q.answer()
            except:
                await q.answer("Gagal memuat statistik.")
        return

    # --- 3. MENU SPIN (CEK SALDO, WD, BACK) ---
    if data == "spin_cek":
        res = db_query("SELECT balance, spin_count, points FROM users WHERE id=%s", (uid,), fetchone=True)
        bal, sc, pts = res if res else (0, 0, 0)
        txt = (f"🚀 <b>Informasi Akun Anda</b>\n\n"
               f"💰 Balance: Rp{bal:,}\n"
               f"🎡 Spin: {sc}×\n"
               f"🪙 Poin: {pts:,}")
        await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data="spin_back")]]), parse_mode="HTML")
        return await q.answer()

    if data == "spin_wd":
        res = db_query("SELECT balance FROM users WHERE id=%s", (uid,), fetchone=True)
        balance = res[0] if res else 0
        if balance < 50000:
            return await q.answer(f"❌ Balance kurang! (Minimal Rp50.000).", show_alert=True)
        
        context.user_data['state'] = 'wd_input'
        wd_text = ("<b>Kirimkan format withdraw untuk admin Transfer</b>\n\n"
                   "<b>Format:</b>\nNama Bank:\nNomor Rekening:\nNama Pemilik:\nTotal Withdraw:\n\n"
                   "<i>Silakan isi dan kirimkan format teks tersebut di sini.</i>")
        await q.edit_message_text(wd_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Batal", callback_data="spin_back")]]), parse_mode="HTML")
        return await q.answer()

    if data == "spin_back":
        text = (
            "🚀 <b>Tukar Poin Sambung-Kata Jadi Saldo Nyata!</b>\n\n"
            "Gunakan poin Top Global kamu untuk bermain Spin.\n"
            "Setiap 1.000 poin = 1x Kesempatan Spin.\n\n"
            "Kumpulkan saldo dan lakukan Withdraw!"
        )
        kb = [
            [InlineKeyboardButton("🎡 Spin Sekarang", callback_data="spin_go")],
            [InlineKeyboardButton("✅ Cek Saldo", callback_data="spin_cek")],
            [InlineKeyboardButton("💰 Withdraw", callback_data="spin_wd")]
        ]
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        return await q.answer()

    if data == "spin_go":
        res = db_query("SELECT points FROM users WHERE id=%s", (uid,), fetchone=True)
        if (res[0] if res else 0) < 1000: return await q.answer("❌ Poin kurang!", show_alert=True)
        db_query("UPDATE users SET points = points - 1000 WHERE id = %s", (uid,), commit=True)
        
        prices = [0, 100, 500, 1000, 5000]
        for _ in range(3):
            await q.edit_message_text(f"⚙️ <b>SPINNING...</b>\n💎 Rp{random.choice(prices):,}", parse_mode="HTML")
            await asyncio.sleep(0.3)
        
        reward = random.choices([0, 100, 500, 1000, 5000, 10000], weights=[50, 20, 15, 10, 4, 1])[0]
        db_query("UPDATE users SET balance = balance + %s, spin_count = spin_count + 1 WHERE id = %s", (reward, uid), commit=True)
        
        msg = f"🎉 HASIL: <b>Rp{reward:,}</b>" if reward > 0 else "💨 HASIL: <b>Zonk!</b>"
        await q.edit_message_text(f"🚀 <b>SPIN SELESAI</b>\n\n{msg}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎡 Lagi", callback_data="spin_go")], [InlineKeyboardButton("🔙 Menu", callback_data="spin_back")]]), parse_mode="HTML")
        return await q.answer()

    # --- 4. MUAT ULANG ROOM (ANTI-CRASH) ---
    if data == "muat_ulang_room":
        gr = [r for r in rooms.values() if not str(r.get('room_id','')).startswith("SK-")]
        sr = [r for r in rooms.values() if str(r.get('room_id','')).startswith("SK-")]
        txt = "<b>📝 ID ROOM AKTIF</b>\n\n<b>🏢 Mode Grup:</b>\n"
        txt += "\n".join([f"{i+1}. <code>{r['room_id']}</code> {'🟢' if r['active'] else '🔴'}" for i,r in enumerate(gr[:5])]) or "<i>Kosong</i>"
        txt += "\n\n<b>👤 Mode Solo/Cross:</b>\n"
        txt += "\n".join([f"{i+1}. <code>{r['room_id']}</code> {'🟢' if r['active'] else '🔴'}" for i,r in enumerate(sr[:5])]) or "<i>Kosong</i>"
        txt += "\n\n<blockquote>🔴 Menunggu | 🟢 Berjalan</blockquote>"
        try:
            await q.edit_message_text(txt, reply_markup=q.message.reply_markup, parse_mode="HTML")
            await q.answer("💫 ID Room Berhasil Diperbarui")
        except BadRequest:
            await q.answer("💫 Sudah Di Perbarui S-K", show_alert=False)
        return

    # --- 5. LOGIKA GAME LOBBY ---
    if data == "join":
        if room and not room['active'] and uid not in room['players']:
            if not await check_fsub(uid, context): return await q.answer("Join Channel!", show_alert=True)
            room['players'].append(uid); room['player_names'][uid] = u.first_name; room['player_chats'][uid] = cid
            plist = "\n".join([f"{i+1}. {room['player_names'][p]}" for i, p in enumerate(room['players'])])
            await q.edit_message_text(f"<u><b>🎮 ROOM DIBUKA</b></u>\nID: <code>{room['room_id']}</code>\n\n👤 Pemain:\n{plist}", reply_markup=q.message.reply_markup, parse_mode="HTML")
        return await q.answer()

    if data == "leave":
        if room and not room['active'] and uid in room['players']:
            room['players'].remove(uid); room['player_names'].pop(uid, None)
            plist = "\n".join([f"{i+1}. {room['player_names'][p]}" for i, p in enumerate(room['players'])]) or "(Kosong)"
            await q.edit_message_text(f"<u><b>🎮 ROOM DIBUKA</b></u>\nID: <code>{room['room_id']}</code>\n\n👤 Pemain:\n{plist}", reply_markup=q.message.reply_markup, parse_mode="HTML")
        return await q.answer()

    if data == "play":
        if room:
            if uid != room['creator']: return await q.answer("Hanya Leader!", show_alert=True)
            if len(room['players']) < 2: return await q.answer("Min 2 Pemain!", show_alert=True)
            room['active'] = True; room['suffix'] = random.choice("abcdefghijklmnopqrstuvwxyz")
            await q.message.delete(); await next_turn_msg(context, cid)
        return await q.answer()

    # --- 6. ADMIN SETTINGS (FSUB CONFIG) ---
    if uid != OWNER_ID: return

    if data == "back_to_settings":
        from plugins.admin import settings_cmd
        # Menghapus state editing jika ada
        context.user_data.pop('editing_setting', None)
        await settings_cmd(update, context)
        return await q.answer()

    if data in ["set_id", "set_link", "set_msg", "set_btn"]:
        key_map = {
            "set_id": ("fsub_id", "🆔 <b>SET CHANNEL ID</b>\n\nKirimkan ID Channel baru."),
            "set_link": ("fsub_link", "🔗 <b>SET LINK CHANNEL</b>\n\nKirimkan Link Join baru."),
            "set_msg": ("fsub_msg", "📝 <b>SET PESAN FSUB</b>\n\nKirimkan teks pesan baru. ({mention})"),
            "set_btn": ("fsub_btn", "🏷️ <b>SET NAMA TOMBOL</b>\n\nKirimkan teks tombol baru.")
        }
        setting_key, prompt = key_map[data]
        context.user_data['editing_setting'] = setting_key
        kb = [[InlineKeyboardButton("🔙 Kembali", callback_data="back_to_settings")]]
        await q.edit_message_text(prompt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        return await q.answer()

    if data == "set_toggle":
        new = "off" if get_setting('fsub_status') == "on" else "on"
        set_setting('fsub_status', new)
        from plugins.admin import settings_cmd
        await settings_cmd(update, context)
        return await q.answer(f"Fsub: {new}")

    if data == "reset_acc":
        db_query("UPDATE users SET points = 0", commit=True)
        await q.answer("Poin Global Berhasil Direset!", show_alert=True)
        await q.message.delete()
        return

    if data == "set_close":
        await q.message.delete()
        return await q.answer()

    if data == "back_to_start":
        kb = [[InlineKeyboardButton("➕ MASUKKAN KE GRUP", url=f"https://t.me/{context.bot.username}?startgroup=start")]]
        await q.edit_message_text(START_TEXT, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML", disable_web_page_preview=True)
        return await q.answer()

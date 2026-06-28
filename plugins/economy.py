import httpx
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.ext import ContextTypes

from database import db_query
from config import TOKEN, OWNER_ID

# --- 1. DATA LEVEL SAKA (LOGIKA ASLI TIDAK BERUBAH) ---
def get_saka_level(tc):
    """Mengambil data level asli SAKA berdasarkan Turn Count pemain."""
    if tc <= 20: name = "Easy"; emo = "🟢"
    elif tc <= 40: name = "Medium"; emo = "🟡"
    elif tc <= 60: name = "Hard"; emo = "🔴"
    elif tc <= 80: name = "Harapan 3"; emo = "🥉"
    elif tc <= 100: name = "Harapan 2"; emo = "🥈"
    elif tc <= 120: name = "Jawara Harapan"; emo = "🥇"
    elif tc <= 140: name = "Legend Kata"; emo = "🏆"
    else: name = "WNI"; emo = "🏅"
    return f"{emo} {name}"

# --- 2. COMMAND /TOP (TABEL RICH 4 KOLOM: PERINGKAT, PEMAIN, LEVEL, POIN) ---
async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan 20 pemain terbaik dengan tabel Rich 4 Kolom."""
    # Ambil data 20 user terbaik
    res = db_query(
        "SELECT username, points, max_tc FROM users ORDER BY points DESC LIMIT 20", 
        fetchall=True
    )
    
    if not res:
        return await update.message.reply_text("📊 Belum ada data pemain.")

    table_rows = ""
    for i, r in enumerate(res, 1):
        # Ambil nama level asli
        max_tc = r[2] if r[2] else 0
        level_display = get_saka_level(max_tc)
        
        # Sanitasi nama (potong jika terlalu panjang agar pas di tabel mobile)
        display_name = (r[0] if r[0] else f"Agen_{i}").replace("<", "&lt;")
        if len(display_name) > 10: 
            display_name = display_name[:10] + ".."
        
        score = f"{r[1]:,}"
        
        # SUSUN BARIS TABEL (4 KOLOM: PERINGKAT, PEMAIN, LEVEL, POIN)
        table_rows += (
            f"<tr>"
            f"<td>{i}</td>"          # Kolom 1: Peringkat
            f"<td>{display_name}</td>" # Kolom 2: Pemain
            f"<td>{level_display}</td>" # Kolom 3: Level
            f"<td>{score}</td>"        # Kolom 4: Poin
            f"</tr>"
        )

    rich_html = f"""
    <h1>🏆 TOP 20 GLOBAL PLAYER SAKA</h1>
    <table>
      <thead>
        <tr>
          <th>Peringkat</th>
          <th>Pemain</th>
          <th>Level</th>
          <th>Poin</th>
        </tr>
      </thead>
      <tbody>{table_rows}</tbody>
    </table>
    <p><br/><i>Gelar <b>WNI</b> diperoleh pada 141+ Turn Count.</i></p>
    """

    # Mengirim menggunakan httpx (Rich Message API 10.1)
    async with httpx.AsyncClient() as client:
        url = f"https://api.telegram.org/bot{TOKEN}/sendRichMessage"
        payload = {
            "chat_id": update.effective_chat.id,
            "rich_message": {"html": rich_html},
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": "📈 Score Saya", "callback_data": "my_score"}]
                ]
            }
        }
        
        try:
            response = await client.post(url, json=payload, timeout=10.0)
            if response.status_code != 200:
                raise Exception("API_ERROR")
        except:
            # FALLBACK: Kirim pesan HTML biasa jika Rich Message gagal
            fallback_text = "🏆 <b>TOP 20 GLOBAL PLAYER SAKA</b>\n\n"
            for i, r in enumerate(res, 1):
                ld = get_saka_level(r[2] or 0)
                fallback_text += f"{i}. {r[0]} - {ld} - {r[1]} pts\n"
            
            await update.message.reply_text(
                fallback_text, 
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📈 Score Saya", callback_data="my_score")]])
            )

# --- 3. COMMAND /SPIN (FITUR UTAMA TETAP UTUH) ---
async def spin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu Spin untuk menukar poin jadi saldo (Hanya di Private Chat)."""
    if update.effective_chat.type != Chat.PRIVATE:
        return await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="❌ <b>Fitur /spin hanya dapat digunakan di Private Chat bot.</b>", 
            parse_mode="HTML"
        )
    
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
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text=text, 
        reply_markup=InlineKeyboardMarkup(kb), 
        parse_mode="HTML"
    )

# --- 4. COMMAND /E (EDIT POIN - FITUR UTAMA TETAP UTUH) ---
async def edit_point_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fitur khusus Owner untuk manajemen poin pemain."""
    if update.effective_user.id != OWNER_ID:
        return

    if not context.args or len(context.args) < 3:
        return await update.message.reply_text("Format: <code>/e [ID/User] [+ / -] [Poin]</code>", parse_mode="HTML")

    try:
        target = context.args[0].replace("@", "")
        op = context.args[1] 
        val = int(context.args[2])
        
        if target.isdigit():
            db_query(
                f"UPDATE users SET points = GREATEST(0, points {op} %s) WHERE id = %s", 
                (val, int(target)), 
                commit=True
            )
        else:
            db_query(
                f"UPDATE users SET points = GREATEST(0, points {op} %s) WHERE username = %s", 
                (val, target), 
                commit=True
            )
            
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"✅ <b>Berhasil!</b> Poin {target} telah diperbarui."
        )
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"❌ <b>Gagal:</b> {str(e)}"
        )

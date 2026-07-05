import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import TOKEN, OWNER_ID

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan panduan lengkap dengan fitur Tabel Rich HTML 10.1."""
    
    # Konstruksi Rich HTML
    rich_html = (
        "<b>🆘 Help Sambung Kata.</b><br><br>"
        
        "💫 <b>Sambung - Kata | WNI</b> Adalah Bot Kata Bersambung Bergiliran Juga Berantai. "
        "Dapat dimainkan di dalam bot ataupun dimainkan di dalam grup dalam mode kompetisi, "
        "dan mengatur strategi untuk mematikan lawan menjawab.<br><br>"
        
        "🚀 <b>Misi Sambung - Kata | WNI</b><br>"
        "Adalah menyambungkan kata yang sesuai dengan kata terakhir lawan. Secara Bergiliran. "
        "Memiliki waktu 45 Detik untuk menyambungkan kata 1 dengan kata lain nya.<br><br>"

        "<details>"
        "<summary>Tampilkan lebih</summary>"
        "<b>🎮 Game Play</b><br>"
        "Memulai game di dalam grup / bot sangatlah mudah anda hanya mengetikan perintah yang sudah di sediakan oleh pembuat game &#64;ID_Anda. "
        "untuk memicu permainan di dalam grup.<br><br>"

        "<b>⚠️Perintah⚠️</b><br>"
        "<b>/mulai</b> - Memuat List Pemain & ID Room.<br>"
        "Ketika pendaftaran dibuka, user lain gunakan tombol 🚪Gabung. Jika ingin batal, gunakan tombol 🏃‍♂️Keluar. "
        "Syarat mulai adalah minimal 2 Pemain, lalu Leader tekan tombol ▶️Play.<br><br>"

        "<b>/gabung</b> - Bergabung ke game berjalan.<br>"
        "Gunakan <code>/gabung</code> di grup atau <code>/gabung [ID]</code> untuk lintas chat.<br><br>"

        "<b>/keluar</b> - Keluar dari sesi game.<br>"
        "Gunakan <code>/keluar</code> atau <code>/keluar [ID]</code> untuk berhenti bermain.<br><br>"

        "<b>/id</b> - Cek ID aktif.<br>"
        "Melihat seluruh daftar ID Room yang sedang menunggu atau bermain.<br><br>"

        "<b>/stop</b> - Menghentikan total permainan (Hanya Leader/Admin).<br><br>"

        "<b>/ganti</b> - Ganti huruf akhiran (Limit 3× per pemain).<br><br>"

        "<b>/usir</b> - Mengeluarkan pemain yang AFK/Pasif.<br><br>"

        "<b>/top</b> - Melihat 20 Pemain Terbaik Dunia.<br><br>"

        "<b>/spin</b> - Tukar poin jadi saldo nyata (Hanya di Private Chat).<br><br>"

        "<b>⭕Donasi</b><br>"
        "Dukung kami agar bot tetap lancar 24/7 melalui link Qris di bawah ini:<br>"
        "https://t.me/ChBotID/231<br><br>"

        "<b>📊 PENJELASAN LEVEL</b><br>"
        "<table>"
        "<thead><tr><th>Level</th><th>Min Huruf</th></tr></thead>"
        "<tbody>"
        "<tr><td>🟢 Easy</td><td>3 Huruf</td></tr>"
        "<tr><td>🟡 Medium</td><td>4 Huruf</td></tr>"
        "<tr><td>🔴 Hard</td><td>5 Huruf</td></tr>"
        "<tr><td>🥉 Harapan 3</td><td>6 Huruf</td></tr>"
        "<tr><td>🥈 Harapan 2</td><td>7 Huruf</td></tr>"
        "<tr><td>🥇 Jawara</td><td>8 Huruf</td></tr>"
        "<tr><td>🏆 Legend</td><td>9 Huruf</td></tr>"
        "<tr><td>🏅 WNI</td><td>10 Huruf</td></tr>"
        "</tbody></table><br>"

        "<b>🚫 LARANGAN GAME</b><br>"
        "<table>"
        "<thead><tr><th>Larangan</th><th>Sanksi</th></tr></thead>"
        "<tbody>"
        "<tr><td>Nama Orang</td><td>Nyawa -1</td></tr>"
        "<tr><td>Kata Terulang</td><td>Nyawa -1</td></tr>"
        "<tr><td>Kata Non-Baku</td><td>Nyawa -1</td></tr>"
        "<tr><td>Non-KBBI</td><td>Nyawa -1</td></tr>"
        "</tbody></table><br>"

        "<b>⏱️ WAKTU JAWAB</b><br>"
        "<table>"
        "<thead><tr><th>Kategori</th><th>Durasi</th></tr></thead>"
        "<tbody>"
        "<tr><td>Batas Menjawab</td><td>45 Detik</td></tr>"
        "<tr><td>Status AFK</td><td>3× Lewat</td></tr>"
        "</tbody></table><br>"

        "Saya Di Rancang & Di Dukung Oleh:<br><br>"
        "<b>👨‍💻Perancang Bot</b><br>"
        "- &#64;ID_Anda<br>"
        "- &#64;ID_Saya<br><br>"

        "<b>💻Support</b><br>"
        "- &#64;gaemaryllis<br>"
        "- &#64;T1DAK<br>"
        "- &#64;queenalaa23<br>"
        "- &#64;Akusukakue<br>"
        "- &#64;anaakitik | &#64;SilenceSpe4ks<br><br>"
        
        "📢<b>Channel:</b> &#64;ChBotID"
        "</details>"
    )

    payload = {
        "chat_id": update.effective_chat.id,
        "rich_message": {"html": rich_html},
        "reply_markup": {
            "inline_keyboard": [[{"text": "👨‍💻 Bantuan Admin", "url": f"tg://user?id={OWNER_ID}"}]]
        }
    }

    async with httpx.AsyncClient() as client:
        url = f"https://api.telegram.org/bot{TOKEN}/sendRichMessage"
        try:
            response = await client.post(url, json=payload, timeout=25.0)
            if response.status_code != 200:
                print(f"DEBUG HELP ERROR: {response.text}")
                raise Exception("API_REJECTED")
        except Exception:
            # Fallback jika Rich Message gagal
            await update.message.reply_text(
                "🆘 <b>Help Sambung Kata</b>\n\nMaaf, terjadi kendala saat memuat panduan. Hubungi admin.",
                parse_mode="HTML"
            )

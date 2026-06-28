import httpx
import platform
import sys
from telegram import Update
from telegram.ext import ContextTypes
from config import TOKEN, OWNER_ID

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan panduan lengkap dengan narasi mendalam dan fitur Collapsible."""
    
    # 1. Ambil data sistem
    os_info = f"{platform.system()} {platform.machine()}".replace("<", "&lt;").replace(">", "&gt;")
    py_ver = sys.version.split()[0]

    # 2. Susun Rich HTML (Tanpa Indentasi awal baris agar aman 100%)
    rich_html = (
        "<b>👋 SELAMAT DATANG DI ARENA SAMBUNG KATA SAKA!</b><br>"
        "Pusat peradaban kata dan adu ketangkasan otak terbesar di Telegram. Klik judul di bawah untuk mengeksplorasi seluruh fitur kami:<br><br>"
        
        "<details>"
        "<summary>🌟 SAMBUTAN HANGAT</summary>"
        "Halo Agen Bahasa! Kami sangat senang Anda berada di sini. Bot Sambung Kata (SAKA) bukan sekadar bot permainan biasa; ini adalah wadah di mana ribuan orang berkumpul untuk menguji sejauh mana penguasaan kosa kata mereka. Di sini, setiap kata yang Anda ketik adalah senjata, dan setiap jawaban benar adalah langkah menuju gelar Legenda!"
        "</details>"
        
        "<details>"
        "<summary>🛠️ KEGUNAAN BOT INI</summary>"
        "Bot SAKA dirancang sebagai asisten interaktif di dalam Grup maupun Private Chat. Kegunaan utamanya adalah sebagai media hiburan yang edukatif, pengisi kekosongan waktu yang produktif, serta alat untuk menghidupkan suasana grup agar lebih aktif dan kompetitif. Bot ini juga terintegrasi dengan database KBBI yang sangat luas, menjadikannya referensi kata baku yang handal."
        "</details>"
        
        "<details>"
        "<summary>🧠 MANFAAT BERMAIN GAME INI</summary>"
        "Bermain sambung kata secara rutin memiliki manfaat luar biasa, di antaranya:<br>"
        "• <b>Memperluas Kosa Kata:</b> Anda akan menemukan ribuan diksi baru yang jarang didengar.<br>"
        "• <b>Melatih Kecepatan Berpikir:</b> Batas waktu 45 detik memaksa otak bekerja lebih cepat dan fokus.<br>"
        "• <b>Mencegah Pikun:</b> Aktivitas mengingat dan mencari kata sangat baik untuk kesehatan saraf kognitif.<br>"
        "• <b>Cinta Bahasa Indonesia:</b> Mengenal lebih dalam kekayaan bahasa ibu kita melalui Kamus Baku."
        "</details>"
        
        "<details>"
        "<summary>🔥 KESERUAN TANPA BATAS</summary>"
        "Kenapa Anda harus bermain terus? Karena di SAKA, adrenalin Anda akan dipacu! Bayangkan ketegangan saat nyawa tinggal satu, waktu hampir habis, dan Anda harus menemukan kata yang berawalan sulit. Belum lagi persaingan sengit memperebutkan posisi <b>TOP 20 GLOBAL</b> untuk memamerkan gengsi Anda sebagai penguasa bahasa di hadapan pemain seluruh dunia. Setiap level memiliki tantangan yang semakin berat, membuat Anda tidak akan pernah merasa bosan!"
        "</details>"
        
        "<details>"
        "<summary>💡 CARA BERMAIN</summary>"
        "Mulai petualangan Anda dengan langkah mudah:<br>"
        "1. Ketik <b>/mulai</b> untuk membuka pendaftaran di grup atau bermain sendiri.<br>"
        "2. Jika di grup, ajak teman Anda mengetik <b>/gabung</b>.<br>"
        "3. Leader (pembuat room) klik tombol <b>Play</b> untuk memulai perang kata.<br>"
        "4. Bot memberikan akhiran huruf (misal: 'AT'), Anda wajib <b>REPLY</b> pesan bot dengan kata berawalan huruf tersebut (misal: 'ATAP')."
        "</details>"
        
        "<details>"
        "<summary>📖 PERATURAN PERMAINAN</summary>"
        "Demi menjaga sportivitas, patuhi aturan berikut:<br>"
        "• ⏱️ <b>Waktu:</b> Anda hanya punya 45 detik untuk menjawab.<br>"
        "• 📊 <b>Minimal Huruf:</b> Level Easy (3 huruf) hingga level WNI (10 huruf). Semakin tinggi level, semakin panjang kata yang diminta.<br>"
        "• 🚫 <b>Larangan:</b> Dilarang keras menggunakan Nama Orang/Manusia dan kata yang sudah pernah digunakan dalam sesi tersebut.<br>"
        "• 💀 <b>Eliminasi:</b> Salah menjawab 3x atau AFK (tidak jawab) 3x akan membuat Anda gugur otomatis."
        "</details>"
        
        "<details>"
        "<summary>🖥️ INFORMASI SISTEM</summary>"
        f"🖥️ <b>Spesifikasi Bot:</b><br>"
        f"• <b>OS:</b> {os_info}<br>"
        f"• <b>Python:</b> {py_ver}<br>"
        "• <b>Engine:</b> Modular SAKA Architecture v2.5<br>"
        "• <b>Database:</b> PostgreSQL (Ultra Fast)<br>"
        "• <b>Developer:</b> Dede Aldian"
        "</details>"
        
        "<details>"
        "<summary>🎁 DONASI</summary>"
        "Bot ini berjalan 24/7 tanpa henti berkat dukungan para Agen sekalian. Donasi Anda sangat membantu pembiayaan server VPS agar permainan tetap lancar tanpa lag. Anda bisa berdonasi melalui QRIS manual yang terdapat di menu <b>/top</b>.<br><br>"
        "<b>Gopay:</b> <code>089678824963</code> a/n TJ"
        "</details>"
        
        "<br><i>Teruslah berlatih, raih poin sebanyak mungkin, dan jadilah pilar kosa kata bangsa!</i>"
    )

    # 3. Payload
    payload = {
        "chat_id": update.effective_chat.id,
        "rich_message": {"html": rich_html},
        "reply_markup": {
            "inline_keyboard": [[{"text": "👨‍💻 Bantuan Admin", "url": f"tg://user?id={OWNER_ID}"}]]
        }
    }

    # 4. Kirim via HTTPX
    async with httpx.AsyncClient() as client:
        url = f"https://api.telegram.org/bot{TOKEN}/sendRichMessage"
        try:
            response = await client.post(url, json=payload, timeout=20.0)
            if response.status_code != 200:
                raise Exception(f"Error: {response.text}")
        except Exception:
            # Fallback jika terjadi error
            await update.message.reply_text(
                "❓ <b>PANDUAN BOT SAKA</b>\n\nGagal memuat menu interaktif terbaru. Silakan hubungi admin.",
                reply_markup={"inline_keyboard": [[{"text": "👨‍💻 Bantuan", "url": f"tg://user?id={OWNER_ID}"}]]},
                parse_mode="HTML"
            )

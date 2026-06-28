import os
import sys
import logging
from dotenv import load_dotenv

# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv()

# Token & Database (Diambil dari .env)
TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- VALIDASI DASAR ---
if not TOKEN:
    print("❌ ERROR: TOKEN tidak ditemukan di file .env!")
    sys.exit(1)
if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL tidak ditemukan di file .env!")
    sys.exit(1)

# --- USER & GROUP ID CONFIG ---
OWNER_ID = 8298238837
LOG_GROUP_ID = -1003031295203

# --- FILE PATHS ---
DICTIONARY_FILE = "list_10.0.0.txt"
NAMA_FILE_MODULE = "nama" # Merujuk ke nama.py

# --- GAME SETTINGS ---
TIMEOUT_GAME = 45  # Detik
MAX_MISTAKES = 3   # Maksimal salah jawab/timeout
GANTI_LIMIT_DEFAULT = 3
USIR_LIMIT_DEFAULT = 1

# --- ASSETS DATA ---
# Data QRIS untuk donasi
QRIS_DATA = (
    "00020101021126610014COM.GO-JEK.WWW01189360091436446025500210G6446025500303UMI514400"
    "14ID.CO.QRIS.WWW0215ID10254092891920303UMI5204899953033605802ID5925Sambung Kata Bot, "
    "Digital6007CIREBON61054515162070703A016304B56C"
)

# URL QRIS Image generator (API)
QR_URL_API = "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data="

# --- LOGGING CONFIGURATION ---
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = logging.WARNING # Ubah ke logging.INFO jika ingin melihat log masuk

def setup_logging():
    logging.basicConfig(
        format=LOG_FORMAT,
        level=LOG_LEVEL
    )

# --- IMPORT BANNED NAMES (DAFTAR_NAMA) ---
def get_banned_names():
    try:
        # Import dinamis agar bisa di-reload nantinya
        import importlib
        nama_module = importlib.import_module(NAMA_FILE_MODULE)
        return nama_module.DAFTAR_NAMA.lower().split()
    except (ImportError, AttributeError):
        print(f"⚠️ WARNING: File {NAMA_FILE_MODULE}.py tidak ditemukan atau DAFTAR_NAMA kosong!")
        return []

# Load pertama kali
BANNED_NAMES = get_banned_names()

# --- TEXT MESSAGES (Statistik / Default) ---
START_TEXT = (
    " 👋 Hallo, ayok kita main sambung kata!\n\n"
    "Kamu bisa tambahkan bot ini kedalam grup kamu ❗\n\n"
    "🕹️ KONTROL PERMAINAN:\n"
    "• /mulai - Memulai game (Grup / Private)\n"
    "• /gabung - Ikut bermain grup (Pakai /gabung [ID] untuk lintas chat)\n"
    "• /keluar - Berhenti bermain grup (Pakai /keluar [ID] berhenti lintas chat)\n"
    "• /ganti - Ganti huruf awal (Limit 1x)\n"
    "• /stop - Paksa berhenti permainan\n"
    "• /usir - Mengeluarkan pemain pasif\n"
    "• /id - Mengecek ID game yang sedang aktif\n\n"
    "🏆 MENU POIN & HADIAH:\n"
    "• /top - Lihat pemain & Grup terbaik dunia\n"
    "• /spin - Tukar Poin Jadi Saldo\n"
    "• /help - Menu panduan, donasi, info, & aturan\n\n"
    "⚠️𝖣𝗂𝖽𝗎𝗄𝗎𝗇𝗀 𝖮𝗅𝖾𝗁: <a href='https://t.me/drakwebot'>𝖣𝗋𝖺𝗄𝗐𝖾𝖻 𝖦𝖺𝗆𝖾</a>"
)

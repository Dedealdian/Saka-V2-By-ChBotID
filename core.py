import os
import random
import string
import logging
from datetime import datetime
from config import DICTIONARY_FILE, OWNER_ID
from database import db_query

# --- GLOBAL GAME VARIABLES ---
# rooms menyimpan semua data game aktif (Grup & Solo)
rooms = {}

# Dictionary untuk menyimpan kata baku
dictionary = set()

# Cache prefix untuk pengecekan ketersediaan kata secara instan (Optimasi RAM)
valid_prefixes = set()

# --- HELPER PERMAINAN ---

def load_dictionary():
    """
    Memuat kata-kata dari file txt ke dalam memory.
    Fungsi ini dibuat SENYAP (Silent) agar tidak menyebabkan spam log.
    Mengembalikan jumlah kata yang berhasil dimuat.
    """
    global dictionary, valid_prefixes
    dictionary.clear()
    valid_prefixes.clear()
    
    # Cek keberadaan file kamus
    if not os.path.exists(DICTIONARY_FILE):
        try:
            open(DICTIONARY_FILE, 'w').close()
            # Log hanya dikirim jika terjadi anomali (file hilang)
            logging.warning(f"<b>⚠️ Kamus</b>: File {DICTIONARY_FILE} dibuat baru karena tidak ditemukan.")
        except:
            pass
        return 0

    try:
        with open(DICTIONARY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if w:
                    dictionary.add(w)
                    # Cache prefix untuk optimasi anti-mentok (2 & 3 huruf pertama)
                    if len(w) >= 2: valid_prefixes.add(w[:2])
                    if len(w) >= 3: valid_prefixes.add(w[:3])
        
        # Mengembalikan angka saja. Pengiriman pesan log dilakukan oleh pemanggilnya.
        return len(dictionary)
    except Exception as e:
        # Error fatal tetap dicatat namun diformat tebal
        logging.error(f"<b>❌ Gagal Muat Kamus</b>: {str(e)}")
        return 0

def get_level_info(tc):
    """Mengambil informasi level berdasarkan jumlah turn (tc)."""
    if tc <= 20: return "Easy", 3, "🟢"
    elif tc <= 40: return "Medium", 4, "🟡"
    elif tc <= 60: return "Hard", 5, "🔴"
    elif tc <= 80: return "Harapan 3", 6, "🥉"
    elif tc <= 100: return "Harapan 2", 7, "🥈"
    elif tc <= 120: return "Jawara Harapan", 8, "🥇"
    elif tc <= 140: return "Legend Kata", 9, "🏆"
    else: return "WNI (Warga Negara Indonesia)", 10, "🏅"

def is_owner(user_id):
    """Cek apakah user adalah owner bot berdasarkan ID di config."""
    return user_id == OWNER_ID

def generate_solo_id():
    """Generate ID unik untuk mode Solo/Cross-chat (Format: SK-XXXXX)."""
    chars = string.ascii_uppercase + string.digits
    return "SK-" + "".join(random.choice(chars) for _ in range(5))

def update_points(user_id, username, amount, tc_reached=0):
    """
    Update poin dan statistik user ke database.
    Menggunakan logika UPSERT (Insert or Update) yang stabil.
    """
    un = username.replace("@", "") if username else "Player"
    
    # 1. Pastikan user terdaftar di database
    db_query('''INSERT INTO users (id, username, points, max_tc, balance, spin_count) 
                VALUES (?, ?, 0, 0, 0, 0) ON CONFLICT (id) DO NOTHING''', 
             (user_id, un), commit=True)
    
    # 2. Update poin akumulatif dan rekor turn count tertinggi
    db_query('''UPDATE users SET 
                points = GREATEST(0, points + ?), 
                username = ?, 
                max_tc = GREATEST(max_tc, ?) 
                WHERE id = ?''', 
             (amount, un, tc_reached, user_id), commit=True)

# --- CATATAN PENTING ---
# load_dictionary() sengaja tidak dipanggil di sini.
# Pemuatan dilakukan di kata.py (startup) atau game.py (saat mulai game)
# untuk menjaga urutan log agar sinkron dan tidak spam.

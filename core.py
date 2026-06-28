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

# Cache prefix untuk pengecekan ketersediaan kata secara instan
valid_prefixes = set()

# --- HELPER PERMAINAN ---

def load_dictionary():
    """Memuat kata-kata dari file txt ke dalam memory."""
    global dictionary, valid_prefixes
    dictionary.clear()
    valid_prefixes.clear()
    
    if not os.path.exists(DICTIONARY_FILE):
        open(DICTIONARY_FILE, 'w').close()
        print(f"⚠️ Kamus {DICTIONARY_FILE} tidak ditemukan, membuat file baru.")
        return set()

    try:
        with open(DICTIONARY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if w:
                    dictionary.add(w)
                    # Cache prefix untuk optimasi anti-mentok
                    if len(w) >= 2: valid_prefixes.add(w[:2])
                    if len(w) >= 3: valid_prefixes.add(w[:3])
        print(f"✅ Kamus dimuat: {len(dictionary)} kata.")
        return dictionary
    except Exception as e:
        print(f"❌ Gagal memuat kamus: {e}")
        return set()

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
    """Cek apakah user adalah owner bot."""
    return user_id == OWNER_ID

def generate_solo_id():
    """Generate ID unik untuk mode Solo/Cross-chat (SK-XXXXX)."""
    chars = string.ascii_uppercase + string.digits
    return "SK-" + "".join(random.choice(chars) for _ in range(5))

def update_points(user_id, username, amount, tc_reached=0):
    """Update poin user ke database PostgreSQL."""
    un = username.replace("@", "") if username else "Player"
    # Pastikan user ada di DB
    db_query('''INSERT INTO users (id, username, points, max_tc, balance, spin_count) 
                VALUES (?, ?, 0, 0, 0, 0) ON CONFLICT (id) DO NOTHING''', 
             (user_id, un), commit=True)
    
    # Update poin dan max turn count (tc)
    db_query('''UPDATE users SET 
                points = GREATEST(0, points + ?), 
                username = ?, 
                max_tc = GREATEST(max_tc, ?) 
                WHERE id = ?''', 
             (amount, un, tc_reached, user_id), commit=True)

# Muat kamus saat module ini diimpor pertama kali
load_dictionary()

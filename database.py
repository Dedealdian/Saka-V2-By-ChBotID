import sqlite3
import psycopg2
from psycopg2 import extras, pool
import os
import logging
from config import DATABASE_URL

# --- CONNECTION POOLING SETUP ---
try:
    # Menggunakan SimpleConnectionPool untuk efisiensi RAM VPS
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL)
    logging.info("🗄️ Database Connection: Pool berhasil dibuat.")
except Exception as e:
    logging.error(f"⚠️ Database Connection: Gagal membuat pool - {e}")
    db_pool = None

# --- CACHE SETTINGS ---
SETTINGS_CACHE = {}

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    """Fungsi universal untuk menjalankan query PostgreSQL."""
    conn = None
    try:
        if db_pool:
            conn = db_pool.getconn()
        else:
            conn = psycopg2.connect(DATABASE_URL)
            
        c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Konversi placeholder SQLite (?) ke PostgreSQL (%s)
        query = query.replace('?', '%s')
        
        # Logika penggantian INSERT OR IGNORE / REPLACE untuk PostgreSQL
        if "INSERT OR IGNORE" in query:
            query = query.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            if "users" in query: query += " ON CONFLICT (id) DO NOTHING"
            elif "groups" in query: query += " ON CONFLICT (id) DO NOTHING"
            elif "settings" in query: query += " ON CONFLICT (key) DO NOTHING"

        if "INSERT OR REPLACE" in query:
            query = query.replace("INSERT OR REPLACE INTO", "INSERT INTO")
            if "settings" in query: query += " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            elif "users" in query: query += " ON CONFLICT (id) DO UPDATE SET username = EXCLUDED.username, points = EXCLUDED.points, balance = EXCLUDED.balance, max_tc = EXCLUDED.max_tc, spin_count = EXCLUDED.spin_count"

        c.execute(query, params)
        res = None
        if fetchone: res = c.fetchone()
        if fetchall: res = c.fetchall()
        if commit: conn.commit()
        return res
    except Exception as e:
        if conn: conn.rollback()
        # Penanganan khusus untuk versi Postgres yang mungkin tidak support ON CONFLICT
        if "syntax error at or near \"ON\"" in str(e) or "ON CONFLICT" in str(e):
            try:
                c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                raw_query = query.split(" ON CONFLICT")[0]
                c.execute(raw_query, params)
                if commit: conn.commit()
            except:
                if conn: conn.rollback()
        else:
            logging.error(f"❌ Database Query Error: {e}")
            raise e
    finally:
        if conn:
            if db_pool:
                db_pool.putconn(conn)
            else:
                conn.close()

def migrate_from_all_sqlite():
    """Migrasi data dari database lama (SQLite) ke PostgreSQL."""
    for db_file in ['database.db', 'bungkata.db']:
        if os.path.exists(db_file):
            logging.info(f"🔄 Database Migration: Memproses {db_file}...")
            conn_sq = sqlite3.connect(db_file)
            c_sq = conn_sq.cursor()
            try:
                c_sq.execute("SELECT id, username, points, max_tc, balance, spin_count FROM users")
                rows = c_sq.fetchall()
                for u in rows:
                    db_query("INSERT OR IGNORE INTO users (id, username, points, max_tc, balance, spin_count) VALUES (?, ?, ?, ?, ?, ?)",
                             (u[0], u[1], u[2], u[3], u[4], u[5]), commit=True)
                logging.info(f"✅ Database Migration: {db_file} selesai dipindahkan.")
            except Exception as e:
                logging.error(f"❌ Database Migration: Gagal pada {db_file} - {e}")
            finally:
                conn_sq.close()

def init_db():
    """Inisialisasi tabel-tabel utama."""
    db_query('''CREATE TABLE IF NOT EXISTS users (
        id BIGINT PRIMARY KEY,
        username TEXT,
        points INTEGER DEFAULT 0,
        max_tc INTEGER DEFAULT 0,
        balance INTEGER DEFAULT 0,
        spin_count INTEGER DEFAULT 0
    )''', commit=True)
    
    db_query('''CREATE TABLE IF NOT EXISTS groups (
        id BIGINT PRIMARY KEY, 
        title TEXT,
        invite_link TEXT DEFAULT '(Privasi)',
        total_chat INTEGER DEFAULT 0,
        last_msg_id BIGINT DEFAULT 0,
        warning_time TEXT DEFAULT ''
    )''', commit=True)
    
    db_query('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''', commit=True)

    # Jalankan migrasi jika ada file SQLite
    migrate_from_all_sqlite()

    # Masukkan pengaturan default (fsub, dll)
    defaults = [
        ('fsub_id', '-1002856616933'),
        ('fsub_link', 'https://t.me/addlist/Ld2g4xk8AAwyOTg1'),
        ('fsub_btn', '🚪 Join Channel'),
        ('fsub_status', 'on'),
        ('fsub_msg', '<b>⚠️ AKSES TERBATAS</b>\n\nUntuk menggunakan fitur bot dan bermain di grup, Anda wajib bergabung ke Channel kami melalui link di bawah! {mention}')
    ]
    for k, v in defaults:
        db_query("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v), commit=True)
    
    logging.info("✅ Database System: Tabel & Default Settings siap.")

def get_setting(key):
    """Mengambil setting dengan sistem cache untuk menghemat RAM VPS."""
    if key in SETTINGS_CACHE: return SETTINGS_CACHE[key]
    res = db_query("SELECT value FROM settings WHERE key=%s", (key,), fetchone=True)
    val = res[0] if res else ""
    SETTINGS_CACHE[key] = val
    return val

def set_setting(key, value):
    """Mengupdate setting."""
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)), commit=True)
    SETTINGS_CACHE[key] = str(value)

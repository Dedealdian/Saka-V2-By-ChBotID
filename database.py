import sqlite3
import psycopg2
from psycopg2 import extras, pool
import os
from config import DATABASE_URL

# --- CONNECTION POOLING SETUP ---
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL)
    print("✅ Database connection pool berhasil dibuat.")
except Exception as e:
    print(f"⚠️ Gagal membuat database pool: {e}")
    db_pool = None

# --- CACHE SETTINGS ---
SETTINGS_CACHE = {}

def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    """Fungsi universal untuk menjalankan query PostgreSQL."""
    conn = None
    if db_pool:
        conn = db_pool.getconn()
    else:
        conn = psycopg2.connect(DATABASE_URL)
        
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # Konversi placeholder SQLite (?) ke PostgreSQL (%s)
        query = query.replace('?', '%s')
        
        # Logika penggantian INSERT OR IGNORE / REPLACE untuk PostgreSQL modern
        # Jika PostgreSQL versi lama, bagian ini mungkin perlu disesuaikan manual
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
        # Jika error karena ON CONFLICT (Postgres Tua), kita abaikan saja khusus untuk INSERT
        if "syntax error at or near \"ON\"" in str(e) or "ON CONFLICT" in str(e):
            conn.rollback()
            # Coba jalankan tanpa ON CONFLICT (Akan error jika duplicate, tapi aman untuk init)
            try:
                raw_query = query.split(" ON CONFLICT")[0]
                c.execute(raw_query, params)
                if commit: conn.commit()
            except:
                conn.rollback()
        else:
            print(f"❌ Database Error: {e}")
            raise e
    finally:
        c.close()
        if db_pool:
            db_pool.putconn(conn)
        else:
            conn.close()

def migrate_from_all_sqlite():
    """Migrasi data dari database lama (SQLite) ke PostgreSQL."""
    for db_file in ['database.db', 'bungkata.db']:
        if os.path.exists(db_file):
            print(f">>> MEMPROSES MIGRASI: {db_file}")
            conn_sq = sqlite3.connect(db_file)
            c_sq = conn_sq.cursor()
            try:
                c_sq.execute("SELECT id, username, points, max_tc, balance, spin_count FROM users")
                for u in c_sq.fetchall():
                    db_query("INSERT OR IGNORE INTO users (id, username, points, max_tc, balance, spin_count) VALUES (?, ?, ?, ?, ?, ?)",
                             (u[0], u[1], u[2], u[3], u[4], u[5]), commit=True)
                print(f"✅ SELESAI MIGRASI {db_file}")
            except Exception as e:
                print(f"❌ ERROR MIGRASI {db_file}: {e}")
            finally:
                conn_sq.close()

def init_db():
    """Inisialisasi tabel-tabel."""
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

    migrate_from_all_sqlite()

    # Pakai INSERT OR IGNORE agar ditangani oleh logika db_query
    defaults = [
        ('fsub_id', '-1002856616933'),
        ('fsub_link', 'https://t.me/addlist/Ld2g4xk8AAwyOTg1'),
        ('fsub_btn', '🚪 Join Channel'),
        ('fsub_status', 'on'),
        ('fsub_msg', '<b>⚠️ AKSES TERBATAS</b>\n\nUntuk menggunakan fitur bot dan bermain di grup, Anda wajib bergabung ke Channel kami melalui link di bawah! {mention}')
    ]
    for k, v in defaults:
        db_query("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v), commit=True)

def get_setting(key):
    if key in SETTINGS_CACHE: return SETTINGS_CACHE[key]
    res = db_query("SELECT value FROM settings WHERE key=%s", (key,), fetchone=True)
    val = res[0] if res else ""
    SETTINGS_CACHE[key] = val
    return val

def set_setting(key, value):
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)), commit=True)
    SETTINGS_CACHE[key] = str(value)

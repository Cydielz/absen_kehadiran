import os
import secrets
from datetime import datetime
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception
from datetime import timezone, timedelta

from werkzeug.security import generate_password_hash

from app import db, init_db

try:
    TZ = ZoneInfo('Asia/Jayapura') if ZoneInfo else timezone(timedelta(hours=9))
except ZoneInfoNotFoundError:
    TZ = timezone(timedelta(hours=9))

init_db()
conn = db()

# --- Contoh data siswa ---
rows = [
    ('0012345678', 'Contoh Siswa 1', 'X IPA 1', '081234567890'),
    ('0012345679', 'Contoh Siswa 2', 'X IPA 1', '081298765432'),
]
for nisn, nama, kelas, wa in rows:
    conn.execute('''INSERT OR IGNORE INTO siswa (nisn,nama,kelas,whatsapp_ortu,created_at)
                    VALUES (?,?,?,?,?)''', (nisn, nama, kelas, wa, datetime.now(TZ).isoformat()))

# --- Akun admin default (WAJIB diganti setelah login pertama) ---
existing_admin = conn.execute('SELECT id FROM admin_users LIMIT 1').fetchone()
if not existing_admin:
    default_username = os.getenv('SEED_ADMIN_USERNAME', 'admin')
    default_password = os.getenv('SEED_ADMIN_PASSWORD') or secrets.token_urlsafe(9)
    conn.execute(
        'INSERT INTO admin_users (username, password_hash, created_at) VALUES (?,?,?)',
        (default_username, generate_password_hash(default_password), datetime.now(TZ).isoformat())
    )
    print('=' * 60)
    print('AKUN ADMIN DIBUAT:')
    print(f'  Username : {default_username}')
    print(f'  Password : {default_password}')
    print('CATAT password ini sekarang — tidak akan ditampilkan lagi.')
    print('Segera login dan pertimbangkan mengganti kredensial.')
    print('=' * 60)
else:
    print('Akun admin sudah ada, tidak membuat akun baru.')

# --- Contoh perangkat scanner (opsional, untuk uji coba lokal) ---
existing_device = conn.execute('SELECT id FROM devices LIMIT 1').fetchone()
if not existing_device:
    demo_key = secrets.token_hex(16)
    conn.execute(
        'INSERT INTO devices (nama_perangkat, api_key, aktif, created_at) VALUES (?,?,1,?)',
        ('HP Scanner Contoh', demo_key, datetime.now(TZ).isoformat())
    )
    print('=' * 60)
    print('PERANGKAT CONTOH DIBUAT (untuk uji coba /scan):')
    print(f'  Nama       : HP Scanner Contoh')
    print(f'  X-Device-Key : {demo_key}')
    print('Masukkan kode ini ke aplikasi Android, atau buat perangkat baru dari panel admin.')
    print('=' * 60)

conn.commit()
conn.close()
print('Database siap.')

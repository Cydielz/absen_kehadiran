"""Bootstrap database SEKALI SAJA saat pertama kali dijalankan.

start_server.bat/.sh memanggil skrip ini setiap kali server dinyalakan,
tapi skrip ini hanya benar-benar membuat data (akun admin, siswa contoh,
perangkat contoh) kalau database masih benar-benar kosong (belum ada
akun admin sama sekali). Setelah setup pertama, menjalankan skrip ini
lagi TIDAK akan menambahkan apa pun -- jadi data yang sudah kamu hapus
dari panel admin (misalnya siswa contoh) tidak akan muncul lagi sendiri.
"""
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

existing_admin = conn.execute('SELECT id FROM admin_users LIMIT 1').fetchone()

if existing_admin:
    # Sudah pernah di-setup sebelumnya -> jangan sentuh data apa pun lagi.
    # Ini yang mencegah siswa/perangkat contoh muncul lagi setelah dihapus.
    print('Database sudah pernah di-setup sebelumnya, tidak ada yang ditambahkan.')
    print('(Kalau butuh akun admin baru/reset password, pakai reset_admin.py.)')
else:
    # --- Setup pertama kali: buat akun admin ---
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

    # --- Contoh data siswa (hanya sekali, boleh dihapus kapan saja dari panel admin) ---
    contoh_siswa = [
        ('0012345678', 'Contoh Siswa 1', 'X IPA 1', '081234567890'),
        ('0012345679', 'Contoh Siswa 2', 'X IPA 1', '081298765432'),
    ]
    for nisn, nama, kelas, wa in contoh_siswa:
        conn.execute('''INSERT OR IGNORE INTO siswa (nisn,nama,kelas,whatsapp_ortu,created_at)
                        VALUES (?,?,?,?,?)''', (nisn, nama, kelas, wa, datetime.now(TZ).isoformat()))
    print('2 siswa contoh ditambahkan (boleh dihapus kapan saja dari panel admin, tidak akan muncul lagi).')

    # --- Contoh perangkat scanner (hanya sekali) ---
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

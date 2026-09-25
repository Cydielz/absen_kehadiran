"""Reset password admin panel kalau lupa.

Cara pakai (dari folder backend, venv aktif):
    python reset_admin.py
lalu ikuti instruksi di layar.

Kalau username admin belum ada sama sekali, skrip ini akan membuatkan.
Kalau sudah ada, password lama akan DIGANTI dengan yang baru.
"""
import getpass
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

from app import db, init_db, now_local

init_db()
conn = db()

rows = conn.execute('SELECT id, username FROM admin_users').fetchall()

if rows:
    print('Akun admin yang ada saat ini:')
    for r in rows:
        print(f"  - {r['username']}")
    username = input('Ketik username yang mau direset password-nya: ').strip()
    row = conn.execute('SELECT id FROM admin_users WHERE username=?', (username,)).fetchone()
    if not row:
        print(f'Username "{username}" tidak ditemukan. Batal.')
        conn.close()
        raise SystemExit(1)
else:
    username = input('Belum ada akun admin. Buat username baru: ').strip() or 'admin'
    row = None

password = getpass.getpass('Password baru (ketikan tidak akan terlihat): ').strip()
password2 = getpass.getpass('Ulangi password baru: ').strip()

if not password or password != password2:
    print('Password kosong atau tidak sama. Batal, tidak ada yang diubah.')
    conn.close()
    raise SystemExit(1)

password_hash = generate_password_hash(password)

if row:
    conn.execute('UPDATE admin_users SET password_hash=? WHERE id=?', (password_hash, row['id']))
    print(f'Password untuk "{username}" berhasil diganti.')
else:
    conn.execute(
        'INSERT INTO admin_users (username, password_hash, created_at) VALUES (?,?,?)',
        (username, password_hash, now_local().isoformat())
    )
    print(f'Akun admin baru "{username}" berhasil dibuat.')

conn.commit()
conn.close()
print('Selesai. Silakan login dengan username & password baru.')

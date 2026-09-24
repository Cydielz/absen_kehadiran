import os
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception

from flask import (
    Flask, jsonify, request, render_template, redirect, url_for, flash, g
)
import requests
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user, login_required,
    current_user,
)
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
DB_PATH = os.path.join(BASE_DIR, 'sekolah.db')
TIMEZONE = os.getenv('TIMEZONE', 'Asia/Jayapura')

# Windows installations may not include the IANA time-zone database.
# Fall back to WIT (UTC+09:00) so the server does not crash with HTTP 500.
try:
    LOCAL_TZ = ZoneInfo(TIMEZONE) if ZoneInfo else timezone(timedelta(hours=9))
except ZoneInfoNotFoundError:
    LOCAL_TZ = timezone(timedelta(hours=9))

app = Flask(__name__)

# --- SECRET_KEY ---------------------------------------------------------
# Kalau admin belum mengganti FLASK_SECRET_KEY di .env, jangan pakai nilai
# default yang statis (nilainya sama di semua instalasi = gampang ditebak).
# Sebagai gantinya, buat kunci acak khusus untuk sesi berjalan ini dan beri
# peringatan. Ini membuat session tetap aman, hanya saja semua orang akan
# ter-logout setiap server direstart sampai .env benar-benar diisi.
_secret_from_env = os.getenv('FLASK_SECRET_KEY', '')
if not _secret_from_env or _secret_from_env.startswith('ganti-'):
    app.secret_key = secrets.token_hex(32)
    print(
        '[PERINGATAN] FLASK_SECRET_KEY belum diatur di backend/.env. '
        'Memakai kunci acak sementara (sesi akan hilang tiap restart server). '
        'Segera isi FLASK_SECRET_KEY dengan string acak yang panjang.'
    )
else:
    app.secret_key = _secret_from_env

csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[])

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Silakan login untuk mengakses halaman admin.'


# --------------------------------------------------------------------------
# Utilitas waktu & tahun ajaran
# --------------------------------------------------------------------------

def now_local():
    return datetime.now(LOCAL_TZ)


def tahun_ajaran_dan_semester(dt: datetime):
    """Tahun ajaran Indonesia umumnya berjalan Juli-Juni.
    Juli-Desember = semester Ganjil, Januari-Juni = semester Genap."""
    if dt.month >= 7:
        tahun_ajaran = f"{dt.year}/{dt.year + 1}"
        semester = 'Ganjil'
    else:
        tahun_ajaran = f"{dt.year - 1}/{dt.year}"
        semester = 'Genap'
    return tahun_ajaran, semester


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    conn = db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS siswa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nisn TEXT NOT NULL UNIQUE,
        nama TEXT NOT NULL,
        kelas TEXT NOT NULL,
        whatsapp_ortu TEXT,
        aktif INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS absensi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        siswa_id INTEGER NOT NULL,
        tanggal TEXT NOT NULL,
        jam_masuk TEXT,
        jam_keluar TEXT,
        status TEXT NOT NULL DEFAULT 'Hadir',
        kelas TEXT NOT NULL,
        tahun_ajaran TEXT NOT NULL,
        semester TEXT NOT NULL,
        keterangan TEXT,
        device_id TEXT,
        dicatat_oleh TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(siswa_id) REFERENCES siswa(id) ON DELETE CASCADE,
        UNIQUE(siswa_id, tanggal)
    );

    CREATE INDEX IF NOT EXISTS idx_absensi_tanggal ON absensi(tanggal);
    CREATE INDEX IF NOT EXISTS idx_siswa_nisn ON siswa(nisn);

    CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama_perangkat TEXT NOT NULL,
        api_key TEXT NOT NULL UNIQUE,
        aktif INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    ''')
    conn.commit()

    # Migrasi ringan untuk database lama (dibuat sebelum kolom-kolom baru ada).
    existing_cols = {row['name'] for row in conn.execute('PRAGMA table_info(absensi)')}
    migrations = {
        'jam_keluar': "ALTER TABLE absensi ADD COLUMN jam_keluar TEXT",
        'kelas': "ALTER TABLE absensi ADD COLUMN kelas TEXT NOT NULL DEFAULT ''",
        'tahun_ajaran': "ALTER TABLE absensi ADD COLUMN tahun_ajaran TEXT NOT NULL DEFAULT ''",
        'semester': "ALTER TABLE absensi ADD COLUMN semester TEXT NOT NULL DEFAULT ''",
        'keterangan': "ALTER TABLE absensi ADD COLUMN keterangan TEXT",
        'dicatat_oleh': "ALTER TABLE absensi ADD COLUMN dicatat_oleh TEXT",
    }
    for col, ddl in migrations.items():
        if col not in existing_cols:
            conn.execute(ddl)
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# Login admin (Flask-Login)
# --------------------------------------------------------------------------

class AdminUser(UserMixin):
    def __init__(self, row):
        self.id = str(row['id'])
        self.username = row['username']


@login_manager.user_loader
def load_user(user_id):
    conn = db()
    row = conn.execute('SELECT * FROM admin_users WHERE id=?', (user_id,)).fetchone()
    conn.close()
    return AdminUser(row) if row else None


# --------------------------------------------------------------------------
# WhatsApp (Fonnte)
# --------------------------------------------------------------------------

def send_whatsapp(target: str, message: str):
    token = os.getenv('FONNTE_TOKEN', '').strip()
    if not token or not target:
        return {'sent': False, 'reason': 'FONNTE_TOKEN atau nomor WhatsApp belum diatur'}

    try:
        response = requests.post(
            'https://api.fonnte.com/send',
            headers={'Authorization': token},
            data={
                'target': target,
                'message': message,
                'countryCode': os.getenv('FONNTE_COUNTRY_CODE', '62'),
            },
            timeout=20,
        )
        ok = response.ok
        try:
            body = response.json()
        except Exception:
            body = {'raw': response.text}
        return {'sent': ok, 'response': body, 'http_status': response.status_code}
    except requests.RequestException as exc:
        return {'sent': False, 'reason': str(exc)}


# --------------------------------------------------------------------------
# Autentikasi device untuk endpoint /scan
# --------------------------------------------------------------------------

def get_authorized_device():
    """Kembalikan row device aktif kalau header X-Device-Key valid, else None."""
    api_key = request.headers.get('X-Device-Key', '').strip()
    if not api_key:
        return None
    conn = db()
    row = conn.execute(
        'SELECT * FROM devices WHERE api_key=? AND aktif=1 LIMIT 1', (api_key,)
    ).fetchone()
    conn.close()
    return row


# --------------------------------------------------------------------------
# Halaman login / logout
# --------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn = db()
        row = conn.execute('SELECT * FROM admin_users WHERE username=?', (username,)).fetchone()
        conn.close()
        if row and check_password_hash(row['password_hash'], password):
            login_user(AdminUser(row))
            flash('Berhasil login.', 'success')
            return redirect(url_for('home'))
        flash('Username atau password salah.', 'error')
    return render_template('login.html')


@app.post('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda sudah logout.', 'success')
    return redirect(url_for('login'))


# --------------------------------------------------------------------------
# Halaman admin (WAJIB login)
# --------------------------------------------------------------------------

@app.get('/')
@login_required
def home():
    tanggal = request.args.get('tanggal', now_local().strftime('%Y-%m-%d'))
    conn = db()
    students = conn.execute('SELECT * FROM siswa ORDER BY nama COLLATE NOCASE').fetchall()
    rekap = conn.execute('''
        SELECT a.*, s.nisn, s.nama
        FROM absensi a JOIN siswa s ON s.id = a.siswa_id
        WHERE a.tanggal = ?
        ORDER BY COALESCE(a.jam_masuk, '99:99:99') ASC
    ''', (tanggal,)).fetchall()
    devices = conn.execute('SELECT * FROM devices ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template(
        'admin.html',
        students=students,
        rekap=rekap,
        tanggal=tanggal,
        devices=devices,
    )


@app.get('/api/health')
def health():
    # Endpoint publik ringan untuk cek server hidup (tidak membocorkan data siswa).
    return jsonify({'ok': True, 'timezone': TIMEZONE})


@app.post('/scan')
@limiter.limit('30 per minute')
@csrf.exempt
def scan():
    device = get_authorized_device()
    if not device:
        return jsonify({
            'success': False,
            'code': 'DEVICE_UNAUTHORIZED',
            'message': 'Perangkat tidak dikenali. Hubungi admin untuk mendapatkan kode perangkat.',
        }), 401

    data = request.get_json(silent=True) or {}
    nisn = str(data.get('nisn', '')).strip()
    android_device_id = str(data.get('device_id', '')).strip()[:100]
    device_label = f"{device['nama_perangkat']} ({android_device_id})" if android_device_id else device['nama_perangkat']

    if not nisn:
        return jsonify({'success': False, 'code': 'NISN_REQUIRED', 'message': 'NISN kosong.'}), 400

    conn = db()
    siswa = conn.execute(
        'SELECT * FROM siswa WHERE nisn=? AND aktif=1 LIMIT 1', (nisn,)
    ).fetchone()

    if not siswa:
        conn.close()
        return jsonify({'success': False, 'code': 'STUDENT_NOT_FOUND', 'message': 'NISN tidak terdaftar atau siswa tidak aktif.'}), 404

    current = now_local()
    tanggal = current.strftime('%Y-%m-%d')
    jam = current.strftime('%H:%M:%S')
    tahun_ajaran, semester = tahun_ajaran_dan_semester(current)

    existing = conn.execute(
        'SELECT * FROM absensi WHERE siswa_id=? AND tanggal=? LIMIT 1',
        (siswa['id'], tanggal)
    ).fetchone()

    wa_result = None
    whatsapp = (siswa['whatsapp_ortu'] or '').strip()

    if existing is None:
        # Scan pertama hari ini -> catat jam masuk.
        try:
            conn.execute(
                '''INSERT INTO absensi
                   (siswa_id, tanggal, jam_masuk, status, kelas, tahun_ajaran, semester,
                    device_id, dicatat_oleh, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (siswa['id'], tanggal, jam, 'Hadir', siswa['kelas'], tahun_ajaran, semester,
                 device_label, 'scan', current.isoformat())
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # Race condition dua scan hampir bersamaan; ambil ulang row yang menang.
            conn.rollback()
            existing = conn.execute(
                'SELECT * FROM absensi WHERE siswa_id=? AND tanggal=?', (siswa['id'], tanggal)
            ).fetchone()
            conn.close()
            return jsonify({
                'success': True, 'code': 'ALREADY_ATTENDED',
                'message': f"{siswa['nama']} sudah absen hari ini.",
                'student': dict(siswa), 'attendance': dict(existing) if existing else None,
            })

        if whatsapp:
            message = (
                f"PEMBERITAHUAN ABSENSI SEKOLAH\n\n"
                f"Nama: {siswa['nama']}\nNISN: {siswa['nisn']}\nKelas: {siswa['kelas']}\n"
                f"Status: HADIR (masuk)\nTanggal: {current.strftime('%d-%m-%Y')}\nJam masuk: {jam}\n\n"
                f"Pesan ini dikirim otomatis oleh sistem absensi sekolah."
            )
            wa_result = send_whatsapp(whatsapp, message)

        conn.close()
        return jsonify({
            'success': True, 'code': 'ATTENDANCE_RECORDED',
            'message': f"Absensi masuk {siswa['nama']} berhasil dicatat pada {jam}.",
            'student': {'nisn': siswa['nisn'], 'nama': siswa['nama'], 'kelas': siswa['kelas']},
            'attendance': {'tanggal': tanggal, 'jam_masuk': jam, 'jam_keluar': None, 'status': 'Hadir'},
            'whatsapp': wa_result,
        }), 201

    if existing['jam_masuk'] and not existing['jam_keluar']:
        # Scan kedua hari ini -> catat jam pulang.
        conn.execute(
            'UPDATE absensi SET jam_keluar=? WHERE id=?', (jam, existing['id'])
        )
        conn.commit()
        if whatsapp:
            message = (
                f"PEMBERITAHUAN ABSENSI SEKOLAH\n\n"
                f"Nama: {siswa['nama']}\nNISN: {siswa['nisn']}\nKelas: {siswa['kelas']}\n"
                f"Status: PULANG\nTanggal: {current.strftime('%d-%m-%Y')}\nJam pulang: {jam}\n\n"
                f"Pesan ini dikirim otomatis oleh sistem absensi sekolah."
            )
            wa_result = send_whatsapp(whatsapp, message)
        conn.close()
        return jsonify({
            'success': True, 'code': 'CHECKOUT_RECORDED',
            'message': f"Absensi pulang {siswa['nama']} berhasil dicatat pada {jam}.",
            'student': {'nisn': siswa['nisn'], 'nama': siswa['nama'], 'kelas': siswa['kelas']},
            'attendance': {'tanggal': tanggal, 'jam_masuk': existing['jam_masuk'], 'jam_keluar': jam, 'status': 'Hadir'},
            'whatsapp': wa_result,
        })

    if not existing['jam_masuk'] and existing['status'] in ('Izin', 'Sakit', 'Alpa'):
        # Admin sudah mencatat status manual (mis. Izin), tapi siswa ternyata datang & scan.
        # Scan fisik dianggap sumber kebenaran -> timpa jadi Hadir dengan jam masuk sebenarnya.
        conn.execute(
            '''UPDATE absensi SET jam_masuk=?, status='Hadir', device_id=?, dicatat_oleh='scan'
               WHERE id=?''',
            (jam, device_label, existing['id'])
        )
        conn.commit()
        conn.close()
        return jsonify({
            'success': True, 'code': 'ATTENDANCE_RECORDED',
            'message': f"{siswa['nama']} ternyata hadir, status diperbarui dari '{existing['status']}' menjadi Hadir pada {jam}.",
            'student': {'nisn': siswa['nisn'], 'nama': siswa['nama'], 'kelas': siswa['kelas']},
            'attendance': {'tanggal': tanggal, 'jam_masuk': jam, 'jam_keluar': None, 'status': 'Hadir'},
        }), 201

    # Sudah lengkap (masuk & pulang tercatat), atau kasus lain.
    conn.close()
    return jsonify({
        'success': True, 'code': 'ALREADY_COMPLETE',
        'message': f"{siswa['nama']} sudah tercatat lengkap hari ini (masuk {existing['jam_masuk'] or '-'}, "
                    f"pulang {existing['jam_keluar'] or '-'}).",
        'student': dict(siswa), 'attendance': dict(existing),
    })


@app.get('/api/attendance/today')
@login_required
def attendance_today():
    tanggal = request.args.get('tanggal', now_local().strftime('%Y-%m-%d'))
    conn = db()
    rows = conn.execute('''
        SELECT a.id, a.tanggal, a.jam_masuk, a.jam_keluar, a.status, a.kelas, a.device_id,
               s.nisn, s.nama
        FROM absensi a JOIN siswa s ON s.id=a.siswa_id
        WHERE a.tanggal=?
        ORDER BY COALESCE(a.jam_masuk, '99:99:99') ASC
    ''', (tanggal,)).fetchall()
    conn.close()
    return jsonify({'date': tanggal, 'data': [dict(r) for r in rows]})


@app.post('/admin/siswa')
@login_required
def add_student():
    nisn = request.form.get('nisn', '').strip()
    nama = request.form.get('nama', '').strip()
    kelas = request.form.get('kelas', '').strip()
    wa = request.form.get('whatsapp_ortu', '').strip()
    if not nisn or not nama or not kelas:
        flash('NISN, nama, dan kelas wajib diisi.', 'error')
        return redirect(url_for('home'))
    conn = db()
    try:
        conn.execute(
            'INSERT INTO siswa (nisn,nama,kelas,whatsapp_ortu,created_at) VALUES (?,?,?,?,?)',
            (nisn, nama, kelas, wa, now_local().isoformat())
        )
        conn.commit()
        flash('Siswa berhasil ditambahkan.', 'success')
    except sqlite3.IntegrityError:
        flash('NISN sudah terdaftar.', 'error')
    finally:
        conn.close()
    return redirect(url_for('home'))


@app.post('/admin/siswa/<int:siswa_id>/toggle')
@login_required
def toggle_student(siswa_id):
    conn = db()
    row = conn.execute('SELECT aktif FROM siswa WHERE id=?', (siswa_id,)).fetchone()
    if row:
        conn.execute('UPDATE siswa SET aktif=? WHERE id=?', (0 if row['aktif'] else 1, siswa_id))
        conn.commit()
    conn.close()
    return redirect(url_for('home'))


@app.post('/admin/status')
@login_required
def set_manual_status():
    """Admin mencatat status non-scan: Izin / Sakit / Alpa / atau Hadir manual untuk tanggal tertentu."""
    siswa_id = request.form.get('siswa_id', type=int)
    tanggal = request.form.get('tanggal', '').strip()
    status = request.form.get('status', '').strip()
    keterangan = request.form.get('keterangan', '').strip()

    valid_status = {'Izin', 'Sakit', 'Alpa', 'Hadir'}
    if not siswa_id or not tanggal or status not in valid_status:
        flash('Data status tidak lengkap/valid.', 'error')
        return redirect(url_for('home', tanggal=tanggal or None))

    conn = db()
    siswa = conn.execute('SELECT * FROM siswa WHERE id=?', (siswa_id,)).fetchone()
    if not siswa:
        conn.close()
        flash('Siswa tidak ditemukan.', 'error')
        return redirect(url_for('home'))

    try:
        tgl_dt = datetime.strptime(tanggal, '%Y-%m-%d').replace(tzinfo=LOCAL_TZ)
    except ValueError:
        conn.close()
        flash('Format tanggal tidak valid.', 'error')
        return redirect(url_for('home'))
    tahun_ajaran, semester = tahun_ajaran_dan_semester(tgl_dt)

    existing = conn.execute(
        'SELECT * FROM absensi WHERE siswa_id=? AND tanggal=?', (siswa_id, tanggal)
    ).fetchone()

    dicatat_oleh = f'admin:{current_user.username}'
    if existing:
        # Jangan timpa jam_masuk/jam_keluar yang sudah tercatat dari scan asli;
        # hanya perbarui status & keterangan.
        conn.execute(
            'UPDATE absensi SET status=?, keterangan=?, dicatat_oleh=? WHERE id=?',
            (status, keterangan or None, dicatat_oleh, existing['id'])
        )
    else:
        conn.execute(
            '''INSERT INTO absensi
               (siswa_id, tanggal, jam_masuk, jam_keluar, status, kelas, tahun_ajaran, semester,
                keterangan, dicatat_oleh, created_at)
               VALUES (?,?,NULL,NULL,?,?,?,?,?,?,?)''',
            (siswa_id, tanggal, status, siswa['kelas'], tahun_ajaran, semester,
             keterangan or None, dicatat_oleh, now_local().isoformat())
        )
    conn.commit()
    conn.close()
    flash(f'Status {status} untuk {siswa["nama"]} pada {tanggal} disimpan.', 'success')
    return redirect(url_for('home', tanggal=tanggal))


@app.get('/admin/export')
@login_required
def export_rekap():
    from csv import writer
    from io import StringIO
    tanggal = request.args.get('tanggal', now_local().strftime('%Y-%m-%d'))
    conn = db()
    rows = conn.execute('''
        SELECT s.nisn, s.nama, a.kelas, a.tanggal, a.jam_masuk, a.jam_keluar, a.status,
               a.tahun_ajaran, a.semester, a.keterangan
        FROM absensi a JOIN siswa s ON s.id=a.siswa_id WHERE a.tanggal=?
        ORDER BY COALESCE(a.jam_masuk, '99:99:99')
    ''', (tanggal,)).fetchall()
    conn.close()
    out = StringIO()
    w = writer(out)
    w.writerow(['NISN', 'Nama', 'Kelas', 'Tanggal', 'Jam Masuk', 'Jam Pulang', 'Status', 'Tahun Ajaran', 'Semester', 'Keterangan'])
    for r in rows:
        w.writerow([r['nisn'], r['nama'], r['kelas'], r['tanggal'], r['jam_masuk'] or '', r['jam_keluar'] or '',
                    r['status'], r['tahun_ajaran'], r['semester'], r['keterangan'] or ''])
    from flask import Response
    return Response(out.getvalue(), mimetype='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="absensi-{tanggal}.csv"'
    })


# Alias lama tetap berfungsi (dulu hanya untuk hari ini).
@app.get('/admin/export-today')
@login_required
def export_today():
    return redirect(url_for('export_rekap', tanggal=now_local().strftime('%Y-%m-%d')))


# --------------------------------------------------------------------------
# Manajemen perangkat (API key untuk /scan)
# --------------------------------------------------------------------------

@app.post('/admin/devices')
@login_required
def add_device():
    nama_perangkat = request.form.get('nama_perangkat', '').strip()
    if not nama_perangkat:
        flash('Nama perangkat wajib diisi.', 'error')
        return redirect(url_for('home'))
    api_key = secrets.token_hex(16)
    conn = db()
    conn.execute(
        'INSERT INTO devices (nama_perangkat, api_key, aktif, created_at) VALUES (?,?,1,?)',
        (nama_perangkat, api_key, now_local().isoformat())
    )
    conn.commit()
    conn.close()
    flash(f'Perangkat "{nama_perangkat}" ditambahkan. Kode API: {api_key} (salin & masukkan ke aplikasi Android sekarang, kode ini tidak ditampilkan lagi).', 'success')
    return redirect(url_for('home'))


@app.post('/admin/devices/<int:device_id>/toggle')
@login_required
def toggle_device(device_id):
    conn = db()
    row = conn.execute('SELECT aktif FROM devices WHERE id=?', (device_id,)).fetchone()
    if row:
        conn.execute('UPDATE devices SET aktif=? WHERE id=?', (0 if row['aktif'] else 1, device_id))
        conn.commit()
    conn.close()
    return redirect(url_for('home'))


@app.get('/api/qr/<nisn>')
@login_required
def qr_payload(nisn):
    conn = db()
    row = conn.execute('SELECT nisn,nama,kelas FROM siswa WHERE nisn=? AND aktif=1', (nisn,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'success': False, 'message': 'Siswa tidak ditemukan.'}), 404
    return jsonify({'success': True, 'qr_value': row['nisn'], 'student': dict(row)})


if __name__ == '__main__':
    init_db()
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', '5000'))
    app.run(host=host, port=port, debug=False)

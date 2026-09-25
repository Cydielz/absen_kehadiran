# Backend Absensi Siswa

## 1. Jalankan di Windows/Python
```bat
cd backend
\.venv\Scripts\Activate.ps1
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python seed.py
python app.py
```

`seed.py` akan membuat:
- akun admin panel (username + password acak dicetak di terminal — **catat saat itu juga**, tidak ditampilkan lagi);
- satu perangkat scanner contoh beserta kode API-nya (`X-Device-Key`), untuk uji coba `/scan`.

Server mendengarkan pada `http://0.0.0.0:5000`. Dari HP di Wi-Fi yang sama, gunakan alamat laptop, misalnya `http://192.168.1.10:5000`.

**Sebelum dipakai di sekolah:** buka `.env` dan ganti `FLASK_SECRET_KEY` dengan string acak yang panjang (jangan biarkan nilai `ganti-...`). Kalau tidak diganti, server tetap jalan tapi mencetak peringatan dan memakai kunci sementara yang membuat semua orang ter-logout tiap restart.

## 2. Login admin
Semua halaman `/` dan `/admin/*` sekarang **wajib login** (Flask-Login). Buka `http://IP-SERVER:5000/login`, masukkan username & password dari output `seed.py`.

**Lupa password admin?** Jalankan `python reset_admin.py` dari folder `backend` (venv aktif), ikuti instruksi di layar untuk memasukkan password baru. Tidak perlu hapus database atau kehilangan data siswa/absensi.

## 3. Perangkat scanner (X-Device-Key)
`POST /scan` sekarang **wajib** header `X-Device-Key` yang cocok dengan salah satu perangkat aktif di tabel `devices`. Cara menambah perangkat baru:
1. Login ke panel admin.
2. Di kartu **"Perangkat Scanner"**, isi nama perangkat lalu klik **Buat Perangkat & Kode Baru**.
3. Kode API hanya ditampilkan sekali di notifikasi hijau — salin, lalu tempel ke aplikasi Android pada kolom **"Kode Perangkat"**.
4. Kalau kode hilang, nonaktifkan perangkat lama dan buat yang baru (jangan pernah membagikan kode yang sama ke banyak HP kalau ingin bisa melacak/mencabut akses per HP).

## 4. Konfigurasi Fonnte
Atur `FONNTE_TOKEN` pada `.env` server. Jangan masukkan token ke APK — backend yang memanggil Fonnte, bukan aplikasi Android.

## 5. Endpoint scan
`POST /scan` (header wajib: `X-Device-Key: <kode perangkat>`)
```json
{"nisn":"0012345678","device_id":"HP-ABSEN-01"}
```

Alur sekarang mendukung masuk **dan** pulang:
- scan pertama pada suatu tanggal → mencatat `jam_masuk`, status `Hadir`, kirim WA "masuk";
- scan kedua pada tanggal yang sama → mencatat `jam_keluar`, kirim WA "pulang";
- scan ketiga dst → server menjawab `ALREADY_COMPLETE`, tidak menulis apa pun lagi;
- kalau admin sudah mencatat status manual (Izin/Sakit/Alpa) tapi siswa ternyata datang & scan, status otomatis diperbarui jadi `Hadir` dengan jam masuk sebenarnya.

Tanpa `X-Device-Key` yang valid, endpoint membalas `401 DEVICE_UNAUTHORIZED` dan tidak menyentuh database. Endpoint ini juga dibatasi 30 request/menit per IP untuk memperlambat percobaan tebak-tebak NISN.

## 6. Status kehadiran manual (Izin/Sakit/Alpa)
Di panel admin, kartu **"Catat Status Manual"** memungkinkan admin mencatat status untuk siswa yang tidak scan, termasuk tanggal lampau. Kalau siswa itu sudah punya baris absensi asli (ada `jam_masuk`), status boleh dikoreksi tapi jam masuk/pulang asli tidak ditimpa.

## 7. Rekap & export
- Panel admin sekarang punya pemilih tanggal untuk melihat rekap hari mana pun, bukan cuma hari ini.
- `GET /admin/export?tanggal=YYYY-MM-DD` — export CSV rekap tanggal tersebut (kolom kelas, tahun ajaran, dan semester adalah **snapshot** saat absensi dicatat, bukan data siswa saat ini — jadi tetap akurat meski siswa sudah naik kelas).
- `GET /admin/export-today` tetap ada sebagai alias ke rekap hari ini.
- `GET /api/attendance/today?tanggal=YYYY-MM-DD` — versi JSON, juga wajib login.

## 8. Database
SQLite dibuat otomatis dengan nama `sekolah.db`. Menjalankan `init_db()` pada database lama (dibuat sebelum update ini) akan otomatis menambahkan kolom-kolom baru (`jam_keluar`, `kelas`, `tahun_ajaran`, `semester`, `keterangan`, `dicatat_oleh`) lewat migrasi ringan — tidak perlu hapus database lama.

## Jika muncul "Internal Server Error" di Windows

Paket ini sudah menambahkan `tzdata` dan fallback UTC+09:00 agar zona waktu `Asia/Jayapura` tidak menyebabkan Flask HTTP 500 pada Windows. Setelah mengganti file, jalankan ulang:

```bat
cd backend
.venv\Scripts\activate
pip install -r requirements.txt
py seed.py
py app.py
```

Tes di laptop dengan membuka `http://127.0.0.1:5000/api/health`. Jika berhasil, browser akan menampilkan JSON dengan `"ok": true`.

## Yang belum dibenahi (di luar permintaan kali ini)
- Trafik masih HTTP biasa (bukan HTTPS) — disarankan pasang reverse proxy (Nginx/Caddy) kalau server akan diakses di luar LAN sekolah.
- Belum ada backup otomatis untuk `sekolah.db`.
- Notifikasi WA yang gagal terkirim belum punya antrian retry — kolom `whatsapp` di respons `/scan` menunjukkan status kirim, tapi kalau gagal, admin harus tahu dari situ (belum ada pencatatan status kirim di database).

-- Schema referensi. Aplikasi Flask membuat tabel ini otomatis saat pertama kali dijalankan (init_db()).
-- File ini hanya dokumentasi struktur database, bukan yang dieksekusi langsung oleh app.

CREATE TABLE IF NOT EXISTS siswa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nisn TEXT NOT NULL UNIQUE,
    nama TEXT NOT NULL,
    kelas TEXT NOT NULL,
    whatsapp_ortu TEXT,
    aktif INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- Absensi kini menyimpan jam_keluar, snapshot kelas & tahun ajaran saat kejadian,
-- serta status non-hadir (Izin/Sakit/Alpa) yang bisa diinput manual oleh admin.
CREATE TABLE IF NOT EXISTS absensi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    siswa_id INTEGER NOT NULL,
    tanggal TEXT NOT NULL,
    jam_masuk TEXT,
    jam_keluar TEXT,
    status TEXT NOT NULL DEFAULT 'Hadir',      -- Hadir | Izin | Sakit | Alpa
    kelas TEXT NOT NULL,                       -- snapshot kelas siswa saat dicatat (bukan referensi ke siswa.kelas)
    tahun_ajaran TEXT NOT NULL,                -- contoh: 2026/2027
    semester TEXT NOT NULL,                    -- Ganjil | Genap
    keterangan TEXT,
    device_id TEXT,
    dicatat_oleh TEXT,                         -- 'scan' atau 'admin:<username>'
    created_at TEXT NOT NULL,
    FOREIGN KEY(siswa_id) REFERENCES siswa(id) ON DELETE CASCADE,
    UNIQUE(siswa_id, tanggal)
);

CREATE INDEX IF NOT EXISTS idx_absensi_tanggal ON absensi(tanggal);
CREATE INDEX IF NOT EXISTS idx_siswa_nisn ON siswa(nisn);

-- Akun admin panel (login wajib untuk semua route /admin/* dan halaman utama).
CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Whitelist perangkat yang boleh memanggil POST /scan.
-- Admin membuat entri di sini, lalu memasukkan api_key ke aplikasi Android.
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama_perangkat TEXT NOT NULL,
    api_key TEXT NOT NULL UNIQUE,
    aktif INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

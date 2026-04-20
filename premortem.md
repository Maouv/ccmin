# ccmin Premortem — Execution Plan

---

## 1. Symlink corrupt lagi di edge case baru
**Root cause:** Auto-detect broken symlink hanya ada di `--init`, tidak di launch biasa. User tidak tau `--repair` exist.
**File:** `ccmin/ccmin.py` → `cmd_launch()`
**Fix:** Cek `is_symlink() and not exists()` di awal `cmd_launch`, print pesan jelas dan exit dengan instruksi `python3 ccmin/ccmin.py --repair`.

---

## 2. Launcher custom tidak divalidasi
**Root cause:** Wizard terima input apapun tanpa cek apakah launcher-nya executable. Silent fail saat launch.
**File:** `ccmin/ccmin.py` → `cmd_init()`
**Fix:** Tambah `shutil.which(launcher)` setelah user input. Kalau `None`, warn dan minta input ulang.

---

## 3. Backup terlama terhapus diam-diam
**Root cause:** `backup_limit=10` hapus backup terlama tanpa warning. User tidak bisa rollback jauh.
**File:** `ccmin/core/backup.py`
**Fix:** Sebelum hapus, print "⚠ Oldest backup will be removed" dan jumlah backup yang tersisa.

---

## 4. Prompt outdated setelah update repo
**Root cause:** `~/.ccmin/minimal-prompt.txt` tidak ter-update otomatis saat user pull repo baru. Model jalan dengan prompt lama tanpa ada warning.
**File:** `ccmin/ccmin.py` → `cmd_launch()`
**Fix:** Bandingkan checksum `~/.ccmin/minimal-prompt.txt` vs `templates/minimal-prompt.txt` saat launch. Kalau beda, warn: "⚠ Prompt outdated, run ccmin --init to update".

---

## 5. Custom tools format salah, silent fail
**Root cause:** Mode 3 (custom) wizard tidak validasi format input. `bash(git*)` tanpa kapital atau spasi diterima tapi tidak jalan sesuai ekspektasi.
**File:** `ccmin/ccmin.py` → `cmd_init()`
**Fix:** Normalize input (strip whitespace), warn kalau ada tool yang format-nya mencurigakan (lowercase, tanpa kurung, dll).

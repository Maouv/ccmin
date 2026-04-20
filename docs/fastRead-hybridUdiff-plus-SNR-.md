```markdown
# Plan: Fast Read + udiff + Search/Replace Fallback

## Overview
Custom tool system untuk ccmin yang replace built-in Read/Edit Claude Code.
Goal: hemat token, tetap reliable, support batch edit.

---

## Tools

### `fast_read`
- Full read sekali per sesi per file
- Support line range: `fast_read(file, lines=10:50)`
- Support keyword search: `fast_read(file, search="def my_func")`
- Return content + file hash + timestamp
- Track file mana yang sudah di-read beserta hash-nya

### `fast_edit`
- Single udiff patch
- Validasi hash sebelum apply — reject kalau file sudah berubah
- Return updated line range sebagai shadow memory update
- Fallback ke s&r kalau udiff gagal (user configurable on/off)

### `fast_multi_edit`
- Array of udiff patches
- Apply sequential top-to-bottom
- Script recalculate line offset setelah tiap patch
- Atomic — kalau satu patch gagal, rollback semua perubahan di batch
- Return summary hasil tiap patch

---

## Flow

```

1. fast_read(file)
   → return: content, hash, timestamp

2. Claude generate patch (udiff)

3. fast_edit(file, patch)  /  fast_multi_edit(file, patches[])
   → validate hash
   → apply sequential (multi_edit)
   → return: updated lines sebagai shadow memory

4. Kalau udiff gagal → fallback s&r (kalau enabled)
   → Claude kirim old_string + new_string
   → script apply s&r
```

---

## Mitigasi Risiko

### 1. Patch Mismatch (udiff fragile terhadap whitespace)
- **Risk:** Claude generate context yang salah 1 spasi/tab, patch reject
- **Mitigation:** Fallback otomatis ke s&r kalau udiff fail
- **User config:** fallback s&r bisa di-toggle on/off

### 2. Multi-edit Drift (line numbers geser dalam batch)
- **Risk:** Patch ke-2 dst pakai line numbers stale karena patch ke-1 sudah geser file
- **Mitigation:** Script recalculate offset setelah tiap patch apply, bukan Claude yang hitung

### 3. Partial Apply (batch gagal di tengah)
- **Risk:** 3 dari 5 patch berhasil, file jadi corrupt/setengah-setengah
- **Mitigation:** Atomic batch — backup file sebelum apply, rollback semua kalau ada yang gagal

### 4. External Edit / Stale Shadow Memory
- **Risk:** User edit file manual di luar ccmin, shadow memory Claude stale, patch apply ke content salah
- **Mitigation:** Checksum validation wajib sebelum setiap apply. Hash mismatch → auto reject, prompt re-read

### 5. Sesi Panjang / Memory Drift
- **Risk:** Claude "lupa" content file di sesi panjang, generate patch dari memori yang drift
- **Mitigation:** Shadow memory di-update setiap setelah edit. Timestamp read di-track, warn kalau terlalu lama

### 6. Multiple File Confusion
- **Risk:** Claude campur aduk content antar file kalau banyak file di-read dalam satu sesi
- **Mitigation:** Script track semua file yang sudah di-read + hash-nya, return sebagai context header

### 7. Large File
- **Risk:** Full read file besar flood context window, kontraproduktif
- **Mitigation:** Default fast_read pakai line range, full read hanya kalau user explicit minta

---

## User Configurable
- Fallback s&r: on/off
- Context lines di udiff: default 1-2 baris
- Force re-read threshold: berapa lama sebelum warn stale

---

## Status
- [ ] fast_read implementation
- [ ] fast_edit implementation  
- [ ] fast_multi_edit implementation
- [ ] Checksum validation
- [ ] Atomic rollback
- [ ] Shadow memory update
- [ ] s&r fallback
- [ ] User config toggle

---

## Tools Integration

### Cara Claude Tau Tools Ini Ada
Tools didokumentasikan di `minimal-prompt.txt` langsung — format input/output, kapan pakai fast_read vs fast_edit vs fast_multi_edit, dan rules penggunaan (read once, jangan re-read kecuali hash mismatch).

Contoh section yang ditambah ke `minimal-prompt.txt`:
```

# Custom Tools
- fast_read: Bash(python3 ~/.ccmin/tools/fast_read.py <file> [lines=N:M] [search=keyword])
- fast_edit: Bash(python3 ~/.ccmin/tools/fast_edit.py <file> <patch>)
- fast_multi_edit: Bash(python3 ~/.ccmin/tools/fast_multi_edit.py <file> <patches_json>)

Rules:
- Read file SEKALI per sesi. Jangan re-read kecuali dapat pesan hash mismatch.
- Setelah edit, gunakan shadow memory dari konfirmasi tool — jangan re-read.
- Untuk edit kecil gunakan fast_edit, untuk batch gunakan fast_multi_edit.
```

Tools di-allow di `settings.json`:
```json
"allow": [
  "Bash(python3 ~/.ccmin/tools/fast_read.py *)",
  "Bash(python3 ~/.ccmin/tools/fast_edit.py *)",
  "Bash(python3 ~/.ccmin/tools/fast_multi_edit.py *)"
]
```

# Plan: Repo Map

## Overview
Generate lightweight map struktur project yang di-inject ke system prompt saat launch.
Goal: Claude punya context struktur file tanpa perlu explore sendiri, hemat token di sesi panjang.

---

## Config (di ~/.ccmin/config.json)
```json
{
  "repo_map": {
    "enabled": false,
    "max_tokens": 1024,
    "exclude": ["node_modules", ".git", "dist", "build", "__pycache__", "*.pyc"]
  }
}
```

Saat `--init` wizard tanya:
- Enable repo map? y/n
- Max tokens? (default 1024)

---

## Cara Kerja

```
1. Launch ccmin
2. Cek hash directory structure
3. Kalau hash sama dengan cache → pakai cached map
4. Kalau hash beda → regenerate map, update cache
5. Trim map ke max_tokens secara hierarchical
6. Inject ke system prompt
```

---

## Format Map
```
project/
├── src/
│   ├── main.py        # entry point
│   ├── config.py
│   └── utils/
│       └── helpers.py
├── tests/
│   └── test_main.py
└── README.md
```

Simple tree structure, no file content — hanya struktur dan nama file.

---

## Trim Strategy (Hierarchical)
Kalau map melebihi max_tokens:
1. Prioritas file di cwd level pertama
2. Lalu subfolder satu level
3. Potong dari subfolder paling jauh dari cwd
4. Jangan potong di tengah entry — selalu complete per folder

---

## Mitigasi Risiko

### 1. Flood Context Window
- **Risk:** Map terlalu besar, habiskan token budget sebelum Claude mulai kerja
- **Mitigation:** Hard cap max_tokens dari config, trim hierarchical sebelum inject

### 2. Stale Map
- **Risk:** File baru ditambah/dihapus, map tidak di-update, Claude salah referensi
- **Mitigation:** Hash directory structure saat launch, regenerate kalau hash berubah

### 3. Token Cutoff Tidak Graceful
- **Risk:** Map terpotong di tengah entry, Claude dapat info incomplete
- **Mitigation:** Trim per folder unit, bukan hard cut di karakter — map lebih pendek tapi selalu complete

### 4. Generate Lambat di Project Besar
- **Risk:** Tiap launch harus generate ulang, UX buruk
- **Mitigation:** Cache map ke `~/.ccmin/repo-map-cache.json`, hanya regenerate kalau hash berubah

### 5. Irrelevant Content
- **Risk:** Map include node_modules, build artifacts, buang token
- **Mitigation:** Respect `.gitignore` + configurable exclude list di config.json

---

## User Configurable
- Enable/disable repo map
- max_tokens (default 1024)
- Exclude patterns (tambahan di atas .gitignore)

---

## Status
- [ ] Hash-based cache system
- [ ] Tree generator (respect .gitignore + exclude)
- [ ] Hierarchical trim ke max_tokens
- [ ] Inject ke system prompt saat launch
- [ ] --init wizard integration
- [ ] config.json schema update


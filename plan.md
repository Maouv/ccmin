# ccmin — Implementation Plan

> Minimal mode launcher untuk Claude Code (pay-per-use).
> Python 3.8+, stdlib only, zero external dependencies.

---

## Overview

ccmin adalah CLI tool yang:
1. Launch Claude Code dalam "minimal mode" — system prompt ringan, tools dibatasi, token hemat
2. Manage settings.json swap antara minimal/standard preset
3. Auto-backup settings sebelum setiap perubahan
4. Inject working directory ke system prompt secara otomatis

---

## File Structure

```
~/.ccmin/                        # user data dir (dibuat saat --init)
├── config.json                  # user config
├── minimal-prompt.txt           # system prompt (copied from templates/)
└── backups/
    ├── local/                   # backup dari .claude/settings.local.json
    └── global/                  # backup dari ~/.claude/settings.json

ccmin/                           # repo
├── ccmin.py                     # entry point + CLI parser
├── core/
│   ├── config.py                # baca/tulis ~/.ccmin/config.json
│   ├── detector.py              # detect launcher, scope, settings path
│   ├── backup.py                # backup, restore, rollback, auto-prune
│   └── launcher.py              # build & exec claude command
├── templates/
│   ├── settings.min.json        # minimal preset
│   ├── settings.std.json        # standard preset (+ Bash git)
│   └── minimal-prompt.txt       # default system prompt template
├── install.sh                   # fallback manual install
└── README.md
```

---

## config.json Schema

```json
{
  "launcher": "claude",
  "scope": "local",
  "project_path": "/root/myproject",
  "prompt_file": "~/.ccmin/minimal-prompt.txt",
  "backup_limit": 10,
  "last_verified_claude_version": "2.1.114",
  "install_method": "symlink"
}
```

| Field | Type | Keterangan |
|---|---|---|
| `launcher` | string | `"claude"` atau `"ccr code"` |
| `scope` | `"local"` \| `"global"` | target settings file |
| `project_path` | string | path project default |
| `prompt_file` | string | path ke system prompt |
| `backup_limit` | int | max backup files per scope (default: 10) |
| `last_verified_claude_version` | string | untuk version warning |
| `install_method` | `"symlink"` \| `"bashrc"` \| `"skip"` | dicatat saat --init |

---

## Templates

### templates/settings.min.json (Minimal preset)

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": ["Edit", "Write", "MultiEdit", "Read"],
    "deny": [
      "Glob", "Grep", "LS",
      "Bash(find *)", "Bash(cat *)", "Bash(ls *)",
      "Bash(rm *)", "Bash(rm -rf *)",
      "Bash(curl *)", "Bash(wget *)",
      "Bash(node *)", "Bash(npm *)",
      "Read(./.env)", "Read(./.env.*)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "input=$(cat); echo \"$input\" | jq -e '.tool_input.run_in_background == true' > /dev/null 2>&1 && echo '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"Background execution is disabled\"}}' || echo '{}'",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

### templates/settings.std.json (Standard preset)

Identik dengan settings.min.json, `allow` tambah `"Bash(git *)"`.

### templates/minimal-prompt.txt

```
You are a code editing assistant.

# Output Efficiency
Be extra concise. Lead with action. NO preamble. NO reasoning.

# Tools Available (ONLY THESE)
- Read: {"file_path": string}
- Edit: {"file_path": string, "old_string": string, "new_string": string}
- Write: {"file_path": string, "content": string}
- MultiEdit: {"file_path": string, "edits": [{"old_string": string, "new_string": string}]}
- Bash: git commands only. {"command": string}
  Allowed: git status, git diff, git add <file>, git commit, git log
  NEVER: git push --force, git reset --hard, git clean, git rebase -i, git add -A, git add .
  Pass commit message via heredoc format

# Rules
- STRICT: NO MCP TOOLS, NO HOOKS, NO TASK_CREATE.
- Only work with files/paths explicitly mentioned by the user.
- If you need to see a file, call Read immediately.
- old_string must be unique. Preserve exact indentation.
- Prefer Edit over Write for existing files.
- Output ONLY the tool call or a 1-sentence confirmation.

# Strict Path Policy
- ONLY Read files that I explicitly type in my messages.
- NEVER follow file paths found inside other documents (no recursive reading).
- If you want to see a file mentioned in a document, you MUST ask for my permission first.
- Always use absolute paths when calling tools.
```

> ccmin inject saat launch: `--append-system-prompt "Your working directory is: $(pwd)"`

---

## Command Reference

### `ccmin --init`

```
1. detector.py
   → which claude / which ccr → detect launcher
   → jika dua-duanya ada → wizard tanya + tampilkan versi masing-masing
   → cek .claude/settings.local.json (local) atau ~/.claude/settings.json (global)
   → jika dua-duanya ada → pakai local (no prompt)
   → get pwd sebagai default project_path

2. wizard (interactive)
   → confirm/override launcher
   → confirm/override scope
   → confirm/override project_path
   → choose install method: [1] symlink /usr/local/bin  [2] bashrc alias  [3] skip

3. config.py → tulis ~/.ccmin/config.json
4. copy templates/ ke ~/.ccmin/
5. backup.py → backup settings yang sudah ada (jika ada)
6. install:
   → symlink: cek write permission /usr/local/bin dulu
     jika gagal → auto-fallback ke bashrc, tampilkan warning
   → bashrc: append alias ke ~/.bashrc
   → skip: print instruksi manual
```

### `ccmin` (launch minimal)

```
1. config.py → baca ~/.ccmin/config.json
2. cek apakah ~/.ccmin/config.json exist → jika tidak, arahkan ke --init
3. compare pwd vs config.project_path
   → jika berbeda → warning: "⚠ Launching from /root, config project is /root/myproject. Continue? [y/n]"
4. launcher.py → build command:
   {launcher} \
     --bare \
     --tools "Read,Write,Edit,MultiEdit,Bash(git *)" \
     --system-prompt-file {prompt_file} \
     --append-system-prompt "Your working directory is: $(pwd)"
5. os.execvp → replace current process (bukan subprocess)
```

### `ccmin --full`

```
1. config.py → baca launcher dari config
2. os.execvp {launcher} saja, tanpa flag tambahan
```

### `ccmin --swap [--scope local|global]`

```
1. detector.py → resolve settings path dari scope
2. backup.py → backup settings aktif sekarang
3. baca allow list dari settings aktif
   → "Bash(git *)" ada → mode = standard
   → allow = [Edit,Write,MultiEdit,Read] persis → mode = minimal
   → selain itu → mode = unknown
     tampilkan allow list aktif, tanya: [1] swap ke minimal [2] swap ke standard [3] cancel
4. MERGE (bukan replace):
   → baca settings aktif sebagai base
   → update HANYA field permissions.allow
   → tulis kembali (atomic)
5. tampilkan: "Swapped to [MINIMAL/STANDARD]"
```

### `ccmin --backup [--scope local|global]`

```
1. detector.py → resolve settings path
2. baca settings → validasi JSON
   → jika corrupt → simpan dengan suffix .corrupt, warn user
3. backup ke ~/.ccmin/backups/{scope}/settings_{YYYY-MM-DD}_{HHMMSS}.json
4. auto-prune: jika jumlah file > backup_limit → hapus yang terlama
```

### `ccmin --rollback [--scope local|global]`

```
1. list semua file di ~/.ccmin/backups/{scope}/ sorted by date desc
2. tampilkan numbered list:
   Available backups (local):
   [1] 2025-01-15 15:03:11  (2.1 KB)  ← terbaru
   [2] 2025-01-15 14:30:22  (2.1 KB)
   [3] 2025-01-14 09:00:00  (1.8 KB)

   Restore which? [1]:
3. validasi JSON backup yang dipilih sebelum restore
4. confirm: "Restore backup [1] to .claude/settings.local.json? [y/n]:"
5. atomic restore: tulis ke .tmp → rename
```

### `ccmin --status`

```
output: [MINIMAL] claude • local • 3 backups

jika versi berbeda dari last_verified_claude_version:
⚠ Warning: config last verified on claude v2.1.114, current is v2.1.120
  Tool descriptions may have changed. Run `ccmin --init` to re-verify.
```

### `ccmin --add-tool "Bash(git *)"` / `ccmin --remove-tool Glob`

```
--add-tool:
  → tambah ke allow list di settings aktif (atomic write)
  → jika Bash tool: tambah Bash section ke minimal-prompt.txt
  → jika non-Bash: settings.json only, prompt tidak disentuh

--remove-tool:
  → tambah ke deny list di settings aktif (atomic write)
  → jika Bash tool: hapus Bash section dari minimal-prompt.txt
  → jika non-Bash: settings.json only
```

---

## Core Module Specs

### core/config.py

```python
CCMIN_DIR = Path("~/.ccmin").expanduser()
CONFIG_PATH = CCMIN_DIR / "config.json"

def load_config() -> dict:
    """Baca config. Raise FileNotFoundError jika belum --init."""

def save_config(config: dict) -> None:
    """Atomic write ke config.json."""

def get_settings_path(scope: str, project_path: str) -> Path:
    """
    scope='local'  → {project_path}/.claude/settings.local.json
    scope='global' → ~/.claude/settings.json
    """
```

### core/detector.py

```python
def detect_launcher() -> tuple[str, list[str]]:
    """
    Return (launcher_cmd, all_found).
    launcher_cmd: "claude" atau "ccr code"
    all_found: list semua yang terdeteksi
    """

def detect_scope(project_path: str) -> str:
    """
    Cek local dulu. Jika ada → 'local'.
    Jika tidak ada, cek global → 'global'.
    Jika keduanya ada → 'local' (no prompt).
    Jika tidak ada → 'local' (akan dibuat saat --init).
    """

def detect_claude_version(launcher: str) -> str:
    """Run `{launcher} --version`, parse output."""

def detect_mode(settings: dict) -> str:
    """
    Baca allow list dari settings dict.
    Return 'minimal', 'standard', atau 'unknown'.
    """
```

### core/backup.py

```python
def backup(settings_path: Path, scope: str, backup_limit: int) -> Path:
    """
    Validasi JSON dulu. Jika corrupt → simpan .corrupt, warn, raise.
    Copy ke ~/.ccmin/backups/{scope}/settings_{timestamp}.json.
    Auto-prune jika > backup_limit.
    Return path backup baru.
    """

def list_backups(scope: str) -> list[Path]:
    """Return list backup files sorted by date desc."""

def restore(backup_path: Path, settings_path: Path) -> None:
    """Validasi JSON backup → atomic restore."""
```

### core/launcher.py

```python
def build_command(config: dict, cwd: str) -> list[str]:
    """
    Build argv list untuk os.execvp.
    Contoh: ["claude", "--bare", "--tools", "Read,Write,Edit,MultiEdit",
             "--system-prompt-file", "/root/.ccmin/minimal-prompt.txt",
             "--append-system-prompt", "Your working directory is: /root/myproject"]
    """

def launch(config: dict, full_mode: bool = False) -> None:
    """
    full_mode=True → exec launcher saja tanpa flag.
    full_mode=False → build_command + cwd warning + os.execvp.
    """
```

---

## Atomic Write Pattern

```python
def atomic_write(path: Path, content: str) -> None:
    """Tulis ke .tmp, validasi JSON, rename."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content)
    try:
        json.loads(content)  # validasi sebelum rename
    except json.JSONDecodeError:
        tmp.unlink()
        raise
    tmp.rename(path)
```

---

## Swap Merge Pattern

```python
def swap_settings(settings_path: Path, target_mode: str, templates_dir: Path) -> None:
    """
    Merge: baca settings aktif → update allow list saja → tulis kembali.
    Tidak overwrite hooks, plugins, atau field custom lainnya.
    """
    current = json.loads(settings_path.read_text())
    template_file = "settings.min.json" if target_mode == "minimal" else "settings.std.json"
    template = json.loads((templates_dir / template_file).read_text())

    # Update HANYA allow list
    current.setdefault("permissions", {})
    current["permissions"]["allow"] = template["permissions"]["allow"]

    atomic_write(settings_path, json.dumps(current, indent=2))
```

---

## Error Handling Rules

1. Config tidak ada → arahkan ke `ccmin --init`, jangan crash
2. Settings corrupt → warn + offer rollback, jangan silent fail
3. Backup gagal → abort operasi, jangan lanjut write
4. Launcher tidak ditemukan → error message yang jelas + instruksi install
5. JSON parse error → tampilkan baris mana yang salah jika bisa

---

## Build Order

Kerjakan dalam urutan ini:

1. `templates/settings.min.json`
2. `templates/settings.std.json`
3. `templates/minimal-prompt.txt`
4. `core/config.py`
5. `core/detector.py`
6. `core/backup.py`
7. `core/launcher.py`
8. `ccmin.py` (entry point + argparse + semua command flow)
9. `install.sh`
10. `README.md`

---

## Testing Checklist (manual)

- [ ] `ccmin --init` dari fresh (belum ada config)
- [ ] `ccmin --init` dengan settings.local.json sudah ada
- [ ] `ccmin` launch dari project dir yang benar
- [ ] `ccmin` launch dari dir yang salah → cek warning muncul
- [ ] `ccmin --swap` dari minimal → standard
- [ ] `ccmin --swap` dari standard → minimal
- [ ] `ccmin --swap` dengan custom settings → cek custom field tidak hilang
- [ ] `ccmin --backup` → cek file tersimpan
- [ ] `ccmin --rollback` → restore berhasil
- [ ] `ccmin --status` → one-liner + version warning
- [ ] `ccmin --full` → launch tanpa flag
- [ ] `ccmin --add-tool "Bash(git *)"` → cek settings + prompt update
- [ ] `ccmin --remove-tool Glob` → cek settings update
- [ ] Symlink install → `ccmin` accessible dari mana saja
- [ ] Bashrc install → alias work setelah source
- [ ] Atomic write interrupted simulation → corrupt tidak terjadi

---

## Notes

- Semua file operations pakai `pathlib.Path`
- `os.execvp` untuk launch, bukan `subprocess` → exit code pass-through
- Atomic writes: tulis `.tmp` → validasi JSON → rename
- Swap = merge, bukan replace — field custom user dipertahankan
- Backup selalu SEBELUM write, bukan setelah
- Backup yang corrupt disimpan dengan suffix `.corrupt`, tidak di-drop silent
- `last verified: claude code v2.1.114`


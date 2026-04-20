#!/usr/bin/env python3
"""
fast_edit - Token-efficient single-file edit untuk ccmin.

Usage:
  fast_edit.py <file> <patch>               # Apply udiff patch
  fast_edit.py <file> --sr <old> <new>      # Search & Replace langsung

Patch format (udiff):
  @@ -N,M +N,M @@
  -old line
  +new line
   context line

Validasi hash sebelum apply — reject kalau file sudah berubah sejak last read.
Return updated line range sebagai shadow memory hint untuk Claude.
"""

import sys
import os
import json
import hashlib
import re
import shutil
import time
from pathlib import Path

SESSION_FILE = Path(f"/tmp/ccmin-session-{os.getppid()}.json")


def _load_session() -> dict:
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_session(session: dict):
    try:
        SESSION_FILE.write_text(json.dumps(session, indent=2))
    except OSError:
        pass


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _count_tokens_approx(text: str) -> int:
    return len(text) // 4


def apply_search_replace(content: str, old_str: str, new_str: str) -> tuple:
    """Apply search & replace. Return (new_content, success)."""
    if old_str not in content:
        return content, False
    new_content = content.replace(old_str, new_str, 1)
    return new_content, True


def apply_udiff(content: str, patch: str) -> tuple:
    """
    Apply udiff patch ke content string.
    Return (new_content, success, error_msg).
    """
    lines = content.splitlines(keepends=True)
    patch_lines = patch.strip().splitlines()

    # Parse hunk headers
    hunks = []
    i = 0
    while i < len(patch_lines):
        line = patch_lines[i]
        m = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
        if m:
            orig_start = int(m.group(1))
            orig_count = int(m.group(2)) if m.group(2) is not None else 1
            hunk_lines = []
            i += 1
            while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                hunk_lines.append(patch_lines[i])
                i += 1
            hunks.append((orig_start, orig_count, hunk_lines))
        else:
            i += 1

    if not hunks:
        return content, False, "No valid @@ hunk headers found in patch"

    # Apply hunks dari belakang ke depan supaya line numbers tidak drift
    result = list(lines)
    for orig_start, orig_count, hunk_lines in reversed(hunks):
        # Kumpulkan context + removed lines untuk validasi posisi
        expected_context = []
        for hl in hunk_lines:
            if hl.startswith("-") or hl.startswith(" "):
                expected_context.append(hl[1:].rstrip("\n"))

        target_idx = orig_start - 1  # 0-indexed
        search_window = 5  # toleransi drift ±5 baris

        matched = False
        for offset in range(-search_window, search_window + 1):
            idx = target_idx + offset
            if idx < 0 or idx + len(expected_context) > len(result):
                continue
            window = [l.rstrip("\n") for l in result[idx:idx + len(expected_context)]]
            if window == expected_context or \
               [l.strip() for l in window] == [l.strip() for l in expected_context]:
                target_idx = idx
                matched = True
                break

        if not matched:
            return content, False, f"Cannot find context at line {orig_start} (±{search_window})"

        # Bangun replacement lines
        new_lines = []
        context_idx = target_idx
        for hl in hunk_lines:
            if hl.startswith("+"):
                new_lines.append(hl[1:] if hl[1:].endswith("\n") else hl[1:] + "\n")
            elif hl.startswith("-"):
                context_idx += 1  # skip baris ini
            elif hl.startswith(" "):
                if context_idx < len(result):
                    new_lines.append(result[context_idx])
                context_idx += 1

        remove_count = sum(1 for hl in hunk_lines if hl.startswith("-") or hl.startswith(" "))
        result[target_idx:target_idx + remove_count] = new_lines

    return "".join(result), True, ""


def main():
    args = sys.argv[1:]

    if len(args) < 2:
        print("Usage: fast_edit.py <file> <patch>")
        print("       fast_edit.py <file> --sr <old_string> <new_string>")
        sys.exit(1)

    filepath = args[0]
    path = Path(filepath).resolve()

    if not path.exists():
        print(f"[fast_edit] ERROR: File not found: {filepath}")
        sys.exit(1)

    try:
        original_content = path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[fast_edit] ERROR: Cannot read file: {e}")
        sys.exit(1)

    current_hash = _file_hash(path)
    session = _load_session()
    key = str(path)

    # Hash validation
    if key in session:
        cached_hash = session[key]["hash"]
        if cached_hash != current_hash:
            print(f"[fast_edit] HASH MISMATCH: {filepath}")
            print(f"  Expected (from session) : {cached_hash}")
            print(f"  Current                 : {current_hash}")
            print(f"  File was modified externally. Run fast_read to refresh.")
            sys.exit(2)
    else:
        print(f"[fast_edit] Warning: {filepath} not in session (never read via fast_read). Proceeding.")

    # Determine mode
    sr_mode = len(args) >= 2 and args[1] == "--sr"

    if sr_mode:
        if len(args) < 4:
            print("[fast_edit] ERROR: --sr requires <old_string> <new_string>")
            sys.exit(1)
        old_str = args[2]
        new_str = args[3]
        new_content, success = apply_search_replace(original_content, old_str, new_str)
        if not success:
            print(f"[fast_edit] ERROR: old_string not found in {filepath}")
            print("[fast_edit] Tip: old_string harus exact match (termasuk indentation)")
            sys.exit(1)
        method = "search-replace"
    else:
        patch = args[1]
        new_content, success, err = apply_udiff(original_content, patch)

        if not success:
            print(f"[fast_edit] udiff FAILED: {err}")

            # Cek apakah fallback s&r enabled di config
            fallback_enabled = True
            ccmin_config = Path.home() / ".ccmin" / "config.json"
            if ccmin_config.exists():
                try:
                    cfg = json.loads(ccmin_config.read_text())
                    fallback_enabled = cfg.get("fast_edit", {}).get("sr_fallback", True)
                except Exception:
                    pass

            if not fallback_enabled:
                print("[fast_edit] s&r fallback disabled. Edit failed.")
                sys.exit(1)

            print("[fast_edit] Fallback: gunakan --sr mode")
            print("  fast_edit.py <file> --sr '<old_string>' '<new_string>'")
            sys.exit(3)  # exit code 3 = caller harus retry dengan --sr

        method = "udiff"

    # Backup sebelum write
    backup_path = path.with_suffix(path.suffix + ".ccmin-bak")
    try:
        shutil.copy2(path, backup_path)
    except OSError as e:
        print(f"[fast_edit] Warning: backup failed: {e}")

    # Atomic write
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(new_content, encoding="utf-8")
        tmp.rename(path)
    except OSError as e:
        print(f"[fast_edit] ERROR: Write failed: {e}")
        if tmp.exists():
            tmp.unlink()
        sys.exit(1)

    # Update session hash
    new_hash = _file_hash(path)
    new_tokens = _count_tokens_approx(new_content)
    if key not in session:
        session[key] = {}
    session[key]["hash"] = new_hash
    session[key]["ts"] = time.time()
    session[key]["tokens"] = new_tokens
    session[key]["full"] = True
    _save_session(session)

    # Shadow memory: diff baris yang berubah
    orig_lines = original_content.splitlines()
    new_lines_list = new_content.splitlines()
    changed_start = None
    changed_end = None
    for i, (ol, nl) in enumerate(zip(orig_lines, new_lines_list)):
        if ol != nl:
            if changed_start is None:
                changed_start = i + 1
            changed_end = i + 1
    if len(new_lines_list) != len(orig_lines):
        changed_end = max(len(new_lines_list), len(orig_lines))

    shadow = ""
    if changed_start and changed_end:
        snippet = "\n".join(new_lines_list[changed_start - 1:min(changed_end, changed_start + 20)])
        shadow = f"\n[shadow] Updated lines {changed_start}-{changed_end}:\n{snippet}"

    print(f"[fast_edit] OK ({method}): {filepath} | new_hash={new_hash} | tokens≈{new_tokens}{shadow}")


if __name__ == "__main__":
    main()

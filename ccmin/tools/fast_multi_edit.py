#!/usr/bin/env python3
"""
fast_multi_edit - Atomic batch edit untuk ccmin.

Usage:
  fast_multi_edit.py <file> <patches_json>

patches_json format (JSON array of patch strings):
  [
    "@@ -10,3 +10,3 @@\\n-old\\n+new\\n context",
    "@@ -25,2 +25,2 @@\\n-foo\\n+bar"
  ]

Behavior:
- Apply patches sequential top-to-bottom
- Recalculate line offsets setelah tiap patch (tidak drift)
- Atomic: kalau satu patch gagal, rollback semua
- Hash validation sebelum apply
- Return summary hasil tiap patch + shadow memory update
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


def parse_hunks(patch: str) -> list:
    """Parse udiff patch string jadi list of (orig_start, hunk_lines)."""
    patch_lines = patch.strip().splitlines()
    hunks = []
    i = 0
    while i < len(patch_lines):
        m = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', patch_lines[i])
        if m:
            orig_start = int(m.group(1))
            hunk_lines = []
            i += 1
            while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                hunk_lines.append(patch_lines[i])
                i += 1
            hunks.append((orig_start, hunk_lines))
        else:
            i += 1
    return hunks


def apply_single_hunk(lines: list, orig_start: int, hunk_lines: list, offset: int) -> tuple:
    """
    Apply satu hunk ke lines (list of strings).
    offset: akumulasi offset dari patch sebelumnya.
    Return (new_lines, new_offset, success, err_msg, changed_range).
    """
    adjusted_start = orig_start - 1 + offset  # 0-indexed

    # Kumpulkan context untuk validasi
    expected_context = []
    for hl in hunk_lines:
        if hl.startswith("-") or hl.startswith(" "):
            expected_context.append(hl[1:].rstrip("\n"))

    # Fuzzy find dengan toleransi ±5 baris
    search_window = 5
    target_idx = adjusted_start
    matched = False
    for off in range(-search_window, search_window + 1):
        idx = target_idx + off
        if idx < 0 or idx + len(expected_context) > len(lines):
            continue
        window = [l.rstrip("\n") for l in lines[idx:idx + len(expected_context)]]
        if window == expected_context or \
           [l.strip() for l in window] == [l.strip() for l in expected_context]:
            target_idx = idx
            matched = True
            break

    if not matched:
        return lines, offset, False, f"Context not found near line {orig_start + offset} (±{search_window})", None

    # Build replacement
    new_segment = []
    context_ptr = target_idx
    for hl in hunk_lines:
        if hl.startswith("+"):
            new_segment.append(hl[1:] if hl[1:].endswith("\n") else hl[1:] + "\n")
        elif hl.startswith("-"):
            context_ptr += 1  # skip
        elif hl.startswith(" "):
            if context_ptr < len(lines):
                new_segment.append(lines[context_ptr])
            context_ptr += 1

    remove_count = sum(1 for hl in hunk_lines if hl.startswith("-") or hl.startswith(" "))
    added_count = sum(1 for hl in hunk_lines if hl.startswith("+"))
    removed_count = sum(1 for hl in hunk_lines if hl.startswith("-"))

    new_lines = lines[:target_idx] + new_segment + lines[target_idx + remove_count:]

    # Recalculate offset: baris yang ditambah dikurangi baris yang dihapus
    delta = added_count - removed_count
    new_offset = offset + delta

    changed_start = target_idx + 1  # 1-indexed
    changed_end = target_idx + len(new_segment)

    return new_lines, new_offset, True, "", (changed_start, changed_end)


def main():
    args = sys.argv[1:]

    if len(args) < 2:
        print("Usage: fast_multi_edit.py <file> <patches_json>")
        print("  patches_json: JSON array of udiff patch strings")
        sys.exit(1)

    filepath = args[0]
    path = Path(filepath).resolve()

    if not path.exists():
        print(f"[fast_multi_edit] ERROR: File not found: {filepath}")
        sys.exit(1)

    # Parse patches
    try:
        patches = json.loads(args[1])
        if not isinstance(patches, list):
            raise ValueError("patches_json must be a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[fast_multi_edit] ERROR: Invalid patches_json: {e}")
        sys.exit(1)

    if not patches:
        print("[fast_multi_edit] ERROR: patches array is empty")
        sys.exit(1)

    # Read file
    try:
        original_content = path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[fast_multi_edit] ERROR: Cannot read file: {e}")
        sys.exit(1)

    current_hash = _file_hash(path)
    session = _load_session()
    key = str(path)

    # Hash validation
    if key in session:
        cached_hash = session[key]["hash"]
        if cached_hash != current_hash:
            print(f"[fast_multi_edit] HASH MISMATCH: {filepath}")
            print(f"  Expected: {cached_hash}")
            print(f"  Current : {current_hash}")
            print(f"  File was modified externally. Run fast_read to refresh.")
            sys.exit(2)
    else:
        print(f"[fast_multi_edit] Warning: {filepath} not in session. Proceeding.")

    # Backup sebelum apply
    backup_path = path.with_suffix(path.suffix + ".ccmin-bak")
    try:
        shutil.copy2(path, backup_path)
    except OSError as e:
        print(f"[fast_multi_edit] Warning: backup failed: {e}")

    # Apply patches secara atomic
    lines = original_content.splitlines(keepends=True)
    offset = 0
    results = []
    failed = False
    failed_idx = None
    failed_msg = ""

    for patch_idx, patch in enumerate(patches):
        hunks = parse_hunks(patch)
        if not hunks:
            results.append(f"  patch[{patch_idx}]: SKIP (no valid hunks)")
            continue

        patch_success = True
        for hunk_idx, (orig_start, hunk_lines) in enumerate(hunks):
            lines, offset, success, err, changed = apply_single_hunk(
                lines, orig_start, hunk_lines, offset
            )
            if not success:
                patch_success = False
                failed = True
                failed_idx = patch_idx
                failed_msg = f"patch[{patch_idx}] hunk[{hunk_idx}]: {err}"
                break

        if not patch_success:
            break

        if changed:
            results.append(f"  patch[{patch_idx}]: OK lines {changed[0]}-{changed[1]}")
        else:
            results.append(f"  patch[{patch_idx}]: OK")

    if failed:
        # Rollback — tidak tulis apa-apa, file asli masih utuh
        print(f"[fast_multi_edit] FAILED at {failed_msg}")
        print("[fast_multi_edit] ROLLBACK: no changes written")
        print("\nResults so far:")
        for r in results:
            print(r)
        sys.exit(1)

    # Semua berhasil — atomic write
    new_content = "".join(lines)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(new_content, encoding="utf-8")
        tmp.rename(path)
    except OSError as e:
        print(f"[fast_multi_edit] ERROR: Write failed: {e}")
        if tmp.exists():
            tmp.unlink()
        sys.exit(1)

    # Update session
    new_hash = _file_hash(path)
    new_tokens = _count_tokens_approx(new_content)
    if key not in session:
        session[key] = {}
    session[key]["hash"] = new_hash
    session[key]["ts"] = time.time()
    session[key]["tokens"] = new_tokens
    session[key]["full"] = True
    _save_session(session)

    print(f"[fast_multi_edit] OK: {filepath} | {len(patches)} patches applied | new_hash={new_hash} | tokens≈{new_tokens}")
    print("Patch results:")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()

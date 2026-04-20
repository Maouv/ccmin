#!/usr/bin/env python3
"""
fast_read - Token-efficient file reading untuk ccmin.

Usage:
  fast_read.py <file>                        # Full read (sekali per sesi)
  fast_read.py <file> lines=10:50            # Baca baris 10-50
  fast_read.py <file> search=def my_func    # Cari keyword, return context
  fast_read.py --session-map                 # Lihat file yang sudah di-read sesi ini
  fast_read.py --invalidate <file>           # Force invalidate cache file tertentu

Session state disimpan di /tmp/ccmin-session-<pid>.json
Hash mismatch otomatis reject dan prompt re-read.
"""

import sys
import os
import json
import hashlib
import time
from pathlib import Path

# Session file — unik per parent PID (Claude Code process)
SESSION_FILE = Path(f"/tmp/ccmin-session-{os.getppid()}.json")
CONTEXT_LINES = 5  # Baris context sekitar keyword


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
    except OSError as e:
        print(f"[fast_read] Warning: cannot save session: {e}", file=sys.stderr)


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _count_tokens_approx(text: str) -> int:
    """Approx token count: 1 token ~= 4 chars."""
    return len(text) // 4


def read_lines(path: Path, start: int, end: int) -> str:
    """Baca baris start..end (1-indexed, inclusive)."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)
    start = max(1, start)
    end = min(total, end)
    chunk = lines[start - 1:end]
    return "\n".join(chunk), start, end, total


def read_search(path: Path, keyword: str) -> str:
    """Cari keyword di file, return context sekitar setiap match."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)
    results = []
    seen_ranges = []

    for i, line in enumerate(lines):
        if keyword.lower() in line.lower():
            lo = max(0, i - CONTEXT_LINES)
            hi = min(total - 1, i + CONTEXT_LINES)

            # Skip kalau overlap dengan range sebelumnya
            if any(lo <= prev_hi and hi >= prev_lo for prev_lo, prev_hi in seen_ranges):
                continue

            seen_ranges.append((lo, hi))
            chunk_lines = []
            for j in range(lo, hi + 1):
                marker = ">>>" if j == i else "   "
                chunk_lines.append(f"{marker} {j+1:4d} | {lines[j]}")
            results.append("\n".join(chunk_lines))

    if not results:
        return None
    return f"\n{'─'*40}\n".join(results)


def cmd_session_map():
    session = _load_session()
    if not session:
        print("(no files read this session)")
        return

    print(f"Files read this session (pid={os.getppid()}):")
    for fpath, meta in session.items():
        ts = time.strftime("%H:%M:%S", time.localtime(meta["ts"]))
        tokens = meta.get("tokens", "?")
        print(f"  {fpath}  [hash={meta['hash']}  tokens≈{tokens}  read_at={ts}]")


def cmd_invalidate(filepath: str):
    session = _load_session()
    key = str(Path(filepath).resolve())
    if key in session:
        del session[key]
        _save_session(session)
        print(f"[fast_read] Invalidated cache for {filepath}")
    else:
        print(f"[fast_read] {filepath} not in session cache")


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage: fast_read.py <file> [lines=N:M | search=keyword]")
        sys.exit(1)

    # Special commands
    if args[0] == "--session-map":
        cmd_session_map()
        return

    if args[0] == "--invalidate" and len(args) >= 2:
        cmd_invalidate(args[1])
        return

    filepath = args[0]
    path = Path(filepath).resolve()

    if not path.exists():
        print(f"[fast_read] ERROR: File not found: {filepath}")
        sys.exit(1)

    if not path.is_file():
        print(f"[fast_read] ERROR: Not a file: {filepath}")
        sys.exit(1)

    # Parse mode
    mode = "full"
    line_start = line_end = None
    keyword = None

    for arg in args[1:]:
        if arg.startswith("lines="):
            mode = "lines"
            parts = arg[6:].split(":")
            try:
                line_start = int(parts[0])
                line_end = int(parts[1]) if len(parts) > 1 else line_start + 50
            except (ValueError, IndexError):
                print(f"[fast_read] ERROR: Invalid lines spec '{arg}'. Use lines=N:M")
                sys.exit(1)
        elif arg.startswith("search="):
            mode = "search"
            keyword = arg[7:]

    session = _load_session()
    key = str(path)
    current_hash = _file_hash(path)

    # Cek stale
    if key in session:
        cached = session[key]
        if cached["hash"] != current_hash:
            print(f"[fast_read] HASH MISMATCH: {filepath}")
            print(f"  Cached hash : {cached['hash']}")
            print(f"  Current hash: {current_hash}")
            print(f"  File was modified since last read. Re-reading now.")
            # Lanjut baca — update cache

    # Eksekusi baca
    if mode == "lines":
        content, actual_start, actual_end, total = read_lines(path, line_start, line_end)
        tokens = _count_tokens_approx(content)
        header = f"[fast_read] {filepath} | lines {actual_start}-{actual_end}/{total} | tokens≈{tokens}"
        print(header)
        print(content)

        # Update session — catat partial read tapi jangan set full_read
        if key not in session:
            session[key] = {"hash": current_hash, "ts": time.time(), "tokens": tokens, "full": False}
        else:
            session[key]["hash"] = current_hash

    elif mode == "search":
        result = read_search(path, keyword)
        if result is None:
            print(f"[fast_read] No match for '{keyword}' in {filepath}")
        else:
            tokens = _count_tokens_approx(result)
            print(f"[fast_read] {filepath} | search='{keyword}' | tokens≈{tokens}")
            print(result)

        if key not in session:
            session[key] = {"hash": current_hash, "ts": time.time(), "tokens": tokens if result else 0, "full": False}
        else:
            session[key]["hash"] = current_hash

    else:
        # Full read — satu kali per sesi
        already_read = key in session and session[key].get("full") and session[key]["hash"] == current_hash
        if already_read:
            ts = time.strftime("%H:%M:%S", time.localtime(session[key]["ts"]))
            print(f"[fast_read] {filepath} already read this session at {ts} (hash={current_hash})")
            print(f"[fast_read] Use shadow memory. Re-read only if hash mismatch.")
            # Return content tetap — Claude mungkin perlu refresh
            # Tapi kita beri warning supaya Claude tau ini redundant
            content = path.read_text(encoding="utf-8", errors="replace")
            tokens = _count_tokens_approx(content)
            print(f"[fast_read] Returning content anyway | tokens≈{tokens}")
            print(content)
        else:
            content = path.read_text(encoding="utf-8", errors="replace")
            tokens = _count_tokens_approx(content)
            total_lines = content.count("\n") + 1
            print(f"[fast_read] {filepath} | {total_lines} lines | tokens≈{tokens}")
            print(content)
            session[key] = {
                "hash": current_hash,
                "ts": time.time(),
                "tokens": tokens,
                "full": True
            }

    _save_session(session)


if __name__ == "__main__":
    main()

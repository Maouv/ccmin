#!/usr/bin/env python3
"""
repo_map - Generate lightweight project tree untuk ccmin.

Usage (internal — dipanggil dari launcher.py saat launch):
  repo_map.py <project_dir>        # Print repo map ke stdout
  repo_map.py <project_dir> --json # Print JSON (untuk debug)

Cache: ~/.ccmin/repo-map-cache.json
  - Key: hash dari directory structure
  - Value: cached map string
  - Regenerate otomatis kalau hash berubah (file baru/hapus)

Config (di ~/.ccmin/config.json):
  {
    "repo_map": {
      "enabled": true,
      "max_tokens": 1024,
      "exclude": ["node_modules", ".git", "dist", "build", "__pycache__", "*.pyc"]
    }
  }
"""

import sys
import os
import json
import hashlib
from pathlib import Path
import fnmatch

CCMIN_DIR = Path.home() / ".ccmin"
CACHE_FILE = CCMIN_DIR / "repo-map-cache.json"
CONFIG_PATH = CCMIN_DIR / "config.json"

DEFAULT_EXCLUDE = [
    ".git", "node_modules", "dist", "build", "__pycache__",
    "*.pyc", "*.pyo", "*.pyd", ".DS_Store", "*.egg-info",
    ".venv", "venv", ".env", "env", ".tox",
    "*.min.js", "*.min.css", "coverage", ".nyc_output",
    "*.lock", "package-lock.json", "yarn.lock",
]


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
            return cfg.get("repo_map", {})
        except Exception:
            pass
    return {}


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(cache: dict):
    CCMIN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        CACHE_FILE.write_text(json.dumps(cache, indent=2))
    except OSError:
        pass


def _is_excluded(name: str, exclude_patterns: list) -> bool:
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        if name == pattern:
            return True
    return False


def _read_gitignore(project_dir: Path) -> list:
    """Baca .gitignore dan return list of patterns."""
    gitignore = project_dir / ".gitignore"
    patterns = []
    if gitignore.exists():
        try:
            for line in gitignore.read_text(errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    # Normalisasi: hapus leading slash
                    patterns.append(line.lstrip("/"))
        except OSError:
            pass
    return patterns


def _collect_tree(project_dir: Path, exclude_patterns: list, max_depth: int = 6) -> list:
    """
    Collect tree entries sebagai list of (depth, name, is_dir, path).
    Sorted: direktori dulu, lalu file, alphabetical.
    """
    entries = []

    def _walk(current: Path, depth: int):
        if depth > max_depth:
            return
        try:
            items = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return

        for item in items:
            if _is_excluded(item.name, exclude_patterns):
                continue
            entries.append((depth, item.name, item.is_dir(), item))
            if item.is_dir():
                _walk(item, depth + 1)

    _walk(project_dir, 0)
    return entries


def _struct_hash(entries: list) -> str:
    """Hash dari nama + is_dir saja (bukan content)."""
    parts = [f"{depth}:{name}:{int(is_dir)}" for depth, name, is_dir, _ in entries]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def _render_tree(project_dir: Path, entries: list, max_tokens: int) -> str:
    """
    Render tree sebagai string dengan box-drawing chars.
    Trim secara hierarchical kalau melebihi max_tokens.
    """
    root_name = project_dir.name or str(project_dir)
    lines = [f"{root_name}/"]

    # Group per depth untuk hierarchical trim
    # Kita render full dulu, lalu trim kalau perlu
    prev_counts = {}  # depth -> count of siblings seen

    # Build structure: list of (depth, display_line)
    # Kita perlu track siblings untuk connector yang benar (├── vs └──)
    # Simplification: gunakan always ├── kecuali entry terakhir per parent

    # Collect per parent
    from collections import defaultdict
    children = defaultdict(list)  # parent_path -> [entries]
    for depth, name, is_dir, path in entries:
        children[str(path.parent)].append((depth, name, is_dir, path))

    rendered = []

    def _render(current_path: Path, depth: int):
        key = str(current_path)
        kids = children.get(key, [])
        for i, (d, name, is_dir, path) in enumerate(kids):
            is_last = (i == len(kids) - 1)
            prefix = "    " * (depth) + ("└── " if is_last else "├── ")
            suffix = "/" if is_dir else ""
            rendered.append(f"{prefix}{name}{suffix}")
            if is_dir:
                _render(path, depth + 1)

    _render(project_dir, 0)

    # Tokens approx
    def approx_tokens(text: str) -> int:
        return len(text) // 4

    full = root_name + "/\n" + "\n".join(rendered)

    if approx_tokens(full) <= max_tokens:
        return full

    # Hierarchical trim: potong dari depth terdalam dulu
    # Cari max depth yang masih fit
    for max_d in range(6, 0, -1):
        trimmed = []
        for line in rendered:
            depth_indicator = len(line) - len(line.lstrip())
            current_depth = depth_indicator // 4
            if current_depth <= max_d:
                trimmed.append(line)

        result = root_name + "/\n" + "\n".join(trimmed)
        if approx_tokens(result) <= max_tokens:
            # Tambah note kalau ada yang dipotong
            if len(trimmed) < len(rendered):
                result += f"\n... (trimmed to depth {max_d}, {len(rendered) - len(trimmed)} entries hidden)"
            return result

    # Fallback: hanya top-level
    top = [line for line in rendered if len(line) - len(line.lstrip()) <= 4]
    return root_name + "/\n" + "\n".join(top[:50]) + "\n... (top-level only)"


def generate_map(project_dir_str: str) -> str:
    """
    Main entry: generate atau return cached map.
    Return string siap inject ke system prompt.
    """
    project_dir = Path(project_dir_str).resolve()

    if not project_dir.exists():
        return f"[repo_map] ERROR: Project dir not found: {project_dir}"

    cfg = _load_config()

    if not cfg.get("enabled", False):
        return ""  # Disabled

    max_tokens = cfg.get("max_tokens", 1024)
    extra_exclude = cfg.get("exclude", [])
    exclude_patterns = DEFAULT_EXCLUDE + extra_exclude + _read_gitignore(project_dir)

    # Collect tree
    entries = _collect_tree(project_dir, exclude_patterns)
    struct_hash = _struct_hash(entries)

    # Check cache
    cache = _load_cache()
    cache_key = f"{project_dir}:{struct_hash}"

    if cache_key in cache:
        return cache[cache_key]["map"]

    # Generate baru
    map_str = _render_tree(project_dir, entries, max_tokens)

    # Wrap dengan header
    result = f"# Project Structure\n```\n{map_str}\n```"

    # Save to cache
    cache[cache_key] = {"map": result, "hash": struct_hash}

    # Bersihkan cache lama untuk project ini (hanya keep entry terbaru)
    old_keys = [k for k in cache if k.startswith(str(project_dir) + ":") and k != cache_key]
    for old_key in old_keys:
        del cache[old_key]

    _save_cache(cache)

    return result


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage: repo_map.py <project_dir> [--json]")
        sys.exit(1)

    project_dir = args[0]
    as_json = "--json" in args

    result = generate_map(project_dir)

    if as_json:
        print(json.dumps({"map": result}))
    else:
        print(result)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Backup, restore, rollback utilities for ccmin."""

import json
from datetime import datetime
from pathlib import Path

CCMIN_DIR = Path("~/.ccmin").expanduser()
BACKUPS_DIR = CCMIN_DIR / "backups"


def backup(settings_path: Path, scope: str, backup_limit: int = 10) -> Path:
    """
    Validasi JSON dulu. Jika corrupt → simpan .corrupt, warn, raise.
    Copy ke ~/.ccmin/backups/{scope}/settings_{timestamp}.json.
    Auto-prune jika > backup_limit.
    Return path backup baru.
    """
    if not settings_path.exists():
        raise FileNotFoundError(f"Settings file not found: {settings_path}")

    # Read and validate JSON
    try:
        content = settings_path.read_text(encoding='utf-8')
        json.loads(content)  # Validate JSON
    except json.JSONDecodeError as e:
        # Save corrupt version
        corrupt_path = settings_path.with_suffix('.corrupt')
        corrupt_path.write_text(content, encoding='utf-8')
        raise ValueError(
            f"Settings file is corrupt. Saved as {corrupt_path}. "
            f"JSON error: {e}"
        )

    # Create backup directory
    backup_dir = BACKUPS_DIR / scope
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Create backup filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_path = backup_dir / f"settings_{timestamp}.json"

    # Copy file
    backup_path.write_text(content, encoding='utf-8')

    # Auto-prune if exceeds limit
    _prune_backups(scope, backup_limit)

    return backup_path


def _prune_backups(scope: str, backup_limit: int) -> None:
    """Remove oldest backups if count exceeds limit."""
    backups = list_backups(scope)
    if len(backups) > backup_limit:
        removed = len(backups) - backup_limit
        print(f"⚠ Oldest backup will be removed ({removed} file(s), keeping {backup_limit})")
        # Remove oldest files (already sorted by date desc)
        for old_backup in backups[backup_limit:]:
            old_backup.unlink()


def list_backups(scope: str) -> list[Path]:
    """Return list backup files sorted by date desc."""
    backup_dir = BACKUPS_DIR / scope
    if not backup_dir.exists():
        return []

    backups = list(backup_dir.glob("settings_*.json"))
    # Sort by modification time (newest first)
    backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return backups


def restore(backup_path: Path, settings_path: Path) -> None:
    """Validasi JSON backup → atomic restore."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    # Validate JSON
    try:
        content = backup_path.read_text(encoding='utf-8')
        json.loads(content)  # Validate JSON
    except json.JSONDecodeError as e:
        raise ValueError(f"Backup file is corrupt: {e}")

    # Ensure parent directory exists
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write
    tmp = settings_path.with_suffix('.tmp')
    tmp.write_text(content, encoding='utf-8')
    tmp.rename(settings_path)
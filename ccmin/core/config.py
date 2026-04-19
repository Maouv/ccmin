#!/usr/bin/env python3
"""Config management for ccmin."""

import json
from pathlib import Path

CCMIN_DIR = Path("~/.ccmin").expanduser()
CONFIG_PATH = CCMIN_DIR / "config.json"


def load_config() -> dict:
    """Baca config. Raise FileNotFoundError jika belum --init."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config not found at {CONFIG_PATH}. Run 'ccmin --init' first."
        )
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config: dict) -> None:
    """Atomic write ke config.json."""
    CCMIN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2))
    tmp.rename(CONFIG_PATH)


def get_settings_path(scope: str, project_path: str) -> Path:
    """
    scope='local'  → {project_path}/.claude/settings.local.json
    scope='global' → ~/.claude/settings.json
    """
    if scope == "local":
        return Path(project_path) / ".claude" / "settings.local.json"
    elif scope == "global":
        return Path.home() / ".claude" / "settings.json"
    else:
        raise ValueError(f"Invalid scope: {scope}. Must be 'local' or 'global'.")
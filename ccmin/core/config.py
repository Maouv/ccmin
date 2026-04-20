#!/usr/bin/env python3
"""Config management for ccmin."""

import json
import shutil
from pathlib import Path

CCMIN_DIR = Path("~/.ccmin").expanduser()
CONFIG_PATH = CCMIN_DIR / "config.json"
TOOLS_DIR = CCMIN_DIR / "tools"


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


def install_tools(script_dir: Path) -> list:
    """
    Copy tools dari repo ke ~/.ccmin/tools/.
    Return list of (tool_name, status) untuk reporting.
    """
    src_tools = script_dir / "tools"
    if not src_tools.exists():
        return []

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for tool_file in ["fast_read.py", "fast_edit.py", "fast_multi_edit.py", "repo_map.py"]:
        src = src_tools / tool_file
        dst = TOOLS_DIR / tool_file
        if src.exists():
            shutil.copy2(src, dst)
            dst.chmod(0o755)
            results.append((tool_file, "installed"))
        else:
            results.append((tool_file, "not found in repo"))

    return results

#!/usr/bin/env python3
"""Detection utilities for ccmin."""

import json
import shutil
import subprocess
from pathlib import Path


def detect_launcher() -> tuple[str, list[str]]:
    """
    Return (launcher_cmd, all_found).
    launcher_cmd: "claude" atau "ccr code"
    all_found: list semua yang terdeteksi
    """
    launchers = []
    if shutil.which("claude"):
        launchers.append("claude")
    if shutil.which("ccr"):
        launchers.append("ccr code")

    if not launchers:
        raise FileNotFoundError(
            "Neither 'claude' nor 'ccr' found in PATH. "
            "Install Claude Code or Claude-Code-Router first."
        )

    # Default to "claude" if available, otherwise "ccr code"
    launcher_cmd = "claude" if "claude" in launchers else "ccr code"
    return launcher_cmd, launchers


def detect_scope(project_path: str) -> str:
    """
    Cek local dulu. Jika ada → 'local'.
    Jika tidak ada, cek global → 'global'.
    Jika keduanya ada → 'local' (no prompt).
    Jika tidak ada → 'local' (akan dibuat saat --init).
    """
    local_path = Path(project_path) / ".claude" / "settings.local.json"
    global_path = Path.home() / ".claude" / "settings.json"

    if local_path.exists():
        return "local"
    elif global_path.exists():
        return "global"
    else:
        return "local"  # Will be created during --init


def detect_claude_version(launcher: str) -> str:
    """Run `{launcher} --version`, parse output."""
    try:
        result = subprocess.run(
            [launcher, "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            # Parse version from output like "2.1.114" or "claude v2.1.114"
            output = result.stdout.strip()
            # Extract version numbers
            parts = output.split()
            for part in parts:
                if part.replace('.', '').replace('v', '').isdigit():
                    return part.lstrip('v')
            return output  # Return full output if no clean version found
        else:
            return "unknown"
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return "unknown"


def detect_mode(settings: dict) -> str:
    """
    Baca allow list dari settings dict.
    Return 'minimal', 'standard', atau 'unknown'.
    """
    permissions = settings.get("permissions", {})
    allow_list = permissions.get("allow", [])

    # Convert to set for comparison
    allow_set = set(allow_list)

    # Minimal = exactly [Edit, Write, MultiEdit, Read]
    minimal_set = {"Edit", "Write", "MultiEdit", "Read"}
    if allow_set == minimal_set:
        return "minimal"

    # Standard = minimal + "Bash(git *)"
    standard_set = minimal_set | {"Bash(git *)"}
    if allow_set == standard_set:
        return "standard"

    return "unknown"
#!/usr/bin/env python3
"""Launch utilities for ccmin."""

import os
import sys
from pathlib import Path


def build_command(config: dict, cwd: str) -> list[str]:
    """
    Build argv list untuk os.execvp.
    Membaca allow list dari settings aktif (local/global).
    """
    import json
    from .config import get_settings_path

    launcher_str = config.get("launcher", "claude")
    launcher_parts = launcher_str.split()  # handle multi-word launchers like 'ccr code'
    launcher = launcher_parts[0]
    launcher_extra_args = launcher_parts[1:]
    prompt_file = config.get("prompt_file", "~/.ccmin/minimal-prompt.txt")
    scope = config.get("scope", "local")
    project_path = config.get("project_path", cwd)

    # Expand user path
    prompt_path = Path(prompt_file).expanduser()
    if not prompt_path.exists():
        print(f"Warning: Prompt file not found at {prompt_path}", file=sys.stderr)

    # Baca allow list dari settings aktif
    tools = "Read,Write,Edit,MultiEdit,Bash(git *)"  # fallback
    settings_path = get_settings_path(scope, project_path)
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            allow = settings.get("permissions", {}).get("allow", [])
            if allow:
                tools = ",".join(allow)
        except json.JSONDecodeError:
            pass

    command = [
        launcher,
        *launcher_extra_args,
        "--bare",
        "--add-dir", project_path,  # load .claude/commands/
        "--tools", tools,
        "--system-prompt-file", str(prompt_path),
        "--append-system-prompt", f"Your working directory is: {cwd}"
    ]

    return command


def launch(config: dict, full_mode: bool = False) -> None:
    """
    full_mode=True → exec launcher saja tanpa flag.
    full_mode=False → build_command + cwd warning + os.execvp.
    """
    import subprocess
    from .config import get_settings_path
    from .detector import detect_mode

    launcher_str = config.get("launcher", "claude")
    launcher_parts = launcher_str.split()
    launcher = launcher_parts[0]
    launcher_extra_args = launcher_parts[1:]
    project_path = config.get("project_path", os.getcwd())
    cwd = os.getcwd()

    if full_mode:
        # Launch without any flags
        cmd = [launcher, *launcher_extra_args]
    else:
        # Check if launching from wrong directory
        if cwd != project_path:
            response = input(
                f"⚠ Launching from {cwd}, config project is {project_path}. Continue? [y/n]: "
            )
            if response.lower() != 'y':
                print("Launch cancelled.")
                return

        # Build minimal mode command
        cmd = build_command(config, cwd)

        # Check current mode for informational purposes
        scope = config.get("scope", "local")
        settings_path = get_settings_path(scope, project_path)
        if settings_path.exists():
            try:
                import json
                settings = json.loads(settings_path.read_text())
                mode = detect_mode(settings)
            except (json.JSONDecodeError, ValueError):
                pass  # Ignore mode detection errors during launch

    # Replace current process
    try:
        os.execvp(cmd[0], cmd)
    except FileNotFoundError:
        print(f"Error: Launcher '{launcher_str}' not found.", file=sys.stderr)
        print("Please install Claude Code or Claude-Code-Router.", file=sys.stderr)
        sys.exit(1)

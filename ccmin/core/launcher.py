#!/usr/bin/env python3
"""Launch utilities for ccmin."""

import os
import sys
from pathlib import Path


def build_command(config: dict, cwd: str) -> list[str]:
    """
    Build argv list untuk os.execvp.
    Contoh: ["claude", "--bare", "--tools", "Read,Write,Edit,MultiEdit",
             "--system-prompt-file", "/root/.ccmin/minimal-prompt.txt",
             "--append-system-prompt", "Your working directory is: /root/myproject"]
    """
    launcher = config.get("launcher", "claude")
    prompt_file = config.get("prompt_file", "~/.ccmin/minimal-prompt.txt")

    # Expand user path
    prompt_path = Path(prompt_file).expanduser()
    if not prompt_path.exists():
        print(f"Warning: Prompt file not found at {prompt_path}", file=sys.stderr)

    command = [
        launcher,
        "--bare",
        "--tools", "Read,Write,Edit,MultiEdit,Bash(git *)",
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

    launcher = config.get("launcher", "claude")
    project_path = config.get("project_path", os.getcwd())
    cwd = os.getcwd()

    if full_mode:
        # Launch without any flags
        cmd = [launcher]
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
                print(f"[{mode.upper()}] {launcher}", file=sys.stderr)
            except (json.JSONDecodeError, ValueError):
                pass  # Ignore mode detection errors during launch

    # Replace current process
    try:
        os.execvp(cmd[0], cmd)
    except FileNotFoundError:
        print(f"Error: Launcher '{cmd[0]}' not found.", file=sys.stderr)
        print("Please install Claude Code or Claude-Code-Router.", file=sys.stderr)
        sys.exit(1)
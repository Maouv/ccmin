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

    # Inject CWD into prompt dynamically, write to temp file
    import tempfile
    prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    prompt_text = prompt_text.replace("{cwd}", cwd)
    prompt_text += f"\n\n# Session Context\nWorking directory: {cwd}\nAll file paths are relative to {cwd}. Never access files outside {cwd} unless user provides absolute path."

    tmp_prompt = Path(tempfile.mktemp(suffix=".txt", prefix="ccmin-prompt-"))
    tmp_prompt.write_text(prompt_text, encoding="utf-8")

    # Baca allow list dan detect mode dari settings aktif
    tools = "Read,Write,Edit,MultiEdit,Bash(git *)"  # fallback
    is_very_strict = False
    settings_path = get_settings_path(scope, project_path)
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            allow = settings.get("permissions", {}).get("allow", [])
            ask = settings.get("permissions", {}).get("ask", [])
            # very-strict: Read is in ask, not allow
            if "Read" in ask and "Read" not in allow:
                is_very_strict = True
                tools = ",".join([t for t in allow if t])  # exclude Read from --tools
            elif allow:
                tools = ",".join(allow)
        except json.JSONDecodeError:
            pass

    command = [
        launcher,
        *launcher_extra_args,
        "--bare",
        "--tools", tools,
        "--system-prompt-file", str(tmp_prompt),
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

    # Disable auto-memory to prevent token waste and unsolicited file writes
    os.environ["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"

    # Expose CWD for PreToolUse hook to enforce file access boundaries
    os.environ["CCMIN_CWD"] = cwd

    # Replace current process
    try:
        os.execvp(cmd[0], cmd)
    except FileNotFoundError:
        print(f"Error: Launcher '{launcher_str}' not found.", file=sys.stderr)
        print("Please install Claude Code or Claude-Code-Router.", file=sys.stderr)
        sys.exit(1)

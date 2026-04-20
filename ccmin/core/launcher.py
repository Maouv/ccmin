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
    scope = config.get("scope", "local")
    project_path = config.get("project_path", cwd)
    fast_tools_enabled = config.get("fast_tools", {}).get("enabled", False)

    # Pilih prompt file berdasarkan fast_tools config
    prompt_file = config.get("prompt_file", "~/.ccmin/minimal-prompt.txt")
    prompt_path = Path(prompt_file).expanduser()

    # Fallback: kalau prompt_file tidak ada, cari yang sesuai mode
    if not prompt_path.exists():
        ccmin_dir = Path.home() / ".ccmin"
        if fast_tools_enabled:
            fallback = ccmin_dir / "minimal-prompt-fast.txt"
        else:
            fallback = ccmin_dir / "minimal-prompt.txt"
        if fallback.exists():
            prompt_path = fallback
        else:
            print(f"Warning: Prompt file not found at {prompt_path}", file=sys.stderr)

    # Inject CWD into prompt dynamically, write to temp file
    import tempfile
    prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    prompt_text = prompt_text.replace("{cwd}", cwd)
    prompt_text += f"\n\n# Session Context\nWorking directory: {cwd}\nAll file paths are relative to {cwd}. Never access files outside {cwd} unless user provides absolute path."

    # Inject repo map jika enabled
    try:
        import sys as _sys
        _ccmin_tools = Path.home() / ".ccmin" / "tools"
        if str(_ccmin_tools) not in _sys.path:
            _sys.path.insert(0, str(_ccmin_tools))
        from repo_map import generate_map
        repo_map_str = generate_map(cwd)
        if repo_map_str:
            prompt_text += f"\n\n{repo_map_str}"
    except Exception:
        pass  # repo_map gagal tidak boleh block launch

    tmp_prompt = Path(tempfile.mktemp(suffix=".txt", prefix="ccmin-prompt-"))
    tmp_prompt.write_text(prompt_text, encoding="utf-8")

    # Baca allow list dan detect mode dari settings aktif
    tools = "Read,Write,Edit,MultiEdit,Bash"  # fallback
    command_allowed = None
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
                base_tools = []
                for t in allow:
                    base = t.split("(")[0] if "(" in t else t
                    if base and base not in base_tools:
                        base_tools.append(base)
                if "Read" not in base_tools:
                    base_tools.append("Read")
                tools = ",".join(base_tools)
            elif allow:
                # --tools: base tool names only (no specifier)
                # --allowedTools: full specifier untuk restrict
                base_tools = []
                allowed_tools = []
                for t in allow:
                    base = t.split("(")[0] if "(" in t else t
                    if base and base not in base_tools:
                        base_tools.append(base)
                    allowed_tools.append(t)
                tools = ",".join(base_tools)
                # Pass full specifiers via --allowedTools
                command_allowed = ",".join(allowed_tools)
        except json.JSONDecodeError:
            pass

    command = [
        launcher,
        *launcher_extra_args,
        "--bare",
        "--tools", tools,
        "--system-prompt-file", str(tmp_prompt),
    ]

    if command_allowed:
        command += ["--allowedTools", command_allowed]

    # very-strict: Read requires approval — pass allowedTools without Read
    if is_very_strict:
        allowed = ",".join([t for t in tools.split(",") if t and t != "Read"])
        command += ["--allowedTools", allowed]

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

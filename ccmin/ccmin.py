#!/usr/bin/env python3
"""
ccmin - Minimal mode launcher untuk Claude Code (pay-per-use).
Python 3.8+, stdlib only, zero external dependencies.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.config import load_config, save_config, get_settings_path, CCMIN_DIR, CONFIG_PATH
from core.detector import detect_launcher, detect_scope, detect_claude_version, detect_mode
from core.backup import backup, list_backups, restore, BACKUPS_DIR
from core.launcher import launch, build_command

# Import templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"


def atomic_write(path: Path, content: str) -> None:
    """Tulis ke .tmp, validasi JSON, rename."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding='utf-8')
    try:
        json.loads(content)  # Validate before rename
    except json.JSONDecodeError:
        tmp.unlink()
        raise
    tmp.rename(path)


def swap_settings(settings_path: Path, target_mode: str) -> None:
    """
    Merge: baca settings aktif → update allow list saja → tulis kembali.
    Tidak overwrite hooks, plugins, atau field custom lainnya.
    """
    if not settings_path.exists():
        raise FileNotFoundError(f"Settings file not found: {settings_path}")

    current = json.loads(settings_path.read_text(encoding='utf-8'))
    template_file = "settings.min.json" if target_mode == "minimal" else "settings.std.json"
    template = json.loads((TEMPLATES_DIR / template_file).read_text(encoding='utf-8'))

    # Update HANYA allow list
    current.setdefault("permissions", {})
    current["permissions"]["allow"] = template["permissions"]["allow"]

    atomic_write(settings_path, json.dumps(current, indent=2))


def cmd_repair(args):
    """Repair corrupt symlink."""
    import os, stat
    symlink_path = Path("/usr/local/bin/ccmin")

    # Find real script location from config or __file__
    real_script = None
    if CONFIG_PATH.exists():
        try:
            config = load_config()
            # config does not store script path, derive from project_path
        except Exception:
            pass
    # Fallback: use __file__ (works when called via python3 ccmin.py --repair)
    real_script = Path(os.path.realpath(os.path.abspath(__file__)))

    if not real_script.exists():
        print(f"Error: Cannot locate ccmin script at {real_script}")
        print("Run: python3 /path/to/ccmin/ccmin.py --repair")
        return

    try:
        if symlink_path.is_symlink() or symlink_path.exists():
            symlink_path.unlink()
            print("✓ Removed old/corrupt symlink")

        symlink_path.symlink_to(real_script)
        real_script.chmod(real_script.stat().st_mode | stat.S_IEXEC)
        print(f"✓ Symlink repaired: {symlink_path} → {real_script}")
    except PermissionError:
        print("⚠ Permission denied. Try: sudo python3 ccmin/ccmin.py --repair")
    except Exception as e:
        print(f"Error: {e}")


def cmd_init(args):
    """Initialize ccmin configuration."""
    print("🚀 Initializing ccmin...")

    # Auto-fix corrupt symlink before doing anything else
    import os
    symlink_path = Path("/usr/local/bin/ccmin")
    if symlink_path.is_symlink() and not symlink_path.exists():
        try:
            symlink_path.unlink()
            print("⚠ Removed corrupt symlink at /usr/local/bin/ccmin")
        except Exception as e:
            print(f"⚠ Could not remove corrupt symlink: {e}")

    # Guard: already initialized
    if CONFIG_PATH.exists():
        confirm = input("ccmin is already initialized. Reinitialize? [y/n]: ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return

    # Launcher selection
    try:
        detected_launcher, _ = detect_launcher()
    except FileNotFoundError:
        detected_launcher = None

    print("\nLauncher:")
    print("  [1] claude (default - Claude Code official)")
    print("  [2] Custom launcher")
    launcher_choice = input("Choose [1]: ").strip() or "1"

    if launcher_choice == "2":
        custom = input("Launcher name: ").strip()
        launcher = custom if custom else "claude"
    else:
        launcher = "claude"

    # Scope selection
    cwd = os.getcwd()
    print("\nScope:")
    print("  [1] local  - project only")
    print("  [2] global - user-wide")
    scope_choice = input("Choose [1]: ").strip() or "1"
    scope = "global" if scope_choice == "2" else "local"

    # Project path
    print(f"\nProject path: {cwd}")
    path_confirm = input("Use this path? [y/n]: ").strip().lower()
    if path_confirm == "n":
        project_input = input("Enter project path: ").strip()
        if project_input:
            cwd = project_input

    # Choose install method
    print("\nInstall method:")
    print("  [1] Symlink /usr/local/bin/ccmin")
    print("  [2] Bashrc alias")
    print("  [3] Skip")
    install_choice = input("Choose [1]: ").strip() or "1"

    install_method = {
        "1": "symlink",
        "2": "bashrc",
        "3": "skip"
    }.get(install_choice, "symlink")

    # Create config
    config = {
        "launcher": launcher,
        "scope": scope,
        "project_path": cwd,
        "prompt_file": str(CCMIN_DIR / "minimal-prompt.txt"),
        "backup_limit": 10,
        "last_verified_claude_version": detect_claude_version(launcher),
        "install_method": install_method
    }

    # Save config
    save_config(config)
    print(f"✓ Config saved to {CONFIG_PATH}")

    # Copy templates
    CCMIN_DIR.mkdir(parents=True, exist_ok=True)

    prompt_source = TEMPLATES_DIR / "minimal-prompt.txt"
    prompt_dest = CCMIN_DIR / "minimal-prompt.txt"
    if prompt_source.exists():
        prompt_dest.write_text(prompt_source.read_text(encoding='utf-8'), encoding='utf-8')
        print(f"✓ Prompt file copied to {prompt_dest}")

    # Generate .claude/commands/add.md
    commands_dir = Path(cwd) / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    add_cmd = commands_dir / "add.md"
    if not add_cmd.exists():
        add_cmd.write_text(
            "Read the file at path: $ARGUMENTS\n"
            "File is now in context. Wait for the user's instruction.\n"
            "Do not read any other files.\n"
        )
        print(f"✓ Created /add command: {add_cmd}")

    # Backup existing settings if they exist
    settings_path = get_settings_path(scope, cwd)
    if settings_path.exists():
        try:
            backup_path = backup(settings_path, scope, config["backup_limit"])
            print(f"✓ Existing settings backed up to {backup_path}")
        except Exception as e:
            print(f"⚠ Backup failed: {e}")

    # Install method
    if install_method == "symlink":
        _install_symlink()
    elif install_method == "bashrc":
        _install_bashrc()
    else:
        print("\nManual installation:")
        print(f"  alias ccmin='python3 {Path(__file__).absolute()}'")
        print("  Add to your ~/.bashrc or ~/.zshrc")


def _install_symlink():
    """Install ccmin via symlink."""
    import stat
    import os
    # Use __file__ directly via os.path to avoid resolve() looping on corrupt symlinks
    ccmin_script = Path(os.path.realpath(os.path.abspath(__file__)))
    symlink_path = Path("/usr/local/bin/ccmin")

    try:
        # Always remove first — handles corrupt/loop symlinks safely
        if symlink_path.is_symlink() or symlink_path.exists():
            symlink_path.unlink()

        symlink_path.symlink_to(ccmin_script)
        # chmod the real file, never the symlink
        ccmin_script.chmod(ccmin_script.stat().st_mode | stat.S_IEXEC)
        print(f"✓ Symlink created: {symlink_path} → {ccmin_script}")
    except PermissionError:
        print("⚠ Permission denied for /usr/local/bin, falling back to bashrc")
        _install_bashrc()


def _install_bashrc():
    """Install ccmin via bashrc alias."""
    ccmin_script = Path(__file__).absolute()
    alias_line = f"alias ccmin='python3 {ccmin_script}'\n"

    bashrc_path = Path.home() / ".bashrc"
    if bashrc_path.exists():
        content = bashrc_path.read_text(encoding='utf-8')
        if "alias ccmin=" not in content:
            with open(bashrc_path, 'a', encoding='utf-8') as f:
                f.write(f"\n{alias_line}")
            print(f"✓ Alias added to {bashrc_path}")
            print("  Run 'source ~/.bashrc' or restart your shell")
        else:
            print(f"✓ ccmin alias already exists in {bashrc_path}")
    else:
        print(f"⚠ {bashrc_path} not found. Add this alias manually:")
        print(f"  {alias_line.strip()}")


def cmd_launch(args):
    """Launch Claude in minimal mode."""
    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: ccmin not initialized. Run 'ccmin --init' first.")
        sys.exit(1)

    # Auto-create .claude/ dan copy prompt jika belum ada
    cwd = os.getcwd()
    claude_dir = Path(cwd) / ".claude"
    claude_dir.mkdir(exist_ok=True)

    local_settings = claude_dir / "settings.local.json"
    if not local_settings.exists():
        src_settings = TEMPLATES_DIR / "settings.min.json"
        if src_settings.exists():
            shutil.copy(src_settings, local_settings)
            print(f"✓ Created minimal settings: {local_settings}")

    launch(config, full_mode=False)


def cmd_full(args):
    """Launch Claude in full mode."""
    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: ccmin not initialized. Run 'ccmin --init' first.")
        sys.exit(1)

    launch(config, full_mode=True)


def cmd_swap(args):
    """Swap between minimal and standard mode."""
    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: ccmin not initialized. Run 'ccmin --init' first.")
        sys.exit(1)

    scope = args.scope or config.get("scope", "local")
    settings_path = get_settings_path(scope, config["project_path"])

    if not settings_path.exists():
        print(f"Error: Settings file not found: {settings_path}")
        sys.exit(1)

    # Read current settings
    try:
        current_settings = json.loads(settings_path.read_text(encoding='utf-8'))
        current_mode = detect_mode(current_settings)
    except json.JSONDecodeError as e:
        print(f"Error: Settings file is corrupt: {e}")
        sys.exit(1)

    # Determine target mode
    if current_mode == "minimal":
        target_mode = "standard"
    elif current_mode == "standard":
        target_mode = "minimal"
    else:
        print(f"Current mode: {current_mode} (unknown)")
        print("Allow list:", current_settings.get("permissions", {}).get("allow", []))
        print("\nChoose target mode:")
        print("  [1] minimal")
        print("  [2] standard")
        print("  [3] cancel")
        choice = input("Choose [1]: ").strip() or "1"

        if choice == "1":
            target_mode = "minimal"
        elif choice == "2":
            target_mode = "standard"
        else:
            print("Cancelled.")
            return

    # Backup before swap
    try:
        backup_path = backup(settings_path, scope, config.get("backup_limit", 10))
        print(f"✓ Settings backed up to {backup_path}")
    except Exception as e:
        print(f"Error: Backup failed: {e}")
        sys.exit(1)

    # Perform swap
    try:
        swap_settings(settings_path, target_mode)
        print(f"✓ Swapped to {target_mode.upper()}")
    except Exception as e:
        print(f"Error: Swap failed: {e}")
        sys.exit(1)


def cmd_backup(args):
    """Create backup of settings."""
    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: ccmin not initialized. Run 'ccmin --init' first.")
        sys.exit(1)

    scope = args.scope or config.get("scope", "local")
    settings_path = get_settings_path(scope, config["project_path"])

    if not settings_path.exists():
        print(f"Error: Settings file not found: {settings_path}")
        sys.exit(1)

    try:
        backup_path = backup(settings_path, scope, config.get("backup_limit", 10))
        print(f"✓ Backup created: {backup_path}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_rollback(args):
    """Restore from backup."""
    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: ccmin not initialized. Run 'ccmin --init' first.")
        sys.exit(1)

    scope = args.scope or config.get("scope", "local")
    settings_path = get_settings_path(scope, config["project_path"])

    # List available backups
    backups = list_backups(scope)
    if not backups:
        print(f"No backups found for {scope} scope.")
        return

    print(f"Available backups ({scope}):")
    for i, backup_file in enumerate(backups, 1):
        stat = backup_file.stat()
        size = stat.st_size
        mtime = stat.st_mtime
        from datetime import datetime
        dt = datetime.fromtimestamp(mtime)
        size_str = f"{size/1024:.1f} KB" if size > 1024 else f"{size} B"
        print(f"[{i}] {dt.strftime('%Y-%m-%d %H:%M:%S')}  ({size_str})")

    # Choose backup
    if args.backup_id:
        choice = args.backup_id
    else:
        choice = input(f"\nRestore which? [1]: ").strip() or "1"

    try:
        backup_index = int(choice) - 1
        if backup_index < 0 or backup_index >= len(backups):
            print("Invalid backup selection.")
            return
    except ValueError:
        print("Invalid input. Please enter a number.")
        return

    selected_backup = backups[backup_index]

    # Confirm restore
    print(f"\nRestore backup [{choice}] to {settings_path}?")
    confirm = input("[y/n]: ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    try:
        # Backup current settings before restore
        if settings_path.exists():
            backup(settings_path, scope, config.get("backup_limit", 10))

        restore(selected_backup, settings_path)
        print(f"✓ Restored backup to {settings_path}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_status(args):
    """Show current status."""
    try:
        config = load_config()
    except FileNotFoundError:
        print("ccmin not initialized. Run 'ccmin --init' first.")
        return

    # Get current mode
    scope = config.get("scope", "local")
    settings_path = get_settings_path(scope, config["project_path"])

    mode = "unknown"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding='utf-8'))
            mode = detect_mode(settings)
        except json.JSONDecodeError:
            mode = "corrupt"

    # Count backups
    backups = list_backups(scope)
    backup_count = len(backups)

    launcher = config.get("launcher", "claude")
    print(f"[{mode.upper()}] {launcher} • {scope} • {backup_count} backups")

    # Version warning
    try:
        current_version = detect_claude_version(launcher)
        last_verified = config.get("last_verified_claude_version", "")
        if last_verified and current_version != last_verified:
            print(f"⚠ Warning: config last verified on claude v{last_verified}, current is v{current_version}")
            print("  Tool descriptions may have changed. Run `ccmin --init` to re-verify.")
    except Exception:
        pass  # Ignore version detection errors


def cmd_add_tool(args):
    """Add tool to allow list."""
    _modify_tool(args.tool, add=True)


def cmd_remove_tool(args):
    """Remove tool from allow list."""
    _modify_tool(args.tool, add=False)


def _modify_tool(tool: str, add: bool):
    """Add or remove tool from settings."""
    try:
        config = load_config()
    except FileNotFoundError:
        print("Error: ccmin not initialized. Run 'ccmin --init' first.")
        sys.exit(1)

    scope = config.get("scope", "local")
    settings_path = get_settings_path(scope, config["project_path"])

    if not settings_path.exists():
        print(f"Error: Settings file not found: {settings_path}")
        sys.exit(1)

    # Read current settings
    try:
        settings = json.loads(settings_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        print(f"Error: Settings file is corrupt: {e}")
        sys.exit(1)

    # Backup before modification
    try:
        backup_path = backup(settings_path, scope, config.get("backup_limit", 10))
        print(f"✓ Settings backed up to {backup_path}")
    except Exception as e:
        print(f"Error: Backup failed: {e}")
        sys.exit(1)

    # Modify permissions
    settings.setdefault("permissions", {})
    allow_list = settings["permissions"].get("allow", [])

    if add:
        if tool not in allow_list:
            allow_list.append(tool)
            print(f"✓ Added '{tool}' to allow list")
        else:
            print(f"'{tool}' is already in allow list")
            return
    else:
        if tool in allow_list:
            allow_list.remove(tool)
            print(f"✓ Removed '{tool}' from allow list")
        else:
            print(f"'{tool}' not found in allow list")
            return

    settings["permissions"]["allow"] = allow_list

    # Write back
    try:
        atomic_write(settings_path, json.dumps(settings, indent=2))
    except Exception as e:
        print(f"Error: Failed to write settings: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ccmin - Minimal mode launcher untuk Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ccmin --init          Initialize ccmin
  ccmin                 Launch Claude in minimal mode
  ccmin --full          Launch Claude in full mode
  ccmin --swap          Swap between minimal/standard mode
  ccmin --backup        Create settings backup
  ccmin --rollback      Restore from backup
  ccmin --status        Show current status
  ccmin --add-tool "Bash(git *)"    Add tool to allow list
  ccmin --remove-tool Glob          Remove tool from allow list
        """
    )

    parser.add_argument("--init", action="store_true", help="Initialize ccmin")
    parser.add_argument("--repair", action="store_true", help="Repair corrupt symlink")
    parser.add_argument("--full", action="store_true", help="Launch in full mode")
    parser.add_argument("--swap", action="store_true", help="Swap between modes")
    parser.add_argument("--backup", action="store_true", help="Create backup")
    parser.add_argument("--rollback", action="store_true", help="Restore from backup")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--add-tool", metavar="TOOL", help="Add tool to allow list")
    parser.add_argument("--remove-tool", metavar="TOOL", help="Remove tool from allow list")
    parser.add_argument("--scope", choices=["local", "global"], help="Override scope")

    args = parser.parse_args()

    # Route to appropriate command
    if args.repair:
        cmd_repair(args)
    elif args.init:
        cmd_init(args)
    elif args.full:
        cmd_full(args)
    elif args.swap:
        cmd_swap(args)
    elif args.backup:
        cmd_backup(args)
    elif args.rollback:
        cmd_rollback(args)
    elif args.status:
        cmd_status(args)
    elif args.add_tool:
        args.tool = args.add_tool
        cmd_add_tool(args)
    elif args.remove_tool:
        args.tool = args.remove_tool
        cmd_remove_tool(args)
    else:
        # Default action: launch minimal mode
        cmd_launch(args)


if __name__ == "__main__":
    main()

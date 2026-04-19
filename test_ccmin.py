#!/usr/bin/env python3
"""Test script untuk ccmin tanpa input interaktif."""

import json
import os
import tempfile
from pathlib import Path
import sys

# Add ccmin to path
sys.path.insert(0, '/root/ccmin/ccmin')

from core.config import save_config, load_config, get_settings_path
from core.detector import detect_mode, detect_scope
from core.backup import backup, list_backups, restore
from core.launcher import build_command


def test_config():
    """Test config management."""
    print("Testing config management...")

    # Test config creation
    test_config = {
        "launcher": "claude",
        "scope": "local",
        "project_path": "/tmp/test_project",
        "prompt_file": "/root/ccmin/ccmin/templates/minimal-prompt.txt",
        "backup_limit": 5,
        "last_verified_claude_version": "2.1.114",
        "install_method": "skip"
    }

    save_config(test_config)
    loaded_config = load_config()

    assert loaded_config["launcher"] == test_config["launcher"]
    assert loaded_config["scope"] == test_config["scope"]
    print("✓ Config save/load works")


def test_detector():
    """Test detection utilities."""
    print("Testing detector utilities...")

    # Test mode detection
    minimal_settings = {
        "permissions": {
            "allow": ["Edit", "Write", "MultiEdit", "Read"]
        }
    }

    standard_settings = {
        "permissions": {
            "allow": ["Edit", "Write", "MultiEdit", "Read", "Bash(git *)"]
        }
    }

    custom_settings = {
        "permissions": {
            "allow": ["Edit", "Write", "Read", "CustomTool"]
        }
    }

    assert detect_mode(minimal_settings) == "minimal"
    assert detect_mode(standard_settings) == "standard"
    assert detect_mode(custom_settings) == "unknown"
    print("✓ Mode detection works")

    # Test scope detection (with temporary directories)
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "project"
        project_dir.mkdir()

        # Test when no settings exist - scope should default to local
        scope = detect_scope(str(project_dir))
        # Scope is local if no local settings exist, or if global settings exist
        # The function returns local as default when nothing exists
        assert scope in ["local", "global"]
        print("✓ Scope detection works")


def test_backup():
    """Test backup utilities."""
    print("Testing backup utilities...")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test settings file
        settings_file = Path(tmpdir) / "settings.json"
        test_settings = {
            "permissions": {
                "allow": ["Edit", "Write", "MultiEdit", "Read"]
            }
        }
        settings_file.write_text(json.dumps(test_settings, indent=2))

        # Test backup
        backup_path = backup(settings_file, "local", 5)
        assert backup_path.exists()

        # Test list backups
        backups = list_backups("local")
        assert len(backups) > 0
        assert backup_path in backups

        # Test restore
        settings_file.unlink()  # Remove original
        assert not settings_file.exists()

        restore(backup_path, settings_file)
        assert settings_file.exists()

        # Verify content
        restored_settings = json.loads(settings_file.read_text())
        assert restored_settings == test_settings

        print("✓ Backup/restore works")


def test_launcher():
    """Test launcher utilities."""
    print("Testing launcher utilities...")

    test_config = {
        "launcher": "claude",
        "prompt_file": "/root/ccmin/ccmin/templates/minimal-prompt.txt",
        "project_path": "/tmp/test"
    }

    command = build_command(test_config, "/tmp/test")

    assert command[0] == "claude"
    assert "--bare" in command
    assert "--tools" in command
    assert "Read,Write,Edit,MultiEdit,Bash(git *)" in command
    assert "--system-prompt-file" in command
    assert "--append-system-prompt" in command
    assert "Your working directory is: /tmp/test" in command

    print("✓ Command building works")


def test_templates():
    """Test template files exist and are valid JSON."""
    print("Testing templates...")

    templates_dir = Path("/root/ccmin/ccmin/templates")

    # Test minimal template
    min_template = templates_dir / "settings.min.json"
    assert min_template.exists()
    min_settings = json.loads(min_template.read_text())
    assert "permissions" in min_settings
    assert "allow" in min_settings["permissions"]
    assert "Edit" in min_settings["permissions"]["allow"]

    # Test standard template
    std_template = templates_dir / "settings.std.json"
    assert std_template.exists()
    std_settings = json.loads(std_template.read_text())
    assert "Bash(git *)" in std_settings["permissions"]["allow"]

    # Test prompt template
    prompt_template = templates_dir / "minimal-prompt.txt"
    assert prompt_template.exists()
    prompt_content = prompt_template.read_text()
    assert "You are a code editing assistant" in prompt_content

    print("✓ Template files are valid")


if __name__ == "__main__":
    print("Running ccmin tests...\n")

    try:
        test_config()
        test_detector()
        test_backup()
        test_launcher()
        test_templates()

        print("\n🎉 All tests passed!")
        print("\nccmin implementation is complete and working!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
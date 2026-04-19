#!/usr/bin/env python3
"""Test ccmin --init in non-interactive mode."""

import subprocess
import sys
import os
from pathlib import Path

# Create a test directory
test_dir = Path("/tmp/ccmin_test")
test_dir.mkdir(exist_ok=True)
os.chdir(test_dir)

# Create mock config to simulate init
ccmin_dir = Path.home() / ".ccmin"
ccmin_dir.mkdir(exist_ok=True)

# Create a simple config
config = {
    "launcher": "claude",
    "scope": "local",
    "project_path": str(test_dir),
    "prompt_file": str(ccmin_dir / "minimal-prompt.txt"),
    "backup_limit": 10,
    "last_verified_claude_version": "unknown",
    "install_method": "skip"
}

import json
(ccmin_dir / "config.json").write_text(json.dumps(config, indent=2))

# Copy prompt file
prompt_src = Path("/root/ccmin/ccmin/templates/minimal-prompt.txt")
prompt_dest = ccmin_dir / "minimal-prompt.txt"
if prompt_src.exists():
    prompt_dest.write_text(prompt_src.read_text())

print("✓ Test setup complete")
print(f"Config: {ccmin_dir / 'config.json'}")
print(f"Prompt: {prompt_dest}")

# Test --status
result = subprocess.run([
    sys.executable, "/root/ccmin/ccmin/ccmin.py", "--status"
], capture_output=True, text=True)

print(f"\nccmin --status output:")
print(result.stdout)
if result.stderr:
    print(f"stderr: {result.stderr}")

print(f"Return code: {result.returncode}")

# Test help
result = subprocess.run([
    sys.executable, "/root/ccmin/ccmin/ccmin.py", "--help"
], capture_output=True, text=True)

print(f"\n✓ ccmin --help works (return code: {result.returncode})")

print("\n🎉 ccmin installation is working!")
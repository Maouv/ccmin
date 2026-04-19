# ccmin

> Minimal mode launcher untuk Claude Code (pay-per-use).
> Python 3.8+, stdlib only, zero external dependencies.

## Features

- **Minimal Mode**: System prompt ringan, tools dibatasi, token hemat
- **Settings Management**: Swap antara minimal/standard preset
- **Auto-backup**: Backup settings sebelum setiap perubahan
- **Working Directory Injection**: Auto-inject working directory ke system prompt
- **Safe by Default**: Background execution disabled, limited tool access

## Quick Start

```bash
# Install (choose one method)
python3 ccmin.py --init                    # Interactive setup
bash install.sh                            # Install script

# Usage
ccmin --init                               # Initialize configuration
ccmin                                      # Launch Claude in minimal mode
ccmin --full                               # Launch Claude in full mode
ccmin --swap                               # Toggle minimal ↔ standard
ccmin --status                             # Show current status
```

## Commands

| Command | Description |
|---------|-------------|
| `ccmin` | Launch Claude in minimal mode |
| `ccmin --init` | Initialize ccmin configuration |
| `ccmin --full` | Launch Claude in full mode |
| `ccmin --swap` | Swap between minimal/standard mode |
| `ccmin --backup` | Create settings backup |
| `ccmin --rollback` | Restore from backup |
| `ccmin --status` | Show current status |
| `ccmin --add-tool "Bash(git *)"` | Add tool to allow list |
| `ccmin --remove-tool Glob` | Remove tool from allow list |
| `ccmin --scope local\|global` | Override scope for commands |

## Modes

### Minimal Mode (Default)
- **Tools**: Read, Write, Edit, MultiEdit, Bash(git *)
- **Restricted**: No MCP tools, no hooks, no background execution
- **Optimized**: Concise output, no reasoning, action-first

### Standard Mode
- **Tools**: Same as minimal + Bash(git *)
- **Features**: Same safety restrictions as minimal

### Full Mode (`ccmin --full`)
- **Tools**: All Claude Code tools available
- **Use Case**: When you need full functionality

## Configuration

Configuration is stored in `~/.ccmin/config.json`:

```json
{
  "launcher": "claude",
  "scope": "local",
  "project_path": "/root/myproject",
  "prompt_file": "~/.ccmin/minimal-prompt.txt",
  "backup_limit": 10,
  "last_verified_claude_version": "2.1.114",
  "install_method": "symlink"
}
```

### Scope

- **Local**: Uses `.claude/settings.local.json` in project directory
- **Global**: Uses `~/.claude/settings.json` (user-wide)

## File Structure

```
~/.ccmin/                    # User data directory
├── config.json              # User configuration
├── minimal-prompt.txt       # System prompt template
└── backups/
    ├── local/               # Project-level backups
    └── global/              # User-level backups

ccmin/                       # Repository
├── ccmin.py                 # Entry point + CLI
├── core/
│   ├── config.py            # Configuration management
│   ├── detector.py          # Launcher/scope detection
│   ├── backup.py            # Backup/restore utilities
│   └── launcher.py          # Command building & execution
├── templates/
│   ├── settings.min.json    # Minimal preset
│   ├── settings.std.json    # Standard preset
│   └── minimal-prompt.txt   # System prompt template
└── install.sh               # Installation script
```

## Safety Features

- **Automatic Backup**: Settings backed up before any modification
- **Atomic Writes**: All file writes are atomic (write → validate → rename)
- **JSON Validation**: All JSON files validated before and after operations
- **Corrupt File Handling**: Corrupt files saved with `.corrupt` suffix
- **Background Execution**: Disabled by default via hooks
- **Limited Bash**: Only git commands allowed in minimal mode

## Examples

```bash
# Setup new project
cd /path/to/project
ccmin --init
# Follow wizard for launcher, scope, and install method

# Daily usage
ccmin                    # Start minimal mode editing session
ccmin --full             # Need full Claude capabilities
ccmin --swap             # Switch to standard mode for git
ccmin --status           # Check current mode and backup count

# Backup management
ccmin --backup           # Manual backup
ccmin --rollback         # Interactive restore
ccmin --backup --scope global  # Backup global settings

# Tool management
ccmin --add-tool "Bash(npm *)"     # Add npm support
ccmin --remove-tool "Bash(git *)"  # Remove git support
```

## Troubleshooting

### "ccmin not initialized"
Run `ccmin --init` to set up configuration.

### "Launcher not found"
Install Claude Code or Claude-Code-Router, or check your PATH.

### "Settings file corrupt"
Check `~/.ccmin/backups/` for recent backups and use `ccmin --rollback`.

### Permission issues with symlink install
Use bashrc method instead, or run with sudo.

## Requirements

- Python 3.8+
- Claude Code or Claude-Code-Router installed
- Unix-like environment (Linux, macOS)

## License

This project is released into the public domain.

---
*Last verified: Claude Code v2.1.114*
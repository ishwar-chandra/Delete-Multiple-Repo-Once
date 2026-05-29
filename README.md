# 🧹 GitHub Repo Remover

A GUI application for bulk deletion of GitHub repositories with encrypted token storage.

## Features

- **Bulk Repository Management**: View and delete multiple repositories at once
- **Encrypted Token Storage**: Securely cache your GitHub token locally
- **Filter & Search**: Find repositories quickly with built-in filtering
- **Modern UI**: Clean interface with multiple themes
- **Progress Tracking**: Real-time deletion progress and activity logs

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python github_multiple_delete_gui.py
```

## Usage

1. **Setup Token**: Enter your GitHub Personal Access Token (PAT)
2. **Load Repositories**: Click "Load Repos" to fetch your owned repositories
3. **Filter**: Use the search box to filter repositories by name
4. **Select**: Choose repositories to delete (Select All/Clear Selection buttons available)
5. **Delete**: Click "Delete Selected" to permanently remove repositories

## Token Security

- Tokens are encrypted using Fernet encryption before storage
- Cached in `~/.github_cleaner/` directory
- Use "Clear Cache" button to remove stored token
- Token auto-loads on app restart

## Requirements

- Python 3.7+
- GitHub Personal Access Token with `delete_repo` permission

## Dependencies

- `requests` - GitHub API communication
- `ttkbootstrap` - Modern UI components
- `cryptography` - Token encryption

## ⚠️ Warning

This tool permanently deletes repositories. Use with caution and ensure you have backups of important code.

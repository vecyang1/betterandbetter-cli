"""
Synchronization and Backup utilities for BetterAndBetter.
Manages bi-directional synchronization between macOS live preferences and Git backup repo.
"""

import os
import shutil
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List

from .constants import (
    BACKUP_DIR,
    LIVE_HELPER_PREFS_PATH,
    LIVE_PREFS_PATH,
    LIVE_PRESETS_DIR,
    REPO_BACKUP_SCRIPT,
    REPO_DIR,
    REPO_HELPER_PREFS_PATH,
    REPO_PREFS_PATH,
    REPO_PRESETS_DIR,
)
from .plist_manager import flush_cfprefsd, restart_bab


def sync_live_to_git(dry_run: bool = False) -> Dict[str, Any]:
    """
    Sync configuration from Live preferences into Git backup repository.
    """
    actions = []

    # 1. Main plist
    if os.path.exists(LIVE_PREFS_PATH):
        actions.append({
            "source": LIVE_PREFS_PATH,
            "dest": REPO_PREFS_PATH,
            "type": "file",
        })

    # 2. Helper plist
    if os.path.exists(LIVE_HELPER_PREFS_PATH):
        actions.append({
            "source": LIVE_HELPER_PREFS_PATH,
            "dest": REPO_HELPER_PREFS_PATH,
            "type": "file",
        })

    # 3. Presets directory
    if os.path.exists(LIVE_PRESETS_DIR):
        actions.append({
            "source": LIVE_PRESETS_DIR,
            "dest": REPO_PRESETS_DIR,
            "type": "directory",
        })

    if not dry_run:
        for act in actions:
            if act["type"] == "file":
                shutil.copy2(act["source"], act["dest"])
            elif act["type"] == "directory":
                # rsync directory
                os.makedirs(act["dest"], exist_ok=True)
                subprocess.run(
                    ["rsync", "-a", "--delete", f"{act['source']}/", f"{act['dest']}/"],
                    capture_output=True,
                    check=False
                )

    return {
        "status": "success",
        "dry_run": dry_run,
        "direction": "live -> git",
        "actions": actions,
        "repo_dir": REPO_DIR,
    }


def sync_git_to_live(dry_run: bool = False, reload_bab: bool = False) -> Dict[str, Any]:
    """
    Restore configuration from Git backup repository into macOS Live preferences.
    Creates safety backups of live preferences before overwriting.
    """
    actions = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # 1. Main plist
    if os.path.exists(REPO_PREFS_PATH):
        actions.append({
            "source": REPO_PREFS_PATH,
            "dest": LIVE_PREFS_PATH,
            "type": "file",
        })

    # 2. Helper plist
    if os.path.exists(REPO_HELPER_PREFS_PATH):
        actions.append({
            "source": REPO_HELPER_PREFS_PATH,
            "dest": LIVE_HELPER_PREFS_PATH,
            "type": "file",
        })

    # 3. Presets directory
    if os.path.exists(REPO_PRESETS_DIR):
        actions.append({
            "source": REPO_PRESETS_DIR,
            "dest": LIVE_PRESETS_DIR,
            "type": "directory",
        })

    backup_files = []
    if not dry_run:
        # Pre-backup live files
        if os.path.exists(LIVE_PREFS_PATH):
            bf = os.path.join(BACKUP_DIR, f"cn.better365.BetterAndBetter.plist.{timestamp}.pre_restore.bak")
            shutil.copy2(LIVE_PREFS_PATH, bf)
            backup_files.append(bf)

        if os.path.exists(LIVE_HELPER_PREFS_PATH):
            bf = os.path.join(BACKUP_DIR, f"com.better365.BetterAndBetterHelper.plist.{timestamp}.pre_restore.bak")
            shutil.copy2(LIVE_HELPER_PREFS_PATH, bf)
            backup_files.append(bf)

        for act in actions:
            if act["type"] == "file":
                shutil.copy2(act["source"], act["dest"])
            elif act["type"] == "directory":
                os.makedirs(act["dest"], exist_ok=True)
                subprocess.run(
                    ["rsync", "-a", "--delete", f"{act['source']}/", f"{act['dest']}/"],
                    capture_output=True,
                    check=False
                )

        flush_cfprefsd()

    reloaded = False
    if reload_bab and not dry_run:
        reloaded = restart_bab()

    return {
        "status": "success",
        "dry_run": dry_run,
        "direction": "git -> live",
        "actions": actions,
        "backup_files": backup_files,
        "reloaded": reloaded,
    }


def run_backup() -> Dict[str, Any]:
    """Execute the repository backup.sh script to commit and push changes."""
    if not os.path.exists(REPO_BACKUP_SCRIPT):
        raise FileNotFoundError(f"Backup script not found: {REPO_BACKUP_SCRIPT}")

    log_file = "/tmp/bab-backup.log"
    start_pos = 0
    if os.path.exists(log_file):
        try:
            start_pos = os.path.getsize(log_file)
        except OSError:
            pass

    res = subprocess.run(
        ["/bin/bash", REPO_BACKUP_SCRIPT],
        capture_output=True,
        text=True,
        check=False
    )

    new_logs = ""
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", errors="replace") as f:
                f.seek(start_pos)
                new_logs = f.read().strip()
        except OSError:
            pass

    combined_output = res.stdout
    if new_logs:
        combined_output = f"{combined_output}\n{new_logs}".strip() if combined_output else new_logs

    return {
        "returncode": res.returncode,
        "stdout": combined_output,
        "stderr": res.stderr,
        "log_messages": new_logs,
    }

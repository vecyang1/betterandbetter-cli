"""
BetterAndBetter LaunchAgent Daemon Manager and Observer.
Inspects, installs, and manages the com.vec.betterandbetter-backup LaunchAgent.
Provides UI observability for backup status, trigger policies, and health receipts.
"""

import json
import os
import plistlib
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    BACKUP_LOG_PATH,
    BACKUP_RECEIPT_PATH,
    BACKUP_TMP_LOG_PATH,
    LAUNCHD_LABEL,
    LAUNCHD_PLIST_PATH,
    LEGACY_LAUNCHD_LABEL,
    LEGACY_LAUNCHD_PLIST_PATH,
    LIVE_HELPER_PREFS_PATH,
    LIVE_PREFS_PATH,
    REPO_BACKUP_SCRIPT,
)


def get_daemon_status() -> Dict[str, Any]:
    """
    Inspect the current state of the LaunchAgent backup daemon.
    Checks:
    - Standard plist existence and validity
    - launchctl loaded status, PID, and last exit code
    - Legacy daemon residue (com.user.betterandbetter-backup)
    - Latest execution receipt
    - Recent log lines
    """
    installed = os.path.exists(LAUNCHD_PLIST_PATH)
    plist_valid = False
    watch_paths: List[str] = []
    throttle_interval: int = 30
    calendar_interval: Dict[str, Any] = {}
    program_args: List[str] = []

    if installed:
        try:
            with open(LAUNCHD_PLIST_PATH, "rb") as f:
                plist_data = plistlib.load(f)
                plist_valid = True
                watch_paths = plist_data.get("WatchPaths", [])
                throttle_interval = plist_data.get("ThrottleInterval", 30)
                calendar_interval = plist_data.get("StartCalendarInterval", {})
                program_args = plist_data.get("ProgramArguments", [])
        except Exception:
            plist_valid = False

    # Check launchctl list
    loaded = False
    pid: Optional[int] = None
    last_exit_code: Optional[int] = None
    try:
        res = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
        for line in res.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3 and parts[2] == LAUNCHD_LABEL:
                loaded = True
                pid = int(parts[0]) if parts[0] != "-" and parts[0].isdigit() else None
                last_exit_code = int(parts[1]) if parts[1].isdigit() else None
                break
    except Exception:
        pass

    # Check legacy
    legacy_loaded = False
    try:
        res = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
        for line in res.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3 and parts[2] == LEGACY_LAUNCHD_LABEL:
                legacy_loaded = True
                break
    except Exception:
        pass

    legacy_plist_exists = os.path.exists(LEGACY_LAUNCHD_PLIST_PATH)

    # Read latest receipt
    receipt: Optional[Dict[str, Any]] = None
    if os.path.exists(BACKUP_RECEIPT_PATH):
        try:
            with open(BACKUP_RECEIPT_PATH, "r", encoding="utf-8") as f:
                receipt = json.load(f)
        except Exception:
            receipt = None

    # Read last log lines
    recent_logs: List[str] = []
    log_src = BACKUP_LOG_PATH if os.path.exists(BACKUP_LOG_PATH) else BACKUP_TMP_LOG_PATH
    if os.path.exists(log_src):
        try:
            with open(log_src, "r", errors="replace") as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
                recent_logs = lines[-5:]
        except Exception:
            pass

    return {
        "installed": installed,
        "plist_path": LAUNCHD_PLIST_PATH,
        "plist_valid": plist_valid,
        "label": LAUNCHD_LABEL,
        "loaded": loaded,
        "pid": pid,
        "last_exit_code": last_exit_code,
        "watch_paths": watch_paths,
        "throttle_interval": throttle_interval,
        "calendar_interval": calendar_interval,
        "program_args": program_args,
        "legacy_detected": legacy_loaded or legacy_plist_exists,
        "legacy_loaded": legacy_loaded,
        "legacy_plist_exists": legacy_plist_exists,
        "receipt": receipt,
        "recent_logs": recent_logs,
    }


def generate_launchd_plist_dict(backup_script: Optional[str] = None) -> Dict[str, Any]:
    """Generate the canonical launchd property list dictionary."""
    script_path = backup_script or REPO_BACKUP_SCRIPT
    return {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": ["/bin/bash", script_path],
        "WatchPaths": [
            LIVE_PREFS_PATH,
            LIVE_HELPER_PREFS_PATH,
        ],
        "ThrottleInterval": 30,
        "StartCalendarInterval": {
            "Hour": 11,
            "Minute": 0,
        },
        "StandardOutPath": BACKUP_TMP_LOG_PATH,
        "StandardErrorPath": BACKUP_TMP_LOG_PATH,
    }


def install_daemon(
    backup_script: Optional[str] = None,
    force: bool = False
) -> Dict[str, Any]:
    """
    Install and activate the com.vec.betterandbetter-backup LaunchAgent.
    """
    script_path = backup_script or REPO_BACKUP_SCRIPT
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"备份执行脚本不存在: {script_path}")

    # Ensure executable
    os.chmod(script_path, 0o755)

    # 1. Purge legacy if exists
    if os.path.exists(LEGACY_LAUNCHD_PLIST_PATH):
        subprocess.run(["launchctl", "unload", "-w", LEGACY_LAUNCHD_PLIST_PATH], capture_output=True, check=False)
        try:
            os.remove(LEGACY_LAUNCHD_PLIST_PATH)
        except OSError:
            pass

    # 2. Check if already loaded
    status = get_daemon_status()
    if status["loaded"]:
        if not force:
            return {
                "status": "already_installed",
                "message": f"LaunchAgent [{LAUNCHD_LABEL}] 已处于加载激活状态。如需重新安装，请指定 --force。",
                "details": status,
            }
        subprocess.run(["launchctl", "unload", "-w", LAUNCHD_PLIST_PATH], capture_output=True, check=False)

    # 3. Write plist
    os.makedirs(os.path.dirname(LAUNCHD_PLIST_PATH), exist_ok=True)
    plist_dict = generate_launchd_plist_dict(script_path)
    with open(LAUNCHD_PLIST_PATH, "wb") as f:
        plistlib.dump(plist_dict, f)

    # 4. Load via launchctl
    res = subprocess.run(["launchctl", "load", "-w", LAUNCHD_PLIST_PATH], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"launchctl load 失败: {res.stderr or res.stdout}")

    new_status = get_daemon_status()
    return {
        "status": "installed",
        "message": f"成功部署并激活 LaunchAgent [{LAUNCHD_LABEL}]",
        "details": new_status,
    }


def uninstall_daemon() -> Dict[str, Any]:
    """
    Deactivate and remove the com.vec.betterandbetter-backup LaunchAgent.
    """
    if os.path.exists(LAUNCHD_PLIST_PATH):
        subprocess.run(["launchctl", "unload", "-w", LAUNCHD_PLIST_PATH], capture_output=True, check=False)
        try:
            os.remove(LAUNCHD_PLIST_PATH)
        except OSError:
            pass

    return {
        "status": "uninstalled",
        "message": f"已成功注销并清理 LaunchAgent [{LAUNCHD_LABEL}]",
    }

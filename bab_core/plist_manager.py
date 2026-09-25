"""
Plist manager for BetterAndBetter.
Handles safe loading, atomic writing, automated pre-mutation backups,
deep structural diffing, and macOS preferences cache flushing.
"""

import fcntl
import hashlib
import os
import plistlib
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    BACKUP_DIR,
    LIVE_PREFS_PATH,
    REPO_PREFS_PATH,
    RULE_CATEGORIES,
)
from .keycodes import format_shortcut, normalize_flags


class PlistLock:
    """Inter-process file lock for safe atomic mutations across concurrent sessions."""
    def __init__(self, path: str):
        h = hashlib.md5(os.path.abspath(path).encode("utf-8")).hexdigest()
        self.lock_path = os.path.join(tempfile.gettempdir(), f"bab_plist_{h}.lock")
        self.fd = None

    def __enter__(self):
        try:
            self.fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
            fcntl.flock(self.fd, fcntl.LOCK_EX)
        except OSError:
            self.fd = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None


def load_plist(path: str) -> Dict[str, Any]:
    """Load and parse an Apple property list file."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Plist file not found at: {path}")
    with open(path, "rb") as f:
        return plistlib.load(f)


def _detect_plist_format(path: str) -> plistlib.PlistFormat:
    """Detect whether a plist file is binary or XML, defaulting to binary for macOS prefs."""
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                header = f.read(32)
                if header.startswith(b"bplist"):
                    return plistlib.FMT_BINARY
                elif b"<?xml" in header or b"<!DOCTYPE" in header:
                    return plistlib.FMT_XML
        except Exception:
            pass
    return plistlib.FMT_BINARY


def save_plist(path: str, data: Dict[str, Any], backup: bool = True) -> str:
    """
    Atomically save a plist dictionary to disk.
    Preserves original binary/XML format (defaulting to binary for macOS preferences).
    If backup is True, saves a timestamped backup to ~/.bab_backups/.
    Verifies read-after-write to guarantee integrity.
    Returns the backup path if created, else empty string.
    """
    backup_file = ""
    if backup and os.path.exists(path):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        filename = os.path.basename(path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_file = os.path.join(BACKUP_DIR, f"{filename}.{timestamp}.bak")
        shutil.copy2(path, backup_file)

    fmt = _detect_plist_format(path)
    # Atomic write pattern: write to tmp file then atomic replace
    tmp_path = f"{path}.tmp.{os.getpid()}.{int(time.time()*1000)}"
    try:
        with open(tmp_path, "wb") as f:
            plistlib.dump(data, f, fmt=fmt)
        os.replace(tmp_path, path)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise IOError(f"Failed to atomically save plist to {path}: {e}")

    # Read-after-write verification
    try:
        verify_data = load_plist(path)
        if not isinstance(verify_data, dict):
            raise ValueError("Verification failed: loaded data is not a dictionary.")
    except Exception as e:
        # If backup exists, restore it
        if backup_file and os.path.exists(backup_file):
            shutil.copy2(backup_file, path)
        raise IOError(f"Read-after-write verification failed for {path}: {e}")

    return backup_file


def get_live_plist() -> Dict[str, Any]:
    """Load the current live BetterAndBetter preferences."""
    return load_plist(LIVE_PREFS_PATH)


def get_git_plist() -> Dict[str, Any]:
    """Load the git backup repository BetterAndBetter preferences."""
    return load_plist(REPO_PREFS_PATH)


def flush_cfprefsd() -> None:
    """Flush macOS cfprefsd cache so system reloads plist from disk."""
    try:
        subprocess.run(["killall", "cfprefsd"], capture_output=True, check=False)
    except Exception:
        pass


def restart_bab() -> bool:
    """Cleanly hot-reload BetterAndBetter process with cfprefsd flush."""
    try:
        subprocess.run(["killall", "BetterAndBetter"], capture_output=True, check=False)
        flush_cfprefsd()
        time.sleep(0.6)
        res = subprocess.run(["open", "-a", "BetterAndBetter"], capture_output=True, text=True, check=False)
        return res.returncode == 0
    except Exception:
        return False


def _rule_signature(category: str, rule: Dict[str, Any]) -> str:
    """Generate a unique signature for a rule to identify matches across datasets."""
    gesture = rule.get("Gesture")
    if category == "ruleOfKeyboard" and isinstance(gesture, dict):
        kc = gesture.get("keyCode")
        flags = normalize_flags(gesture.get("modifierFlags"))
        return f"KEY:{kc}:{flags}"
    elif isinstance(gesture, str):
        return f"STR:{gesture.strip()}"
    elif isinstance(gesture, dict):
        return f"DICT:{gesture}"
    return f"RAW:{str(gesture)}"


def _normalize_enable(val: Any) -> bool:
    """Normalize Enable field to boolean."""
    return str(val) in ("1", "True", "true")


def diff_plists(live_data: Dict[str, Any], git_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform deep structural comparison between Live and Git plists.
    Detects added/removed apps, rule modifications, and script changes.
    """
    diff_report = {
        "is_synced": True,
        "categories": {},
        "scripts": {
            "only_in_live": [],
            "only_in_git": [],
            "modified": [],
        },
        "summary": [],
    }

    # 1. Compare rule categories
    for cat_slug, cat_key in RULE_CATEGORIES.items():
        if cat_key == "ruleOfAppleScript":
            continue

        live_apps_map = {item.get("AppName"): item for item in live_data.get(cat_key, []) if isinstance(item, dict)}
        git_apps_map = {item.get("AppName"): item for item in git_data.get(cat_key, []) if isinstance(item, dict)}

        live_apps = set(live_apps_map.keys())
        git_apps = set(git_apps_map.keys())

        cat_diff = {
            "apps_only_in_live": sorted(list(live_apps - git_apps)),
            "apps_only_in_git": sorted(list(git_apps - live_apps)),
            "apps_with_changes": {},
        }

        common_apps = live_apps & git_apps
        for app in sorted(common_apps):
            live_rules = [r for r in live_apps_map[app].get("All Rules", []) if isinstance(r, dict)]
            git_rules = [r for r in git_apps_map[app].get("All Rules", []) if isinstance(r, dict)]

            matched_live_indices = set()
            matched_git_indices = set()
            modified = []

            # Pass 1: exact matches at same index
            min_len = min(len(live_rules), len(git_rules))
            for i in range(min_len):
                rl = live_rules[i]
                rg = git_rules[i]
                if (
                    rl.get("Gesture") == rg.get("Gesture")
                    and rl.get("Action") == rg.get("Action")
                    and str(rl.get("Note", "")).strip() == str(rg.get("Note", "")).strip()
                    and _normalize_enable(rl.get("Enable")) == _normalize_enable(rg.get("Enable"))
                ):
                    matched_live_indices.add(i)
                    matched_git_indices.add(i)

            # Pass 2: exact matches elsewhere in list
            for i, rl in enumerate(live_rules):
                if i in matched_live_indices:
                    continue
                for j, rg in enumerate(git_rules):
                    if j in matched_git_indices:
                        continue
                    if (
                        rl.get("Gesture") == rg.get("Gesture")
                        and rl.get("Action") == rg.get("Action")
                        and str(rl.get("Note", "")).strip() == str(rg.get("Note", "")).strip()
                        and _normalize_enable(rl.get("Enable")) == _normalize_enable(rg.get("Enable"))
                    ):
                        matched_live_indices.add(i)
                        matched_git_indices.add(j)
                        break

            # Pass 3: same gesture and action, but different enable / note
            for i, rl in enumerate(live_rules):
                if i in matched_live_indices:
                    continue
                for j, rg in enumerate(git_rules):
                    if j in matched_git_indices:
                        continue
                    if (
                        rl.get("Gesture") == rg.get("Gesture")
                        and rl.get("Action") == rg.get("Action")
                    ):
                        matched_live_indices.add(i)
                        matched_git_indices.add(j)
                        live_en = _normalize_enable(rl.get("Enable"))
                        git_en = _normalize_enable(rg.get("Enable"))
                        changes = {}
                        if live_en != git_en:
                            changes["enable"] = {"live": live_en, "git": git_en}
                        if str(rl.get("Note", "")).strip() != str(rg.get("Note", "")).strip():
                            changes["note"] = {"live": rl.get("Note"), "git": rg.get("Note")}
                        if changes:
                            modified.append({
                                "index": i,
                                "gesture": rl.get("Gesture"),
                                "changes": changes,
                            })
                        break

            # Pass 4: same non-empty gesture, but action changed
            for i, rl in enumerate(live_rules):
                if i in matched_live_indices:
                    continue
                g_live = rl.get("Gesture")
                if not g_live or g_live == {} or g_live == "Customize":
                    continue
                for j, rg in enumerate(git_rules):
                    if j in matched_git_indices:
                        continue
                    if g_live == rg.get("Gesture"):
                        matched_live_indices.add(i)
                        matched_git_indices.add(j)
                        live_en = _normalize_enable(rl.get("Enable"))
                        git_en = _normalize_enable(rg.get("Enable"))
                        live_act = rl.get("Action")
                        git_act = rg.get("Action")
                        changes = {}
                        if live_act != git_act:
                            changes["action"] = {"live": live_act, "git": git_act}
                        if live_en != git_en:
                            changes["enable"] = {"live": live_en, "git": git_en}
                        if changes:
                            modified.append({
                                "index": i,
                                "gesture": g_live,
                                "changes": changes,
                            })
                        break

            # Pass 5: gestureless rules (empty dict or None), match by action
            for i, rl in enumerate(live_rules):
                if i in matched_live_indices:
                    continue
                g_live = rl.get("Gesture")
                if g_live not in ({}, None, ""):
                    continue
                for j, rg in enumerate(git_rules):
                    if j in matched_git_indices:
                        continue
                    if rg.get("Gesture") in ({}, None, "") and rl.get("Action") == rg.get("Action"):
                        matched_live_indices.add(i)
                        matched_git_indices.add(j)
                        live_en = _normalize_enable(rl.get("Enable"))
                        git_en = _normalize_enable(rg.get("Enable"))
                        changes = {}
                        if live_en != git_en:
                            changes["enable"] = {"live": live_en, "git": git_en}
                        if changes:
                            modified.append({
                                "index": i,
                                "gesture": g_live,
                                "changes": changes,
                            })
                        break

            added_count = len(live_rules) - len(matched_live_indices)
            removed_count = len(git_rules) - len(matched_git_indices)

            if added_count > 0 or removed_count > 0 or modified:
                diff_report["is_synced"] = False
                cat_diff["apps_with_changes"][app] = {
                    "live_count": len(live_rules),
                    "git_count": len(git_rules),
                    "added_in_live": added_count,
                    "removed_in_live": removed_count,
                    "modified_count": len(modified),
                    "modified_details": modified,
                }

        if cat_diff["apps_only_in_live"] or cat_diff["apps_only_in_git"] or cat_diff["apps_with_changes"]:
            diff_report["is_synced"] = False
            diff_report["categories"][cat_key] = cat_diff

    # 2. Compare ruleOfAppleScript
    live_scripts = {s.get("Id", s.get("Name")): s for s in live_data.get("ruleOfAppleScript", []) if isinstance(s, dict)}
    git_scripts = {s.get("Id", s.get("Name")): s for s in git_data.get("ruleOfAppleScript", []) if isinstance(s, dict)}

    live_s_keys = set(live_scripts.keys())
    git_s_keys = set(git_scripts.keys())

    for k in live_s_keys - git_s_keys:
        diff_report["is_synced"] = False
        diff_report["scripts"]["only_in_live"].append(live_scripts[k].get("Name", k))

    for k in git_s_keys - live_s_keys:
        diff_report["is_synced"] = False
        diff_report["scripts"]["only_in_git"].append(git_scripts[k].get("Name", k))

    for k in live_s_keys & git_s_keys:
        sl = live_scripts[k]
        sg = git_scripts[k]
        if sl.get("AppleScript") != sg.get("AppleScript") or sl.get("Name") != sg.get("Name"):
            diff_report["is_synced"] = False
            diff_report["scripts"]["modified"].append({
                "id": k,
                "name": sl.get("Name"),
                "code_changed": sl.get("AppleScript") != sg.get("AppleScript"),
                "name_changed": sl.get("Name") != sg.get("Name"),
            })

    # Summary string generation
    if diff_report["is_synced"]:
        diff_report["summary"].append("Live preferences 与 Git 备份完全一致，无状态漂移。")
    else:
        for cat_key, cdiff in diff_report["categories"].items():
            if cdiff["apps_only_in_live"]:
                diff_report["summary"].append(f"{cat_key}: 仅在 Live 存在的应用: {', '.join(cdiff['apps_only_in_live'])}")
            if cdiff["apps_only_in_git"]:
                diff_report["summary"].append(f"{cat_key}: 仅在 Git 存在的应用: {', '.join(cdiff['apps_only_in_git'])}")
            for app, chg in cdiff["apps_with_changes"].items():
                diff_report["summary"].append(
                    f"{cat_key} [{app}]: 规则数量 Live={chg['live_count']} vs Git={chg['git_count']}, "
                    f"新增={chg['added_in_live']}, 缺失={chg['removed_in_live']}, 变更={chg['modified_count']}"
                )
        if diff_report["scripts"]["only_in_live"]:
            diff_report["summary"].append(f"AppleScript: 仅在 Live 中存在: {', '.join(diff_report['scripts']['only_in_live'])}")
        if diff_report["scripts"]["only_in_git"]:
            diff_report["summary"].append(f"AppleScript: 仅在 Git 中存在: {', '.join(diff_report['scripts']['only_in_git'])}")
        if diff_report["scripts"]["modified"]:
            mod_names = [s["name"] for s in diff_report["scripts"]["modified"]]
            diff_report["summary"].append(f"AppleScript: 内容已修改: {', '.join(mod_names)}")

    return diff_report

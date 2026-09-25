"""
BetterAndBetter Inspector & Detector.
Checks running processes, inspects apps, rules, categories, and AppleScripts.
"""

import os
import plistlib
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    APP_BUNDLE_PATH,
    APP_PROCESS_NAME,
    HELPER_PROCESS_NAME,
    KNOWN_APP_ALIASES,
    LIVE_PREFS_PATH,
    REPO_PREFS_PATH,
    RULE_CATEGORIES,
)
from .daemon import get_daemon_status
from .keycodes import format_shortcut
from .models import AppleScriptItem, AppSummary, Rule, StatusInfo
from .plist_manager import diff_plists, load_plist, _normalize_enable


def _get_process_info(process_name: str) -> Tuple[bool, Optional[int]]:
    """Check if a process is running and return (is_running, pid)."""
    try:
        res = subprocess.run(["pgrep", "-x", process_name], capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            pids = res.stdout.strip().split()
            return True, int(pids[0])
    except Exception:
        pass

    # Fallback to ps
    try:
        res = subprocess.run(["ps", "-ax", "-o", "pid,command"], capture_output=True, text=True, check=False)
        for line in res.stdout.splitlines():
            if process_name in line and "grep" not in line:
                pid_str = line.strip().split()[0]
                return True, int(pid_str)
    except Exception:
        pass
    return False, None


def get_app_version() -> str:
    """Retrieve CFBundleShortVersionString from BetterAndBetter.app."""
    info_path = os.path.join(APP_BUNDLE_PATH, "Contents", "Info.plist")
    if os.path.exists(info_path):
        try:
            with open(info_path, "rb") as f:
                info = plistlib.load(f)
                return info.get("CFBundleShortVersionString", "Unknown")
        except Exception:
            pass
    return "Not Installed"


def get_status(live_path: str = LIVE_PREFS_PATH, git_path: str = REPO_PREFS_PATH) -> StatusInfo:
    """Gather comprehensive system and configuration status for BetterAndBetter."""
    app_installed = os.path.exists(APP_BUNDLE_PATH)
    app_version = get_app_version() if app_installed else "None"
    app_running, app_pid = _get_process_info(APP_PROCESS_NAME)
    helper_running, helper_pid = _get_process_info(HELPER_PROCESS_NAME)

    live_exists = os.path.exists(live_path)
    live_size = os.path.getsize(live_path) if live_exists else 0
    live_mtime = (
        datetime.fromtimestamp(os.path.getmtime(live_path)).strftime("%Y-%m-%d %H:%M:%S")
        if live_exists else None
    )

    git_exists = os.path.exists(git_path)
    git_size = os.path.getsize(git_path) if git_exists else 0
    git_mtime = (
        datetime.fromtimestamp(os.path.getmtime(git_path)).strftime("%Y-%m-%d %H:%M:%S")
        if git_exists else None
    )

    is_synced = False
    diff_summary = "无法对比（文件缺失）"
    category_stats = {}
    total_apps_set = set()
    total_rules = 0
    total_enabled = 0

    if live_exists:
        try:
            live_data = load_plist(live_path)
            if git_exists:
                git_data = load_plist(git_path)
                diff = diff_plists(live_data, git_data)
                is_synced = diff["is_synced"]
                diff_summary = (
                    "完全同步 (一致)"
                    if is_synced
                    else f"存在差异 ({len(diff['summary'])} 项待对账)"
                )
            else:
                diff_summary = "Git 备份文件不存在"

            # Compute stats from live data
            for cat_slug, cat_key in RULE_CATEGORIES.items():
                if cat_key == "ruleOfAppleScript":
                    scripts = live_data.get(cat_key, [])
                    category_stats[cat_slug] = {
                        "total": len(scripts),
                        "enabled": len(scripts),
                    }
                    continue

                items = live_data.get(cat_key, [])
                cat_total = 0
                cat_enabled = 0
                for item in items:
                    if isinstance(item, dict):
                        app_name = item.get("AppName", "")
                        if app_name:
                            total_apps_set.add(app_name)
                        rules = item.get("All Rules", [])
                        cat_total += len(rules)
                        cat_enabled += sum(1 for r in rules if _normalize_enable(r.get("Enable")))

                category_stats[cat_slug] = {
                    "total": cat_total,
                    "enabled": cat_enabled,
                }
                total_rules += cat_total
                total_enabled += cat_enabled

        except Exception as e:
            diff_summary = f"状态分析错误: {e}"

    return StatusInfo(
        app_installed=app_installed,
        app_version=app_version,
        app_path=APP_BUNDLE_PATH,
        app_running=app_running,
        app_pid=app_pid,
        helper_running=helper_running,
        helper_pid=helper_pid,
        live_plist_exists=live_exists,
        live_plist_size=live_size,
        live_plist_mtime=live_mtime,
        git_plist_exists=git_exists,
        git_plist_size=git_size,
        git_plist_mtime=git_mtime,
        is_synced=is_synced,
        diff_summary=diff_summary,
        total_apps=len(total_apps_set),
        total_rules=total_rules,
        total_enabled=total_enabled,
        category_stats=category_stats,
        daemon_status=get_daemon_status(),
    )


def resolve_app_name(data: Dict[str, Any], app_query: str) -> Tuple[str, bool]:
    """
    Resolve an app query (e.g. 'obsidian', 'Antigravity', 'finder', 'ego lite')
    to the configured AppName in BAB.
    Returns (app_name, is_configured).
    """
    query = app_query.strip().lower()

    # 1. Check known aliases
    if query in KNOWN_APP_ALIASES:
        canonical = KNOWN_APP_ALIASES[query]
        return canonical, True

    # 2. Collect all configured apps in data
    configured_apps = set()
    for cat_key in RULE_CATEGORIES.values():
        if cat_key == "ruleOfAppleScript":
            continue
        for item in data.get(cat_key, []):
            if isinstance(item, dict) and item.get("AppName"):
                configured_apps.add(item["AppName"])

    # Exact match (case-insensitive)
    for app in configured_apps:
        if app.lower() == query:
            return app, True

    # Substring match (e.g. 'obsidian' matches 'md.obsidian')
    matches = [app for app in configured_apps if query in app.lower()]
    if len(matches) == 1:
        return matches[0], True
    elif len(matches) > 1:
        # Prefer exact end or start
        for m in matches:
            if m.lower().endswith(f".{query}") or m.lower() == query:
                return m, True
        return matches[0], True

    # Normalized match (stripping spaces, dots, hyphens, underscores)
    import re
    q_norm = re.sub(r"[^a-z0-9]", "", query)
    if q_norm and len(q_norm) >= 3:
        for app in configured_apps:
            app_norm = re.sub(r"[^a-z0-9]", "", app.lower())
            if q_norm in app_norm:
                return app, True

    # Not found in configured apps
    return app_query, False


def format_action_display(action_dict: Any, scripts_map: Dict[str, str]) -> Tuple[str, str]:
    """
    Convert an Action dictionary into (action_type, human_readable_display).
    Resolves AppleScript IDs to their script names.
    """
    if not isinstance(action_dict, dict):
        return "Unknown", str(action_dict)

    atype = action_dict.get("ActionType", "")
    act = action_dict.get("Action")

    if atype == "Preset":
        return "Preset", str(act)
    elif atype == "Shortcut Keys":
        if isinstance(act, dict):
            s_name = act.get("ShortcutName")
            if s_name:
                return "Shortcut Keys", s_name
            kc = act.get("keyCode")
            mf = act.get("modifierFlags")
            return "Shortcut Keys", format_shortcut(kc, mf)
        return "Shortcut Keys", str(act)
    elif atype == "AppleScript":
        script_id = str(act)
        script_name = scripts_map.get(script_id, script_id)
        return "AppleScript", f"{script_name} (ID: {script_id[:8]}...)"
    elif "OpenArr" in action_dict:
        targets = action_dict.get("OpenArr", [])
        return "Open...", f"Open: {', '.join(targets)}"
    elif not atype and not act:
        return "<None>", "无动作 / 未指定"

    return atype or "Other", str(act)


def get_scripts_map(data: Dict[str, Any]) -> Dict[str, str]:
    """Map AppleScript Id -> Name for clean action display."""
    mapping = {}
    for s in data.get("ruleOfAppleScript", []):
        if isinstance(s, dict) and s.get("Id"):
            mapping[s["Id"]] = s.get("Name", s["Id"])
    return mapping


def inspect_rules(
    data: Dict[str, Any],
    category_filter: Optional[str] = None,
    app_filter: Optional[str] = None,
    enabled_only: bool = False
) -> List[Rule]:
    """
    Inspect and return all rules matching the filters.
    """
    scripts_map = get_scripts_map(data)
    rules_list: List[Rule] = []

    # Determine which categories to inspect
    target_categories = []
    if category_filter:
        cat_key = RULE_CATEGORIES.get(category_filter.lower(), category_filter)
        target_categories = [cat_key]
    else:
        target_categories = [k for k in RULE_CATEGORIES.values() if k != "ruleOfAppleScript"]

    for cat_key in target_categories:
        items = data.get(cat_key, [])
        for item in items:
            if not isinstance(item, dict):
                continue
            app_name = item.get("AppName", "Unknown")

            if app_filter:
                # filter matching
                if app_filter.lower() not in app_name.lower():
                    continue

            rules = item.get("All Rules", [])
            for idx, r in enumerate(rules):
                if not isinstance(r, dict):
                    continue

                en = _normalize_enable(r.get("Enable"))
                if enabled_only and not en:
                    continue

                # Format gesture
                gesture_raw = r.get("Gesture")
                if cat_key == "ruleOfKeyboard" and isinstance(gesture_raw, dict):
                    kc = gesture_raw.get("keyCode")
                    mf = gesture_raw.get("modifierFlags")
                    if kc is None and not mf:
                        gesture_display = "(未分配快捷键)"
                    else:
                        gesture_display = format_shortcut(kc, mf)
                else:
                    gesture_display = str(gesture_raw)

                # Format action
                act_raw = r.get("Action")
                action_type, action_display = format_action_display(act_raw, scripts_map)

                rule_obj = Rule(
                    app=app_name,
                    category=cat_key,
                    index=idx,
                    gesture_display=gesture_display,
                    gesture_raw=gesture_raw,
                    action_type=action_type,
                    action_display=action_display,
                    action_raw=act_raw,
                    enabled=en,
                    note=str(r.get("Note", "")).strip(),
                    is_app_specific=(app_name != "All Applications"),
                    raw_dict=r,
                )
                rules_list.append(rule_obj)

    return rules_list


def inspect_scripts(data: Dict[str, Any], search: Optional[str] = None) -> List[AppleScriptItem]:
    """Inspect AppleScript items from ruleOfAppleScript."""
    items = []
    for s in data.get("ruleOfAppleScript", []):
        if not isinstance(s, dict):
            continue
        name = s.get("Name", "")
        script = s.get("AppleScript", "")
        note = s.get("Note", "")
        sid = s.get("Id", "")

        if search:
            q = search.lower()
            if q not in name.lower() and q not in script.lower() and q not in note.lower() and q not in sid.lower():
                continue

        items.append(AppleScriptItem(
            id=sid,
            name=name,
            script=script,
            note=note,
            edited=bool(s.get("Edited", False)),
        ))
    return items


def list_configured_apps(data: Dict[str, Any], category: Optional[str] = None) -> List[AppSummary]:
    """List all configured applications with rule counts and enabled counts."""
    target_categories = []
    if category:
        cat_key = RULE_CATEGORIES.get(category.lower(), category)
        target_categories = [cat_key]
    else:
        target_categories = [k for k in RULE_CATEGORIES.values() if k != "ruleOfAppleScript"]

    app_stats: Dict[str, Dict[str, Any]] = {}

    for cat_key in target_categories:
        for item in data.get(cat_key, []):
            if not isinstance(item, dict):
                continue
            app_name = item.get("AppName", "")
            if not app_name:
                continue

            if app_name not in app_stats:
                app_stats[app_name] = {
                    "total": 0,
                    "enabled": 0,
                    "categories": {},
                }

            rules = item.get("All Rules", [])
            r_total = len(rules)
            r_enabled = sum(1 for r in rules if _normalize_enable(r.get("Enable")))

            app_stats[app_name]["total"] += r_total
            app_stats[app_name]["enabled"] += r_enabled
            app_stats[app_name]["categories"][cat_key] = r_total

    result = []
    # Ensure 'All Applications' is first
    sorted_apps = sorted(app_stats.keys(), key=lambda x: (x != "All Applications", x.lower()))

    for app in sorted_apps:
        stats = app_stats[app]
        # Resolve friendly display name
        display_name = app
        for alias, can in KNOWN_APP_ALIASES.items():
            if can == app and alias != "all applications":
                display_name = f"{app} ({alias.title()})"
                break

        result.append(AppSummary(
            app_name=app,
            display_name=display_name,
            total_rules=stats["total"],
            enabled_rules=stats["enabled"],
            categories=stats["categories"],
        ))

    return result

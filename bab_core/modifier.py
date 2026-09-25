"""
BetterAndBetter Configurator and Mutation Engine.
Safely adds, updates, enables/disables, and removes rules and AppleScripts with
read-after-write verification, pre-mutation backups, and hot-reload.
"""

import uuid
from typing import Any, Dict, Optional, Union

from .constants import (
    LIVE_PREFS_PATH,
    RULE_CATEGORIES,
)
from .inspector import resolve_app_name
from .keycodes import (
    format_modifier_name,
    format_shortcut,
    parse_shortcut,
    shortcut_matches,
)
from .plist_manager import (
    PlistLock,
    flush_cfprefsd,
    load_plist,
    restart_bab,
    save_plist,
    _normalize_enable,
)


def add_or_update_keyboard_rule(
    plist_path: str = LIVE_PREFS_PATH,
    app_name: str = "All Applications",
    key_str: str = "",
    action_type: str = "Preset",
    action_value: str = "",
    enable: bool = True,
    note: str = "",
    reload_bab: bool = False
) -> Dict[str, Any]:
    """
    Add or update a keyboard rule for a given application.
    Creates automatic backup before writing and verifies integrity after write.
    """
    kc, mf = parse_shortcut(key_str)
    if kc is None:
        raise ValueError(f"无法解析快捷键: '{key_str}'。请使用标准格式如 '⌘B', 'cmd+b', '⇧⌘N' 等。")

    with PlistLock(plist_path):
        data = load_plist(plist_path)
        canonical_app, is_known = resolve_app_name(data, app_name)
        if is_known:
            app_name = canonical_app

        kb_list = data.setdefault("ruleOfKeyboard", [])

        # Find or create app container
        app_item = None
        for item in kb_list:
            if isinstance(item, dict) and item.get("AppName") == app_name:
                app_item = item
                break

        if app_item is None:
            app_item = {"AppName": app_name, "All Rules": []}
            kb_list.append(app_item)

        rules = app_item.setdefault("All Rules", [])

        # Construct Action dictionary
        action_dict: Dict[str, Any] = {"ActionType": action_type}
        if action_type == "Preset":
            action_dict["Action"] = action_value
        elif action_type == "Shortcut Keys":
            a_kc, a_mf = parse_shortcut(action_value)
            if a_kc is None:
                action_dict["Action"] = action_value
            else:
                action_dict["Action"] = {
                    "keyCode": a_kc,
                    "modifierFlags": a_mf,
                    "ShortcutName": format_shortcut(a_kc, a_mf),
                }
        elif action_type == "AppleScript":
            # Check if action_value is already an ID or a script name
            matched_id = None
            for s in data.get("ruleOfAppleScript", []):
                if isinstance(s, dict):
                    if s.get("Id") == action_value or s.get("Name", "").lower() == action_value.lower():
                        matched_id = s.get("Id")
                        break
            action_dict["Action"] = matched_id if matched_id else action_value
        else:
            action_dict["Action"] = action_value

        # Search existing rule by shortcut
        existing_rule = None
        for r in rules:
            if isinstance(r, dict) and shortcut_matches(r.get("Gesture"), kc, mf, exact_flags=True):
                existing_rule = r
                break

        if existing_rule:
            existing_rule["Action"] = action_dict
            existing_rule["Enable"] = 1 if enable else 0
            if note:
                existing_rule["Note"] = note
            op_type = "updated"
        else:
            new_rule = {
                "Gesture": {
                    "keyCode": kc,
                    "modifierFlags": mf,
                    "modifierFlagsName": format_modifier_name(mf),
                },
                "Action": action_dict,
                "Enable": 1 if enable else 0,
                "Note": note,
                "Modifier": " -",
            }
            rules.append(new_rule)
            op_type = "added"

        # Save atomically with backup
        backup_file = save_plist(plist_path, data, backup=True)
        flush_cfprefsd()

        reloaded = False
        if reload_bab:
            reloaded = restart_bab()

        return {
            "status": "success",
            "operation": op_type,
            "app": app_name,
            "shortcut": format_shortcut(kc, mf),
            "action_type": action_type,
            "action": action_value,
            "enable": enable,
            "backup_file": backup_file,
            "reloaded": reloaded,
        }


def toggle_rule(
    plist_path: str = LIVE_PREFS_PATH,
    app_name: str = "All Applications",
    category: str = "keyboard",
    key_or_index: Union[str, int] = "",
    index: Optional[int] = None,
    enable: Optional[bool] = None,
    reload_bab: bool = False
) -> Dict[str, Any]:
    """
    Toggle or explicitly set the Enable status of an existing rule.
    Supports targeting by explicit index, integer key_or_index, or shortcut/gesture string.
    Single-digit shortcuts ('0'-'9') match by keycode before falling back to index.
    """
    cat_key = RULE_CATEGORIES.get(category.lower(), category)

    with PlistLock(plist_path):
        data = load_plist(plist_path)
        canonical_app, is_known = resolve_app_name(data, app_name)
        if is_known:
            app_name = canonical_app

        app_item = None
        for item in data.get(cat_key, []):
            if isinstance(item, dict) and item.get("AppName") == app_name:
                app_item = item
                break

        if not app_item:
            raise ValueError(f"应用 '{app_name}' 在类别 '{cat_key}' 中未配置任何规则。")

        rules = app_item.get("All Rules", [])
        target_rule = None

        # 1. Explicit index or integer parameter
        if index is not None or (isinstance(key_or_index, int) and not isinstance(key_or_index, bool)):
            idx = index if index is not None else int(key_or_index)
            if 0 <= idx < len(rules):
                target_rule = rules[idx]
            else:
                raise IndexError(f"规则索引 {idx} 超出范围 (共 {len(rules)} 条规则)。")
        else:
            # 2. Match by shortcut/gesture string first (preserves single-digit shortcuts like '0'-'9')
            kc, mf = parse_shortcut(str(key_or_index))
            for r in rules:
                if not isinstance(r, dict):
                    continue
                if cat_key == "ruleOfKeyboard" and kc is not None:
                    if shortcut_matches(r.get("Gesture"), kc, mf, exact_flags=True):
                        target_rule = r
                        break
                elif str(r.get("Gesture")).lower() == str(key_or_index).lower():
                    target_rule = r
                    break

            # 3. Fallback: if no shortcut matched and input is pure digits, treat as index
            if target_rule is None and isinstance(key_or_index, str) and key_or_index.isdigit():
                idx = int(key_or_index)
                if 0 <= idx < len(rules):
                    target_rule = rules[idx]

        if not target_rule:
            raise ValueError(f"在应用 '{app_name}' 中未找到匹配 '{key_or_index}' 的规则。")

        cur_en = _normalize_enable(target_rule.get("Enable"))
        new_en = (not cur_en) if enable is None else bool(enable)
        target_rule["Enable"] = 1 if new_en else 0

        backup_file = save_plist(plist_path, data, backup=True)
        flush_cfprefsd()

        reloaded = False
        if reload_bab:
            reloaded = restart_bab()

        return {
            "status": "success",
            "app": app_name,
            "category": cat_key,
            "previous_enable": cur_en,
            "new_enable": new_en,
            "backup_file": backup_file,
            "reloaded": reloaded,
        }


def remove_rule(
    plist_path: str = LIVE_PREFS_PATH,
    app_name: str = "All Applications",
    category: str = "keyboard",
    key_or_index: Union[str, int] = "",
    index: Optional[int] = None,
    reload_bab: bool = False
) -> Dict[str, Any]:
    """
    Remove an existing rule from an application.
    Supports targeting by explicit index, integer key_or_index, or shortcut/gesture string.
    Single-digit shortcuts ('0'-'9') match by keycode before falling back to index.
    """
    cat_key = RULE_CATEGORIES.get(category.lower(), category)

    with PlistLock(plist_path):
        data = load_plist(plist_path)
        canonical_app, is_known = resolve_app_name(data, app_name)
        if is_known:
            app_name = canonical_app

        app_item = None
        for item in data.get(cat_key, []):
            if isinstance(item, dict) and item.get("AppName") == app_name:
                app_item = item
                break

        if not app_item:
            raise ValueError(f"应用 '{app_name}' 在类别 '{cat_key}' 中未配置任何规则。")

        rules = app_item.get("All Rules", [])
        target_idx = None

        # 1. Explicit index or integer parameter
        if index is not None or (isinstance(key_or_index, int) and not isinstance(key_or_index, bool)):
            idx = index if index is not None else int(key_or_index)
            if 0 <= idx < len(rules):
                target_idx = idx
            else:
                raise IndexError(f"规则索引 {idx} 超出范围 (共 {len(rules)} 条规则)。")
        else:
            # 2. Match by shortcut/gesture string first (preserves single-digit shortcuts like '0'-'9')
            kc, mf = parse_shortcut(str(key_or_index))
            for i, r in enumerate(rules):
                if not isinstance(r, dict):
                    continue
                if cat_key == "ruleOfKeyboard" and kc is not None:
                    if shortcut_matches(r.get("Gesture"), kc, mf, exact_flags=True):
                        target_idx = i
                        break
                elif str(r.get("Gesture")).lower() == str(key_or_index).lower():
                    target_idx = i
                    break

            # 3. Fallback: if no shortcut matched and input is pure digits, treat as index
            if target_idx is None and isinstance(key_or_index, str) and key_or_index.isdigit():
                idx = int(key_or_index)
                if 0 <= idx < len(rules):
                    target_idx = idx

        if target_idx is None:
            raise ValueError(f"在应用 '{app_name}' 中未找到匹配 '{key_or_index}' 的规则。")

        removed_rule = rules.pop(target_idx)
        backup_file = save_plist(plist_path, data, backup=True)
        flush_cfprefsd()

        reloaded = False
        if reload_bab:
            reloaded = restart_bab()

        return {
            "status": "success",
            "operation": "removed",
            "app": app_name,
            "category": cat_key,
            "removed_rule": removed_rule,
            "backup_file": backup_file,
            "reloaded": reloaded,
        }


def add_or_update_applescript(
    plist_path: str = LIVE_PREFS_PATH,
    name: str = "",
    code: str = "",
    note: str = "",
    script_id: Optional[str] = None,
    reload_bab: bool = False
) -> Dict[str, Any]:
    """Add or update an AppleScript entry in ruleOfAppleScript."""
    if not name.strip():
        raise ValueError("AppleScript 名称不能为空。")
    if not code.strip():
        raise ValueError("AppleScript 代码内容不能为空。")

    with PlistLock(plist_path):
        data = load_plist(plist_path)
        scripts = data.setdefault("ruleOfAppleScript", [])

        existing = None
        for s in scripts:
            if not isinstance(s, dict):
                continue
            if script_id and s.get("Id") == script_id:
                existing = s
                break
            elif not script_id and s.get("Name", "").lower() == name.lower():
                existing = s
                break

        if existing:
            existing["Name"] = name
            existing["AppleScript"] = code
            existing["Note"] = note
            existing["Edited"] = True
            op_type = "updated"
            res_id = existing.get("Id", "")
        else:
            new_id = script_id or str(uuid.uuid4()).upper()
            new_item = {
                "Name": name,
                "AppleScript": code,
                "Note": note,
                "Edited": False,
                "Id": new_id,
            }
            scripts.append(new_item)
            op_type = "added"
            res_id = new_id

        backup_file = save_plist(plist_path, data, backup=True)
        flush_cfprefsd()

        reloaded = False
        if reload_bab:
            reloaded = restart_bab()

        return {
            "status": "success",
            "operation": op_type,
            "id": res_id,
            "name": name,
            "backup_file": backup_file,
            "reloaded": reloaded,
        }


def remove_applescript(
    plist_path: str = LIVE_PREFS_PATH,
    name_or_id: str = "",
    reload_bab: bool = False
) -> Dict[str, Any]:
    """Remove an AppleScript entry from ruleOfAppleScript."""
    if not name_or_id.strip():
        raise ValueError("AppleScript 名称或 ID 不能为空。")

    with PlistLock(plist_path):
        data = load_plist(plist_path)
        scripts = data.get("ruleOfAppleScript", [])
        target_idx = None
        q = name_or_id.strip().lower()

        for idx, s in enumerate(scripts):
            if not isinstance(s, dict):
                continue
            if s.get("Id", "").lower() == q or s.get("Name", "").lower() == q:
                target_idx = idx
                break

        if target_idx is None:
            raise ValueError(f"未找到名称或 ID 为 '{name_or_id}' 的 AppleScript。")

        removed_script = scripts.pop(target_idx)
        backup_file = save_plist(plist_path, data, backup=True)
        flush_cfprefsd()

        reloaded = False
        if reload_bab:
            reloaded = restart_bab()

        return {
            "status": "success",
            "operation": "removed",
            "id": removed_script.get("Id"),
            "name": removed_script.get("Name"),
            "backup_file": backup_file,
            "reloaded": reloaded,
        }

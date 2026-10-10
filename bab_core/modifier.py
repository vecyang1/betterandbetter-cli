"""
BetterAndBetter Configurator and Mutation Engine.
Safely adds, updates, enables/disables, and removes rules and AppleScripts with
read-after-write verification, pre-mutation backups, and hot-reload.
"""

import base64
import copy
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively convert bytes and non-serializable objects into JSON-compatible primitives."""
    if isinstance(obj, bytes):
        return {"__bytes_base64__": base64.b64encode(obj).decode("ascii")}
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(_sanitize_for_json(v) for v in obj)
    return obj


def _restore_from_json(obj: Any) -> Any:
    """Recursively restore base64-encoded bytes back into native bytes for plist compatibility."""
    if isinstance(obj, dict):
        if "__bytes_base64__" in obj and len(obj) == 1:
            try:
                return base64.b64decode(obj["__bytes_base64__"])
            except Exception:
                return obj
        return {k: _restore_from_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_restore_from_json(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(_restore_from_json(v) for v in obj)
    return obj

from .constants import (
    ACTION_TYPE_APPLESCRIPT,
    ACTION_TYPE_OPEN,
    ACTION_TYPE_PRESET,
    ACTION_TYPE_SHORTCUT,
    LIVE_PREFS_PATH,
    MUTABLE_CATEGORIES,
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


def add_or_update_rule(
    plist_path: str = LIVE_PREFS_PATH,
    app_name: str = "All Applications",
    category: str = "keyboard",
    key_or_gesture: str = "",
    action_type: str = "Preset",
    action_value: str = "",
    open_targets: Optional[Union[str, List[str]]] = None,
    enable: bool = True,
    note: str = "",
    reload_bab: bool = False
) -> Dict[str, Any]:
    """
    Add or update a gesture or shortcut rule for any category (keyboard, trackpad,
    magicmouse, normalmouse, hotcorners).
    Creates automatic pre-mutation backup, enforces atomic file writes,
    and verifies integrity with read-after-write.
    """
    cat_key = RULE_CATEGORIES.get(category.lower(), category)
    valid_cat_keys = [RULE_CATEGORIES[c] for c in MUTABLE_CATEGORIES]
    if cat_key not in valid_cat_keys:
        cats_str = ", ".join(MUTABLE_CATEGORIES)
        raise ValueError(f"不支持在分类 '{category}' 中添加规则。有效分类: {cats_str}")

    # Parse and validate gesture
    kc = None
    mf = None
    if cat_key == "ruleOfKeyboard":
        kc, mf = parse_shortcut(key_or_gesture)
        if kc is None:
            raise ValueError(f"无法解析快捷键: '{key_or_gesture}'。请使用标准格式如 '⌘B', 'cmd+b', '⇧⌘N' 等。")
        gesture_payload: Any = {
            "keyCode": kc,
            "modifierFlags": mf,
            "modifierFlagsName": format_modifier_name(mf),
        }
        display_trigger = format_shortcut(kc, mf)
    else:
        g_str = str(key_or_gesture).strip()
        if not g_str:
            raise ValueError(f"分类 '{category}' 的手势名称不能为空 (例如: '4Finger_Swipe_Right', 'LeftMouse Click at TopLeft Corner')。")
        gesture_payload = g_str
        display_trigger = g_str

    with PlistLock(plist_path):
        data = load_plist(plist_path)
        canonical_app, is_known = resolve_app_name(data, app_name)
        if is_known:
            app_name = canonical_app

        cat_list = data.setdefault(cat_key, [])

        # Find or create app container
        app_item = None
        for item in cat_list:
            if isinstance(item, dict) and item.get("AppName") == app_name:
                app_item = item
                break

        if app_item is None:
            app_item = {"AppName": app_name, "All Rules": []}
            cat_list.append(app_item)

        rules = app_item.setdefault("All Rules", [])

        # Construct Action dictionary
        action_dict: Dict[str, Any] = {}
        is_open_action = (
            open_targets is not None
            or str(action_type).lower() in ("open", "open...", "open application", "open url", "open file")
        )

        if is_open_action:
            if open_targets:
                targets = [open_targets] if isinstance(open_targets, str) else list(open_targets)
            elif action_value:
                targets = [action_value]
            else:
                raise ValueError("Open 动作必须提供打开的目标路径或 URL (例如: 'https://...', '/Applications/...')。")
            action_dict = {
                "ActionType": "Preset",
                "Action": "Open...",
                "OpenArr": targets,
            }
            res_action_type = "Open..."
            res_action_display = ", ".join(targets)
        elif action_type == "Preset":
            if not action_value:
                raise ValueError("Preset 动作不能为空 (例如: 'Half_of_Top', 'Center', 'LockScreen')。")
            action_dict = {
                "ActionType": "Preset",
                "Action": action_value,
            }
            res_action_type = "Preset"
            res_action_display = action_value
        elif action_type == "Shortcut Keys":
            a_kc, a_mf = parse_shortcut(action_value)
            if a_kc is None:
                action_dict = {
                    "ActionType": "Shortcut Keys",
                    "Action": action_value,
                }
                res_action_display = action_value
            else:
                s_name = format_shortcut(a_kc, a_mf)
                action_dict = {
                    "ActionType": "Shortcut Keys",
                    "Action": {
                        "keyCode": a_kc,
                        "modifierFlags": a_mf,
                        "ShortcutName": s_name,
                    },
                }
                res_action_display = s_name
            res_action_type = "Shortcut Keys"
        elif action_type == "AppleScript":
            matched_id = None
            for s in data.get("ruleOfAppleScript", []):
                if isinstance(s, dict):
                    if s.get("Id") == action_value or s.get("Name", "").lower() == action_value.lower():
                        matched_id = s.get("Id")
                        break
            script_id = matched_id if matched_id else action_value
            action_dict = {
                "ActionType": "AppleScript",
                "Action": script_id,
            }
            res_action_type = "AppleScript"
            res_action_display = action_value
        else:
            action_dict = {
                "ActionType": action_type,
                "Action": action_value,
            }
            res_action_type = action_type
            res_action_display = action_value

        # Search existing rule
        existing_rule = None
        for r in rules:
            if not isinstance(r, dict):
                continue
            if cat_key == "ruleOfKeyboard" and kc is not None:
                if shortcut_matches(r.get("Gesture"), kc, mf, exact_flags=True):
                    existing_rule = r
                    break
            else:
                rg = str(r.get("Gesture", "")).strip().lower()
                if rg == display_trigger.lower():
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
                "Gesture": gesture_payload,
                "Action": action_dict,
                "Enable": 1 if enable else 0,
                "Note": note,
                "Modifier": " -",
            }
            rules.append(new_rule)
            op_type = "added"

        # Save atomically with backup
        backup_file = save_plist(plist_path, data, backup=True)
        flush_cfprefsd(plist_path)

        reloaded = False
        if reload_bab:
            reloaded = restart_bab()

        return {
            "status": "success",
            "operation": op_type,
            "app": app_name,
            "category": cat_key,
            "trigger": display_trigger,
            "shortcut": display_trigger if cat_key == "ruleOfKeyboard" else "",
            "action_type": res_action_type,
            "action": res_action_display,
            "enable": enable,
            "backup_file": backup_file,
            "reloaded": reloaded,
        }


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
    Backward-compatible helper for adding/updating keyboard rules.
    Delegates to add_or_update_rule.
    """
    return add_or_update_rule(
        plist_path=plist_path,
        app_name=app_name,
        category="keyboard",
        key_or_gesture=key_str,
        action_type=action_type,
        action_value=action_value,
        enable=enable,
        note=note,
        reload_bab=reload_bab,
    )


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
                elif str(r.get("Gesture", "")).strip().lower() == str(key_or_index).strip().lower():
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
        flush_cfprefsd(plist_path)

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
                elif str(r.get("Gesture", "")).strip().lower() == str(key_or_index).strip().lower():
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
        flush_cfprefsd(plist_path)

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
        flush_cfprefsd(plist_path)

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
        flush_cfprefsd(plist_path)

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


def clone_app_rules(
    plist_path: str = LIVE_PREFS_PATH,
    from_app: str = "com.google.Chrome",
    to_app: Union[str, List[str]] = "com.citrolabs.ego.lite",
    categories: Optional[List[str]] = None,
    overwrite: bool = False,
    only_enabled: bool = False,
    reload_bab: bool = False
) -> Dict[str, Any]:
    """
    Clone or migrate shortcuts and gesture rules from one application to one or more applications
    (e.g., from Google Chrome to AdsPower Browser and BitBrowser).

    Supports:
    - Single target app or comma-separated / list of multiple target apps
    - Selective or all categories (keyboard, trackpad, normalmouse, etc.)
    - Non-destructive merging (preserves existing custom shortcuts by default)
    - Full overwriting if overwrite=True
    - Filtering by active/enabled rules only
    - Atomic locking, pre-mutation backup, and hot-reload.
    """
    if not isinstance(from_app, str) or not from_app.strip():
        raise ValueError("源应用 (from_app) 不能为空。")

    if isinstance(to_app, str):
        target_specs = [t.strip() for t in to_app.split(",") if t.strip()]
    elif isinstance(to_app, (list, tuple, set)):
        target_specs = [str(t).strip() for t in to_app if str(t).strip()]
    else:
        target_specs = []

    if not target_specs:
        raise ValueError("目标应用 (to_app) 不能为空。")

    with PlistLock(plist_path):
        data = load_plist(plist_path)

        # Resolve canonical name for source
        from_canonical, from_is_known = resolve_app_name(data, from_app)
        if not from_is_known:
            raise ValueError(f"源应用 '{from_app}' 未在 BetterAndBetter 配置中找到。")

        # Resolve target categories
        if categories:
            cat_keys = [RULE_CATEGORIES.get(c.lower(), c) for c in categories]
        else:
            cat_keys = [
                RULE_CATEGORIES["keyboard"],
                RULE_CATEGORIES["trackpad"],
                RULE_CATEGORIES["normalmouse"],
                RULE_CATEGORIES["magicmouse"],
                RULE_CATEGORIES["hotcorners"],
            ]

        total_added = 0
        total_updated = 0
        total_skipped = 0
        all_rules_detail: List[Dict[str, Any]] = []
        targets_detail: List[Dict[str, Any]] = []

        for raw_target in target_specs:
            to_canonical, to_is_known = resolve_app_name(data, raw_target)
            if not to_is_known:
                to_canonical = raw_target.strip()

            target_added = 0
            target_updated = 0
            target_skipped = 0
            target_rules_detail: List[Dict[str, Any]] = []

            for cat_key in cat_keys:
                cat_list = data.get(cat_key, [])
                if not isinstance(cat_list, list):
                    continue

                # Locate source app container
                from_container = None
                for item in cat_list:
                    if isinstance(item, dict) and item.get("AppName") == from_canonical:
                        from_container = item
                        break

                if not from_container:
                    continue

                from_rules = from_container.get("All Rules", [])
                if not isinstance(from_rules, list) or not from_rules:
                    continue

                # Locate or create destination app container
                to_container = None
                for item in cat_list:
                    if isinstance(item, dict) and item.get("AppName") == to_canonical:
                        to_container = item
                        break

                if to_container is None:
                    to_container = {"AppName": to_canonical, "All Rules": []}
                    cat_list.append(to_container)

                to_rules = to_container.setdefault("All Rules", [])

                for src_rule in from_rules:
                    if not isinstance(src_rule, dict):
                        continue

                    is_en = _normalize_enable(src_rule.get("Enable"))
                    if only_enabled and not is_en:
                        continue

                    # Match by gesture
                    match_rule = None
                    if cat_key == "ruleOfKeyboard":
                        src_g = src_rule.get("Gesture")
                        kc = src_g.get("keyCode") if isinstance(src_g, dict) else None
                        mf = src_g.get("modifierFlags") if isinstance(src_g, dict) else None
                        if kc is not None:
                            for dst_r in to_rules:
                                if isinstance(dst_r, dict) and shortcut_matches(dst_r.get("Gesture"), kc, mf, exact_flags=True):
                                    match_rule = dst_r
                                    break
                        display_gesture = format_shortcut(kc, mf) if kc is not None else str(src_g)
                    else:
                        src_g = src_rule.get("Gesture")
                        for dst_r in to_rules:
                            if isinstance(dst_r, dict) and str(dst_r.get("Gesture")) == str(src_g):
                                match_rule = dst_r
                                break
                        display_gesture = str(src_g)

                    if match_rule is not None:
                        if overwrite:
                            match_rule.clear()
                            match_rule.update(copy.deepcopy(src_rule))
                            target_updated += 1
                            item_record = {
                                "target_app": to_canonical,
                                "category": cat_key,
                                "gesture": display_gesture,
                                "status": "updated",
                                "action": src_rule.get("Action"),
                                "enable": is_en,
                            }
                            target_rules_detail.append(item_record)
                            all_rules_detail.append(item_record)
                        else:
                            target_skipped += 1
                            item_record = {
                                "target_app": to_canonical,
                                "category": cat_key,
                                "gesture": display_gesture,
                                "status": "skipped (already exists)",
                                "action": match_rule.get("Action"),
                                "enable": _normalize_enable(match_rule.get("Enable")),
                            }
                            target_rules_detail.append(item_record)
                            all_rules_detail.append(item_record)
                    else:
                        to_rules.append(copy.deepcopy(src_rule))
                        target_added += 1
                        item_record = {
                            "target_app": to_canonical,
                            "category": cat_key,
                            "gesture": display_gesture,
                            "status": "added",
                            "action": src_rule.get("Action"),
                            "enable": is_en,
                        }
                        target_rules_detail.append(item_record)
                        all_rules_detail.append(item_record)

            targets_detail.append({
                "to_app": to_canonical,
                "added_count": target_added,
                "updated_count": target_updated,
                "skipped_count": target_skipped,
                "rules": target_rules_detail,
            })
            total_added += target_added
            total_updated += target_updated
            total_skipped += target_skipped

        backup_file = save_plist(plist_path, data, backup=True)
        flush_cfprefsd(plist_path)

        reloaded = False
        if reload_bab:
            reloaded = restart_bab()

        to_app_display = targets_detail[0]["to_app"] if len(targets_detail) == 1 else ", ".join(t["to_app"] for t in targets_detail)

        return {
            "status": "success",
            "from_app": from_canonical,
            "to_app": to_app_display,
            "added_count": total_added,
            "updated_count": total_updated,
            "skipped_count": total_skipped,
            "rules": all_rules_detail,
            "targets": targets_detail,
            "backup_file": backup_file,
            "reloaded": reloaded,
        }


def export_app_rules(
    plist_path: str = LIVE_PREFS_PATH,
    app_name: str = "All Applications",
    categories: Optional[List[str]] = None,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Export all configured rules and referenced AppleScripts for an application
    to a portable, versioned JSON dictionary or file.
    """
    with PlistLock(plist_path):
        data = load_plist(plist_path)
        canonical_app, is_known = resolve_app_name(data, app_name)
        if not is_known:
            raise ValueError(f"应用 '{app_name}' 未在 BetterAndBetter 配置中找到。")
        app_name = canonical_app

        target_cats = (
            [RULE_CATEGORIES.get(c.lower(), c) for c in categories]
            if categories
            else [
                RULE_CATEGORIES["keyboard"],
                RULE_CATEGORIES["trackpad"],
                RULE_CATEGORIES["normalmouse"],
                RULE_CATEGORIES["magicmouse"],
                RULE_CATEGORIES["hotcorners"],
            ]
        )

        exported_rules: Dict[str, List[Dict[str, Any]]] = {}
        referenced_script_ids = set()

        for cat_key in target_cats:
            for item in data.get(cat_key, []):
                if isinstance(item, dict) and item.get("AppName") == app_name:
                    rules = item.get("All Rules", [])
                    exported_rules[cat_key] = _sanitize_for_json(copy.deepcopy(rules))
                    for r in rules:
                        if isinstance(r, dict):
                            act = r.get("Action")
                            if isinstance(act, dict) and act.get("ActionType") == "AppleScript":
                                s_id = act.get("Action")
                                if s_id:
                                    referenced_script_ids.add(str(s_id))
                    break

        # Collect referenced AppleScripts
        referenced_scripts = []
        for s in data.get("ruleOfAppleScript", []):
            if isinstance(s, dict) and str(s.get("Id")) in referenced_script_ids:
                referenced_scripts.append(_sanitize_for_json(copy.deepcopy(s)))

        total_rules = sum(len(v) for v in exported_rules.values())
        payload = {
            "schema_version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "app": app_name,
            "total_rules": total_rules,
            "rules": exported_rules,
            "referenced_scripts": referenced_scripts,
        }

        if output_path:
            out_dir = os.path.dirname(os.path.abspath(output_path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

        return payload


def import_app_rules(
    plist_path: str = LIVE_PREFS_PATH,
    app_name: str = "All Applications",
    input_file_or_data: Union[str, Dict[str, Any]] = "",
    categories: Optional[List[str]] = None,
    overwrite: bool = False,
    reload_bab: bool = False
) -> Dict[str, Any]:
    """
    Import rules and referenced AppleScripts from a JSON file or dictionary into a target application.
    Supports selective category filtering, non-destructive merging or overwriting,
    atomic locking, pre-mutation backup, and hot-reload.
    """
    if isinstance(input_file_or_data, str):
        if not os.path.exists(input_file_or_data):
            raise FileNotFoundError(f"导入配置文件未找到: {input_file_or_data}")
        with open(input_file_or_data, "r", encoding="utf-8") as f:
            payload = json.load(f)
    elif isinstance(input_file_or_data, dict):
        payload = input_file_or_data
    else:
        raise ValueError("输入数据必须为文件路径或字典。")

    if not isinstance(payload, dict) or "rules" not in payload:
        raise ValueError("导入配置格式不合法: 必须包含 'rules' 字典字段。")

    payload = _restore_from_json(payload)

    with PlistLock(plist_path):
        data = load_plist(plist_path)
        canonical_app, is_known = resolve_app_name(data, app_name)
        if is_known:
            app_name = canonical_app

        # 1. Import referenced AppleScripts if missing
        scripts_added = 0
        existing_scripts = data.setdefault("ruleOfAppleScript", [])
        existing_ids = {s.get("Id") for s in existing_scripts if isinstance(s, dict) and s.get("Id")}
        for sc in payload.get("referenced_scripts", []):
            if isinstance(sc, dict) and sc.get("Id") not in existing_ids:
                existing_scripts.append(copy.deepcopy(sc))
                existing_ids.add(sc.get("Id"))
                scripts_added += 1

        # 2. Ingest rules into categories
        import_rules_dict = payload["rules"]
        target_cats = (
            [RULE_CATEGORIES.get(c.lower(), c) for c in categories]
            if categories
            else list(import_rules_dict.keys())
        )

        total_added = 0
        total_updated = 0
        total_skipped = 0

        for cat_key in target_cats:
            if cat_key not in import_rules_dict:
                continue
            src_rules = import_rules_dict[cat_key]
            if not isinstance(src_rules, list):
                continue

            cat_list = data.setdefault(cat_key, [])
            app_item = None
            for item in cat_list:
                if isinstance(item, dict) and item.get("AppName") == app_name:
                    app_item = item
                    break
            if app_item is None:
                app_item = {"AppName": app_name, "All Rules": []}
                cat_list.append(app_item)

            dst_rules = app_item.setdefault("All Rules", [])
            for src_r in src_rules:
                if not isinstance(src_r, dict):
                    continue

                # Match existing rule
                match_r = None
                if cat_key == "ruleOfKeyboard":
                    src_g = src_r.get("Gesture")
                    kc = src_g.get("keyCode") if isinstance(src_g, dict) else None
                    mf = src_g.get("modifierFlags") if isinstance(src_g, dict) else None
                    if kc is not None:
                        for dr in dst_rules:
                            if isinstance(dr, dict) and shortcut_matches(dr.get("Gesture"), kc, mf, exact_flags=True):
                                match_r = dr
                                break
                else:
                    src_g_str = str(src_r.get("Gesture", "")).strip().lower()
                    for dr in dst_rules:
                        if isinstance(dr, dict) and str(dr.get("Gesture", "")).strip().lower() == src_g_str:
                            match_r = dr
                            break

                if match_r is not None:
                    if overwrite:
                        match_r.clear()
                        match_r.update(copy.deepcopy(src_r))
                        total_updated += 1
                    else:
                        total_skipped += 1
                else:
                    dst_rules.append(copy.deepcopy(src_r))
                    total_added += 1

        backup_file = save_plist(plist_path, data, backup=True)
        flush_cfprefsd(plist_path)

        reloaded = False
        if reload_bab:
            reloaded = restart_bab()

        return {
            "status": "success",
            "app": app_name,
            "added_count": total_added,
            "updated_count": total_updated,
            "skipped_count": total_skipped,
            "scripts_imported": scripts_added,
            "backup_file": backup_file,
            "reloaded": reloaded,
        }



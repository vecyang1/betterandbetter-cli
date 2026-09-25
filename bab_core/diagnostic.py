"""
BetterAndBetter Diagnostic-First Engine.
Explains rules, evaluates active precedence & shadowing, and detects state drift against Git backup.
"""

from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    KNOWN_APP_ALIASES,
    RULE_CATEGORIES,
    RULE_CATEGORY_TITLES,
)
from .inspector import (
    format_action_display,
    get_scripts_map,
    inspect_rules,
    inspect_scripts,
    resolve_app_name,
)
from .keycodes import (
    flags_match,
    format_shortcut,
    normalize_flags,
    parse_shortcut,
    shortcut_matches,
)
from .models import DiagnosticResult
from .plist_manager import _normalize_enable, _rule_signature


def _detect_query_intent(query: str, data: Dict[str, Any]) -> str:
    """Classify the user query into SHORTCUT, APP, GESTURE, or ACTION_KEYWORD."""
    q = query.strip()

    # 1. Check if it starts with shortcut symbols or modifiers
    kc, flags = parse_shortcut(q)
    if kc is not None or (flags > 0 and len(q) <= 6):
        return "SHORTCUT"

    # 2. Check if known app alias or exact configured app name
    app_name, is_configured = resolve_app_name(data, q)
    if is_configured:
        return "APP"

    # 3. Check gesture keywords
    gesture_keywords = [
        "tap", "swipe", "click", "finger", "corner", "scroll", "tiptap",
        "doubletap", "forceclick", "pinch", "customize"
    ]
    if any(k in q.lower() for k in gesture_keywords):
        return "GESTURE"

    # 4. Fallback check: could it be an app not yet configured?
    if "." in q or q.lower().endswith("app") or "lite" in q.lower():
        return "APP"

    return "ACTION_KEYWORD"


def _compare_rule_with_git(
    rule_dict: Dict[str, Any],
    cat_key: str,
    app_name: str,
    git_data: Optional[Dict[str, Any]],
    rule_index: Optional[int] = None,
) -> Tuple[str, str]:
    """
    Compare a single live rule against git data.
    Uses positional matching, exact identity matching, and gesture matching to avoid collisions.
    Returns (drift_status, drift_description).
    """
    if not git_data:
        return "NO_GIT_DATA", "未加载 Git 备份数据"

    git_apps = {item.get("AppName"): item for item in git_data.get(cat_key, []) if isinstance(item, dict)}
    if app_name not in git_apps:
        return "ONLY_IN_LIVE", "此应用在 Git 备份中不存在 (仅在 Live 本地)"

    git_rules = [r for r in git_apps[app_name].get("All Rules", []) if isinstance(r, dict)]
    live_en = _normalize_enable(rule_dict.get("Enable"))
    live_act = rule_dict.get("Action")
    live_g = rule_dict.get("Gesture")
    status_str = "已启用" if live_en else "已禁用"

    # 1. Check exact positional match at rule_index
    if rule_index is not None and 0 <= rule_index < len(git_rules):
        rg = git_rules[rule_index]
        if rg.get("Gesture") == live_g and rg.get("Action") == live_act:
            git_en = _normalize_enable(rg.get("Enable"))
            if live_en == git_en:
                return "SYNCHRONIZED", "已对账同步 (Live 与 Git 一致)"
            git_status_str = "已启用" if git_en else "已禁用"
            return "MODIFIED_ENABLE", f"状态漂移: Live 为【{status_str}】，Git 备份为【{git_status_str}】"

    # 2. Search for exact Gesture & Action match across all git rules
    for rg in git_rules:
        if rg.get("Gesture") == live_g and rg.get("Action") == live_act:
            git_en = _normalize_enable(rg.get("Enable"))
            if live_en == git_en:
                return "SYNCHRONIZED", "已对账同步 (Live 与 Git 一致)"
            git_status_str = "已启用" if git_en else "已禁用"
            return "MODIFIED_ENABLE", f"状态漂移: Live 为【{status_str}】，Git 备份为【{git_status_str}】"

    # 3. Non-empty gesture match with modified action
    if live_g and live_g not in ({}, "Customize", ""):
        for rg in git_rules:
            if rg.get("Gesture") == live_g:
                return "MODIFIED_ACTION", "动作漂移: Live 与 Git 备份配置的动作不同"

    # 4. Gestureless slot match with same action
    if live_g in ({}, None, ""):
        for rg in git_rules:
            if rg.get("Gesture") in ({}, None, "") and rg.get("Action") == live_act:
                git_en = _normalize_enable(rg.get("Enable"))
                if live_en == git_en:
                    return "SYNCHRONIZED", "已对账同步 (Live 与 Git 一致)"
                git_status_str = "已启用" if git_en else "已禁用"
                return "MODIFIED_ENABLE", f"状态漂移: Live 为【{status_str}】，Git 备份为【{git_status_str}】"

    return "ONLY_IN_LIVE", "此规则在 Git 备份中不存在 (未同步备份)"


def explain_query(
    query: str,
    live_data: Dict[str, Any],
    git_data: Optional[Dict[str, Any]] = None
) -> DiagnosticResult:
    """
    Diagnostic-First engine:
    Evaluates rule matches, detects active precedence & shadowing, and verifies drift against Git.
    """
    intent = _detect_query_intent(query, live_data)
    scripts_map = get_scripts_map(live_data)

    matched_rules: List[Dict[str, Any]] = []
    matched_scripts: List[Dict[str, Any]] = []
    shadowing_notes: List[str] = []
    drift_notes: List[str] = []
    recommendations: List[str] = []

    # -------------------------------------------------------------
    # 1. SHORTCUT Query Mode
    # -------------------------------------------------------------
    if intent == "SHORTCUT":
        target_kc, target_flags = parse_shortcut(query)
        formatted_query = format_shortcut(target_kc, target_flags)

        global_matched = None
        app_specific_matches = []

        for item in live_data.get("ruleOfKeyboard", []):
            if not isinstance(item, dict):
                continue
            app_name = item.get("AppName", "")
            rules = item.get("All Rules", [])

            for idx, r in enumerate(rules):
                if not isinstance(r, dict):
                    continue
                g = r.get("Gesture")
                if shortcut_matches(g, target_kc, target_flags, exact_flags=(target_flags > 0)):
                    en = _normalize_enable(r.get("Enable"))
                    act_type, act_display = format_action_display(r.get("Action"), scripts_map)
                    drift_status, drift_desc = _compare_rule_with_git(r, "ruleOfKeyboard", app_name, git_data, rule_index=idx)

                    kc = g.get("keyCode") if isinstance(g, dict) else None
                    mf = g.get("modifierFlags") if isinstance(g, dict) else None
                    if kc is None and not mf:
                        trigger_str = "(未分配快捷键)"
                    else:
                        trigger_str = format_shortcut(kc, mf)

                    match_info = {
                        "app": app_name,
                        "category": "ruleOfKeyboard",
                        "category_title": "键盘快捷键",
                        "index": idx,
                        "trigger": trigger_str,
                        "action_type": act_type,
                        "action": act_display,
                        "enabled": en,
                        "note": str(r.get("Note", "")).strip(),
                        "is_app_specific": (app_name != "All Applications"),
                        "drift_status": drift_status,
                        "drift_desc": drift_desc,
                    }
                    matched_rules.append(match_info)

                    if app_name == "All Applications":
                        global_matched = match_info
                    else:
                        app_specific_matches.append(match_info)

        # Shadowing and precedence analysis
        if app_specific_matches:
            apps_str = ", ".join(f"[{m['app']}]" for m in app_specific_matches)
            if global_matched:
                g_status = "已启用" if global_matched["enabled"] else "已停用"
                shadowing_notes.append(
                    f"优先级遮蔽分析：快捷键 【{formatted_query}】 同时存在全局规则与应用专属规则。\n"
                    f"- 在 {apps_str} 中：应用专属规则【优先接管】并遮蔽全局规则。\n"
                    f"- 在其他未单独配置此键的应用中：回退执行 [All Applications] 全局规则（当前{g_status}，动作：{global_matched['action']}）。"
                )
            else:
                shadowing_notes.append(
                    f"优先级分析：快捷键 【{formatted_query}】 仅在应用 {apps_str} 中定义了专属规则。\n"
                    f"- 在这几个应用前台激活时生效；在其他应用中不触发任何 BetterAndBetter 全局动作。"
                )
        elif global_matched:
            g_status = "已启用" if global_matched["enabled"] else "已停用"
            shadowing_notes.append(
                f"优先级分析：快捷键 【{formatted_query}】 仅在 [All Applications] 全局规则中配置（当前{g_status}）。\n"
                f"- 在所有前台应用中均将生效（除非某个应用在其内部系统快捷键中先行拦截了该按键）。"
            )
        else:
            shadowing_notes.append(
                f"未在 BetterAndBetter 中检测到与快捷键 【{formatted_query}】 匹配的规则。"
            )

    # -------------------------------------------------------------
    # 2. APP Query Mode
    # -------------------------------------------------------------
    elif intent == "APP":
        app_name, is_configured = resolve_app_name(live_data, query)

        if not is_configured:
            # The app has NO custom rules in BAB!
            # Explain clearly that it inherits All Applications.
            all_rules = inspect_rules(live_data, app_filter="All Applications", enabled_only=True)
            kb_count = sum(1 for r in all_rules if r.category == "ruleOfKeyboard")
            tp_count = sum(1 for r in all_rules if r.category == "ruleOfTrackPad")
            hc_count = sum(1 for r in all_rules if r.category == "ruleOfHotCorners")

            shadowing_notes.append(
                f"诊断结论：应用 【{query}】（解析目标: {app_name}）尚未在 BetterAndBetter 中配置独立专属规则。\n"
                f"真实运行时行为：\n"
                f"- 该应用完全继承【All Applications】全局规则。\n"
                f"- 当前全局生效统计：键盘快捷键 {kb_count} 条，触控板手势 {tp_count} 条，屏幕触发角 {hc_count} 条。\n"
                f"- 任何全局已启用的快捷键或手势在该应用前台时均可正常触发。"
            )
            recommendations.append(
                f"若需为 {query} 定制独立规则，可执行命令：\n"
                f"  bab set rule --app \"{app_name}\" --category keyboard --key \"⌘B\" --action-type Preset --action Half_of_Top"
            )
        else:
            # Configured app: gather all rules
            for cat_slug, cat_key in RULE_CATEGORIES.items():
                if cat_key == "ruleOfAppleScript":
                    continue
                for item in live_data.get(cat_key, []):
                    if not isinstance(item, dict) or item.get("AppName") != app_name:
                        continue
                    for idx, r in enumerate(item.get("All Rules", [])):
                        if not isinstance(r, dict):
                            continue
                        en = _normalize_enable(r.get("Enable"))
                        act_type, act_display = format_action_display(r.get("Action"), scripts_map)

                        g_raw = r.get("Gesture")
                        if cat_key == "ruleOfKeyboard" and isinstance(g_raw, dict):
                            kc = g_raw.get("keyCode")
                            mf = g_raw.get("modifierFlags")
                            if kc is None and not mf:
                                trigger_disp = "(未分配快捷键)"
                            else:
                                trigger_disp = format_shortcut(kc, mf)
                        else:
                            trigger_disp = str(g_raw)

                        drift_status, drift_desc = _compare_rule_with_git(r, cat_key, app_name, git_data, rule_index=idx)

                        matched_rules.append({
                            "app": app_name,
                            "category": cat_key,
                            "category_title": RULE_CATEGORY_TITLES.get(cat_key, cat_key),
                            "index": idx,
                            "trigger": trigger_disp,
                            "action_type": act_type,
                            "action": act_display,
                            "enabled": en,
                            "note": str(r.get("Note", "")).strip(),
                            "is_app_specific": (app_name != "All Applications"),
                            "drift_status": drift_status,
                            "drift_desc": drift_desc,
                        })

            enabled_count = sum(1 for r in matched_rules if r["enabled"])
            disabled_count = len(matched_rules) - enabled_count
            shadowing_notes.append(
                f"诊断结论：应用 【{app_name}】 共配置了 {len(matched_rules)} 条规则（已启用: {enabled_count}，已禁用: {disabled_count}）。\n"
                f"- 在该应用激活时，这些专属规则优先级高于全局规则。\n"
                f"- 未被上述规则覆盖的其余手势与快捷键，继续继承 [All Applications] 全局规则。"
            )

        # Also search AppleScripts relevant to this app
        q_lower = query.lower()
        for s in live_data.get("ruleOfAppleScript", []):
            if not isinstance(s, dict):
                continue
            name = s.get("Name", "")
            code = s.get("AppleScript", "")
            note = s.get("Note", "")
            sid = s.get("Id", "")
            if q_lower in name.lower() or q_lower in code.lower() or q_lower in note.lower() or q_lower in sid.lower():
                matched_scripts.append({
                    "id": sid,
                    "name": name,
                    "note": note,
                    "code_snippet": code[:100].replace("\n", " "),
                })

    # -------------------------------------------------------------
    # 3. GESTURE or ACTION_KEYWORD Query Mode
    # -------------------------------------------------------------
    else:
        q_lower = query.lower()

        # Search across all rules
        for cat_slug, cat_key in RULE_CATEGORIES.items():
            if cat_key == "ruleOfAppleScript":
                continue

            for item in live_data.get(cat_key, []):
                if not isinstance(item, dict):
                    continue
                app_name = item.get("AppName", "")

                for idx, r in enumerate(item.get("All Rules", [])):
                    if not isinstance(r, dict):
                        continue

                    g_raw = r.get("Gesture")
                    trigger_str = str(g_raw)
                    if cat_key == "ruleOfKeyboard" and isinstance(g_raw, dict):
                        kc = g_raw.get("keyCode")
                        mf = g_raw.get("modifierFlags")
                        if kc is None and not mf:
                            trigger_str = "(未分配快捷键)"
                        else:
                            trigger_str = format_shortcut(kc, mf)

                    act_type, act_display = format_action_display(r.get("Action"), scripts_map)
                    note_str = str(r.get("Note", ""))

                    # Match condition
                    match = (
                        q_lower in trigger_str.lower()
                        or q_lower in act_display.lower()
                        or q_lower in act_type.lower()
                        or q_lower in note_str.lower()
                    )

                    if match:
                        en = _normalize_enable(r.get("Enable"))
                        drift_status, drift_desc = _compare_rule_with_git(r, cat_key, app_name, git_data, rule_index=idx)

                        matched_rules.append({
                            "app": app_name,
                            "category": cat_key,
                            "category_title": RULE_CATEGORY_TITLES.get(cat_key, cat_key),
                            "index": idx,
                            "trigger": trigger_str,
                            "action_type": act_type,
                            "action": act_display,
                            "enabled": en,
                            "note": note_str.strip(),
                            "is_app_specific": (app_name != "All Applications"),
                            "drift_status": drift_status,
                            "drift_desc": drift_desc,
                        })

        # Also search AppleScripts
        for s in live_data.get("ruleOfAppleScript", []):
            if not isinstance(s, dict):
                continue
            name = s.get("Name", "")
            code = s.get("AppleScript", "")
            note = s.get("Note", "")
            sid = s.get("Id", "")

            if q_lower in name.lower() or q_lower in code.lower() or q_lower in note.lower() or q_lower in sid.lower():
                matched_scripts.append({
                    "id": sid,
                    "name": name,
                    "note": note,
                    "code_snippet": code[:100].replace("\n", " "),
                })

        if not matched_rules and not matched_scripts:
            all_rules = inspect_rules(live_data, app_filter="All Applications", enabled_only=True)
            kb_count = sum(1 for r in all_rules if r.category == "ruleOfKeyboard")
            tp_count = sum(1 for r in all_rules if r.category == "ruleOfTrackPad")
            shadowing_notes.append(
                f"关键字诊断：搜索词 【{query}】 未匹配到任何专属规则或 AppleScript。\n"
                f"运行时行为提示：若 【{query}】 为某个 macOS 应用程序，由于未配置专属规则，它将完全继承 [All Applications]（全局规则）生效的所有规则（当前生效键盘快捷键 {kb_count} 条，触控板手势 {tp_count} 条）。"
            )
            recommendations.append(
                f"若需为 【{query}】 定制专属规则，可使用命令：\n"
                f"  bab set rule --app \"{query}\" --category keyboard --key \"⌘B\" --action-type Preset --action Half_of_Top"
            )
        else:
            shadowing_notes.append(
                f"关键字诊断：搜索词 【{query}】 共匹配到 {len(matched_rules)} 条规则和 {len(matched_scripts)} 个 AppleScript 脚本。"
            )

    # -------------------------------------------------------------
    # Drift Summary across all matched rules
    # -------------------------------------------------------------
    unsynced_items = [r for r in matched_rules if r.get("drift_status") not in ("SYNCHRONIZED", "NO_GIT_DATA")]
    if unsynced_items:
        drift_notes.append(
            f"⚠️ 检测到 {len(unsynced_items)} 条匹配规则与 Git 备份存在状态漂移！"
        )
        recommendations.append("运行 `bab sync --to-git` 或 `bab backup` 及时将 Live 状态固化至 Git 仓库。")
    elif git_data:
        drift_notes.append("✅ 所有匹配规则均与 Git 备份保持严格一致，无状态漂移。")

    return DiagnosticResult(
        query=query,
        query_intent=intent,
        matched_rules=matched_rules,
        matched_scripts=matched_scripts,
        shadowing_explanation="\n".join(shadowing_notes),
        drift_explanation="\n".join(drift_notes),
        actionable_recommendations=recommendations,
    )

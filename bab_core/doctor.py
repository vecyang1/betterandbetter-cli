"""
BetterAndBetter Doctor & Health Auditor.
Audits preference files, locks, permissions, processes, LaunchAgent daemon,
and structural rule-to-AppleScript graph integrity.
Exposes ghost logic, orphaned script IDs, and gesture drift.
"""

import json
import os
import plistlib
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    APP_BUNDLE_PATH,
    APP_PROCESS_NAME,
    BACKUP_DIR,
    HELPER_PROCESS_NAME,
    LAUNCHD_LABEL,
    LAUNCHD_PLIST_PATH,
    LEGACY_LAUNCHD_LABEL,
    LEGACY_LAUNCHD_PLIST_PATH,
    LIVE_PREFS_PATH,
    REPO_PREFS_PATH,
    RULE_CATEGORIES,
    RULE_CATEGORY_TITLES,
)
from .daemon import get_daemon_status
from .inspector import _get_process_info
from .keycodes import format_shortcut
from .plist_manager import PlistLock, diff_plists, flush_cfprefsd, load_plist, save_plist, _normalize_enable


@dataclass
class DoctorFinding:
    """An individual finding from the doctor health audit."""
    severity: str  # "CRITICAL", "WARNING", "INFO"
    category: str  # "PLIST", "PERMISSION", "BACKUP", "PROCESS", "DAEMON", "SYNC", "SCRIPTS", "GESTURES"
    message: str
    details: Optional[Dict[str, Any]] = None
    resolution: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "details": self.details or {},
            "resolution": self.resolution,
        }


@dataclass
class DoctorReport:
    """Aggregated doctor health audit report."""
    verdict: str  # "HEALTHY", "WARNING", "CRITICAL"
    checks_run: int
    findings: List[DoctorFinding] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "checks_run": self.checks_run,
            "checked_at": self.checked_at,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
        }


def check_plist_integrity(path: str = LIVE_PREFS_PATH) -> Tuple[bool, Optional[Dict[str, Any]], List[DoctorFinding]]:
    """Verify that the preference file exists, is valid binary/XML plist, and root is dict."""
    findings: List[DoctorFinding] = []
    if not os.path.exists(path):
        findings.append(DoctorFinding(
            severity="CRITICAL",
            category="PLIST",
            message=f"Live 偏好文件缺失: {path}",
            resolution="请启动一次 /Applications/BetterAndBetter.app 或执行 `bab sync --to-live --reload` 从 Git 备份恢复。"
        ))
        return False, None, findings

    size = os.path.getsize(path)
    if size == 0:
        findings.append(DoctorFinding(
            severity="CRITICAL",
            category="PLIST",
            message=f"Live 偏好文件损坏 (文件大小为 0 字节): {path}",
            resolution="执行 `bab sync --to-live --reload` 从 Git 备份恢复。"
        ))
        return False, None, findings

    try:
        data = load_plist(path)
        if not isinstance(data, dict):
            findings.append(DoctorFinding(
                severity="CRITICAL",
                category="PLIST",
                message="Live 偏好文件根节点不是有效字典。",
                resolution="执行 `bab sync --to-live --reload` 恢复标准字典结构。"
            ))
            return False, None, findings
        return True, data, findings
    except Exception as e:
        findings.append(DoctorFinding(
            severity="CRITICAL",
            category="PLIST",
            message=f"解析 Live 偏好文件失败: {e}",
            resolution="执行 `bab sync --to-live --reload` 恢复配置文件。"
        ))
        return False, None, findings


def check_permissions(path: str = LIVE_PREFS_PATH) -> List[DoctorFinding]:
    """Verify write permissions for plist and concurrency lock directory."""
    findings: List[DoctorFinding] = []
    if os.path.exists(path) and not os.access(path, os.W_OK):
        findings.append(DoctorFinding(
            severity="CRITICAL",
            category="PERMISSION",
            message=f"Live 偏好文件缺少写权限: {path}",
            resolution=f"运行 `chmod u+w \"{path}\"` 授予写权限。"
        ))

    # Test lock creation
    test_lock = os.path.join(tempfile.gettempdir(), f"bab_test_perm_{os.getpid()}.lock")
    try:
        with open(test_lock, "w") as f:
            f.write("test")
        os.remove(test_lock)
    except Exception as e:
        findings.append(DoctorFinding(
            severity="CRITICAL",
            category="PERMISSION",
            message=f"无法在系统临时目录 ({tempfile.gettempdir()}) 创建排他锁: {e}",
            resolution="检查 /tmp 目录读写权限。"
        ))

    # Test backup dir
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        test_bak = os.path.join(BACKUP_DIR, f".perm_test_{os.getpid()}")
        with open(test_bak, "w") as f:
            f.write("test")
        os.remove(test_bak)
    except Exception as e:
        findings.append(DoctorFinding(
            severity="WARNING",
            category="BACKUP",
            message=f"无法写入安全备份目录 ({BACKUP_DIR}): {e}",
            resolution=f"运行 `chmod -R u+rwx \"{BACKUP_DIR}\"` 修复备份目录权限。"
        ))

    return findings


def check_processes() -> List[DoctorFinding]:
    """Check running status of BetterAndBetter and helper process."""
    findings: List[DoctorFinding] = []
    app_running, app_pid = _get_process_info(APP_PROCESS_NAME)
    helper_running, helper_pid = _get_process_info(HELPER_PROCESS_NAME)

    if not app_running:
        findings.append(DoctorFinding(
            severity="WARNING",
            category="PROCESS",
            message=f"BetterAndBetter 主进程未在运行。",
            resolution="运行 `bab reload` 或打开 `/Applications/BetterAndBetter.app`。"
        ))
    if not helper_running:
        findings.append(DoctorFinding(
            severity="WARNING",
            category="PROCESS",
            message=f"BetterAndBetterHelper 辅助进程未在运行。",
            resolution="确保在系统设置中授予了辅助功能权限，并重启应用。"
        ))

    return findings


def check_launchd_daemon() -> List[DoctorFinding]:
    """Check LaunchAgent daemon health and legacy residue."""
    findings: List[DoctorFinding] = []
    st = get_daemon_status()

    if not st["installed"]:
        findings.append(DoctorFinding(
            severity="WARNING",
            category="DAEMON",
            message="自动备份守护进程 (LaunchAgent) 未安装。",
            resolution="运行 `bab backup --install-daemon` 安装并激活自动备份守护进程。"
        ))
    elif not st["loaded"]:
        findings.append(DoctorFinding(
            severity="WARNING",
            category="DAEMON",
            message="自动备份守护进程已安装但未加载至 launchd。",
            resolution="运行 `bab backup --install-daemon --force` 重新加载守护进程。"
        ))

    if st.get("legacy_detected"):
        findings.append(DoctorFinding(
            severity="WARNING",
            category="DAEMON",
            message=f"检测到遗留的旧版守护进程 ({LEGACY_LAUNCHD_LABEL}) 残留。",
            resolution="运行 `bab backup --install-daemon --force` 自动清理遗留项。"
        ))

    receipt = st.get("receipt")
    if receipt and receipt.get("status") not in ("success", "no_changes"):
        findings.append(DoctorFinding(
            severity="WARNING",
            category="DAEMON",
            message=f"最近一次自动备份报告非正常状态: {receipt.get('status')} ({receipt.get('message')})",
            resolution="运行 `bab backup` 手动测试备份并检查 Git 仓库网络连接。"
        ))

    return findings


def check_git_sync(live_path: str = LIVE_PREFS_PATH, git_path: str = REPO_PREFS_PATH) -> List[DoctorFinding]:
    """Check if live preferences are synchronized with git backup repository."""
    findings: List[DoctorFinding] = []
    if not os.path.exists(git_path):
        findings.append(DoctorFinding(
            severity="WARNING",
            category="SYNC",
            message=f"Git 备份文件不存在: {git_path}",
            resolution="运行 `bab sync --to-git` 创建首份 Git 备份。"
        ))
        return findings

    try:
        live_data = load_plist(live_path)
        git_data = load_plist(git_path)
        diff = diff_plists(live_data, git_data)
        if not diff["is_synced"]:
            findings.append(DoctorFinding(
                severity="WARNING",
                category="SYNC",
                message=f"检测到 Live 本地偏好与 Git 备份存在状态漂移 (共 {len(diff['summary'])} 项差异)。",
                details={"diff_summary": diff["summary"]},
                resolution="运行 `bab diff` 查看差异明细，并运行 `bab sync --to-git` 或 `bab backup` 固化修改。"
            ))
    except Exception as e:
        findings.append(DoctorFinding(
            severity="WARNING",
            category="SYNC",
            message=f"对账检查执行出错: {e}"
        ))

    return findings


def check_orphaned_scripts(data: Dict[str, Any]) -> List[DoctorFinding]:
    """
    Deep contract check: scan all rules in all categories for ActionType='AppleScript',
    and verify that the referenced Action ID exists in ruleOfAppleScript.
    Detects ghost rules where users deleted a script but the trigger still calls it.
    """
    findings: List[DoctorFinding] = []
    valid_scripts = {
        s.get("Id") for s in data.get("ruleOfAppleScript", [])
        if isinstance(s, dict) and s.get("Id")
    }
    valid_script_names = {
        s.get("Name", "").lower() for s in data.get("ruleOfAppleScript", [])
        if isinstance(s, dict) and s.get("Name")
    }

    orphans = []
    for cat_slug, cat_key in RULE_CATEGORIES.items():
        if cat_key == "ruleOfAppleScript":
            continue
        for app in data.get(cat_key, []):
            if not isinstance(app, dict):
                continue
            app_name = app.get("AppName", "Unknown")
            for idx, r in enumerate(app.get("All Rules", [])):
                if not isinstance(r, dict):
                    continue
                act = r.get("Action")
                if isinstance(act, dict) and act.get("ActionType") == "AppleScript":
                    target_id = str(act.get("Action", ""))
                    if target_id not in valid_scripts and target_id.lower() not in valid_script_names:
                        g = r.get("Gesture")
                        if cat_key == "ruleOfKeyboard" and isinstance(g, dict):
                            trigger_str = format_shortcut(g.get("keyCode"), g.get("modifierFlags"))
                        else:
                            trigger_str = str(g)
                        orphans.append({
                            "app": app_name,
                            "category": cat_key,
                            "index": idx,
                            "trigger": trigger_str,
                            "referenced_id": target_id,
                            "enabled": _normalize_enable(r.get("Enable")),
                        })

    if orphans:
        findings.append(DoctorFinding(
            severity="WARNING",
            category="SCRIPTS",
            message=f"检测到 {len(orphans)} 条规则引用了已失效或已删除的 AppleScript ID (Ghost Triggers)！",
            details={"orphaned_rules": orphans},
            resolution=(
                "这些规则触发时因脚本不存在将无法执行动作。"
                "建议通过 `bab set remove-rule --app <应用名> --category <分类> --key <手势>` 删除失效规则，"
                "或通过 `bab doctor --clean-orphans` 一键安全清理。"
            )
        ))

    return findings


def check_gesture_integrity(data: Dict[str, Any]) -> List[DoctorFinding]:
    """Audit rule gestures for empty objects, missing keycodes, or duplicate triggers."""
    findings: List[DoctorFinding] = []
    empty_gestures = []
    duplicates = []

    for cat_slug, cat_key in RULE_CATEGORIES.items():
        if cat_key == "ruleOfAppleScript":
            continue
        for app in data.get(cat_key, []):
            if not isinstance(app, dict):
                continue
            app_name = app.get("AppName", "Unknown")
            seen_triggers = set()

            for idx, r in enumerate(app.get("All Rules", [])):
                if not isinstance(r, dict):
                    continue
                g = r.get("Gesture")
                if g in ({}, None, ""):
                    empty_gestures.append({
                        "app": app_name,
                        "category": cat_key,
                        "index": idx,
                        "action": r.get("Action"),
                    })
                    continue

                if cat_key == "ruleOfKeyboard" and isinstance(g, dict):
                    kc = g.get("keyCode")
                    mf = g.get("modifierFlags")
                    if kc is None and not mf:
                        empty_gestures.append({
                            "app": app_name,
                            "category": cat_key,
                            "index": idx,
                        })
                        continue
                    sig = f"KEY:{kc}:{mf}"
                else:
                    sig = f"STR:{str(g).strip().lower()}"

                if sig in seen_triggers:
                    duplicates.append({
                        "app": app_name,
                        "category": cat_key,
                        "trigger": str(g),
                        "index": idx,
                    })
                else:
                    seen_triggers.add(sig)

    if empty_gestures:
        findings.append(DoctorFinding(
            severity="INFO",
            category="GESTURES",
            message=f"检测到 {len(empty_gestures)} 条空手势或未分配快捷键的规则占位项 (通常为未激活的动作模板)。",
            details={"empty_count": len(empty_gestures)},
            resolution="若不需要这些占位规则，可按需清理以精简配置文件体积。"
        ))

    if duplicates:
        findings.append(DoctorFinding(
            severity="WARNING",
            category="GESTURES",
            message=f"检测到 {len(duplicates)} 处重复绑定的手势规则 (相同应用内存在多个相同触发器)。",
            details={"duplicates": duplicates[:10]},
            resolution="建议检查并删除冗余的重复手势规则。"
        ))

    return findings


def run_doctor(
    live_path: str = LIVE_PREFS_PATH,
    git_path: str = REPO_PREFS_PATH
) -> DoctorReport:
    """Run all diagnostic doctor health checks and produce an actionable report."""
    all_findings: List[DoctorFinding] = []
    checks_count = 8

    # 1. Plist integrity
    ok, data, plist_findings = check_plist_integrity(live_path)
    all_findings.extend(plist_findings)

    # 2. Permissions
    all_findings.extend(check_permissions(live_path))

    # 3. Processes
    all_findings.extend(check_processes())

    # 4. Launchd daemon
    all_findings.extend(check_launchd_daemon())

    # 5. Git sync parity
    all_findings.extend(check_git_sync(live_path, git_path))

    if ok and data is not None:
        # 6. Orphaned scripts
        all_findings.extend(check_orphaned_scripts(data))

        # 7. Gesture integrity & duplicates
        all_findings.extend(check_gesture_integrity(data))

    crit_count = sum(1 for f in all_findings if f.severity == "CRITICAL")
    warn_count = sum(1 for f in all_findings if f.severity == "WARNING")
    info_count = sum(1 for f in all_findings if f.severity == "INFO")

    if crit_count > 0:
        verdict = "CRITICAL"
    elif warn_count > 0:
        verdict = "WARNING"
    else:
        verdict = "HEALTHY"

    return DoctorReport(
        verdict=verdict,
        checks_run=checks_count,
        findings=all_findings,
        summary={
            "critical": crit_count,
            "warning": warn_count,
            "info": info_count,
            "total_findings": len(all_findings),
        }
    )


def clean_orphaned_rules(
    plist_path: str = LIVE_PREFS_PATH,
    disable_only: bool = True,
    reload_bab: bool = False
) -> Dict[str, Any]:
    """
    Safely clean or disable orphaned AppleScript rules with pre-mutation backup.
    If disable_only is True, sets Enable=0 instead of deleting from plist.
    """
    with PlistLock(plist_path):
        data = load_plist(plist_path)
        valid_scripts = {
            s.get("Id") for s in data.get("ruleOfAppleScript", [])
            if isinstance(s, dict) and s.get("Id")
        }
        valid_names = {
            s.get("Name", "").lower() for s in data.get("ruleOfAppleScript", [])
            if isinstance(s, dict) and s.get("Name")
        }

        modified_count = 0
        cleaned_rules = []

        for cat_slug, cat_key in RULE_CATEGORIES.items():
            if cat_key == "ruleOfAppleScript":
                continue
            for app in data.get(cat_key, []):
                if not isinstance(app, dict):
                    continue
                app_name = app.get("AppName", "Unknown")
                rules = app.get("All Rules", [])
                indices_to_remove = []

                for idx, r in enumerate(rules):
                    if not isinstance(r, dict):
                        continue
                    act = r.get("Action")
                    if isinstance(act, dict) and act.get("ActionType") == "AppleScript":
                        target_id = str(act.get("Action", ""))
                        if target_id not in valid_scripts and target_id.lower() not in valid_names:
                            cleaned_rules.append({
                                "app": app_name,
                                "category": cat_key,
                                "gesture": str(r.get("Gesture")),
                                "script_id": target_id,
                            })
                            if disable_only:
                                r["Enable"] = 0
                                modified_count += 1
                            else:
                                indices_to_remove.append(idx)

                if not disable_only and indices_to_remove:
                    for i in reversed(indices_to_remove):
                        rules.pop(i)
                    modified_count += len(indices_to_remove)

        backup_file = save_plist(plist_path, data, backup=True)
        flush_cfprefsd()

        reloaded = False
        if reload_bab:
            reloaded = restart_bab()

        return {
            "status": "success",
            "operation": "disabled" if disable_only else "removed",
            "modified_count": modified_count,
            "cleaned_rules": cleaned_rules,
            "backup_file": backup_file,
            "reloaded": reloaded,
        }

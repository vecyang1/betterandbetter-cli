"""
Type-safe domain models for BetterAndBetter CLI and Diagnostic Engine.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Rule:
    """Represents an individual gesture/shortcut rule in BetterAndBetter."""
    app: str
    category: str
    index: int
    gesture_display: str
    gesture_raw: Any
    action_type: str
    action_display: str
    action_raw: Any
    enabled: bool
    note: str = ""
    is_app_specific: bool = True
    raw_dict: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app": self.app,
            "category": self.category,
            "index": self.index,
            "gesture": self.gesture_display,
            "action_type": self.action_type,
            "action": self.action_display,
            "enabled": self.enabled,
            "note": self.note,
            "is_app_specific": self.is_app_specific,
        }


@dataclass
class AppleScriptItem:
    """Represents an entry in ruleOfAppleScript."""
    id: str
    name: str
    script: str
    note: str = ""
    edited: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "script": self.script,
            "note": self.note,
            "edited": self.edited,
        }


@dataclass
class AppSummary:
    """Summary of configured rules for a single application."""
    app_name: str
    display_name: str
    total_rules: int
    enabled_rules: int
    categories: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_name": self.app_name,
            "display_name": self.display_name,
            "total_rules": self.total_rules,
            "enabled_rules": self.enabled_rules,
            "categories": self.categories,
        }


@dataclass
class StatusInfo:
    """Comprehensive status of the BetterAndBetter installation and configuration."""
    app_installed: bool
    app_version: str
    app_path: str
    app_running: bool
    app_pid: Optional[int]
    helper_running: bool
    helper_pid: Optional[int]
    live_plist_exists: bool
    live_plist_size: int
    live_plist_mtime: Optional[str]
    git_plist_exists: bool
    git_plist_size: int
    git_plist_mtime: Optional[str]
    is_synced: bool
    diff_summary: str
    total_apps: int
    total_rules: int
    total_enabled: int
    category_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    daemon_status: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_installed": self.app_installed,
            "app_version": self.app_version,
            "app_path": self.app_path,
            "app_running": self.app_running,
            "app_pid": self.app_pid,
            "helper_running": self.helper_running,
            "helper_pid": self.helper_pid,
            "live_plist_exists": self.live_plist_exists,
            "live_plist_size": self.live_plist_size,
            "live_plist_mtime": self.live_plist_mtime,
            "git_plist_exists": self.git_plist_exists,
            "git_plist_size": self.git_plist_size,
            "git_plist_mtime": self.git_plist_mtime,
            "is_synced": self.is_synced,
            "diff_summary": self.diff_summary,
            "total_apps": self.total_apps,
            "total_rules": self.total_rules,
            "total_enabled": self.total_enabled,
            "category_stats": self.category_stats,
            "daemon_status": self.daemon_status,
        }


@dataclass
class DiagnosticResult:
    """Detailed result of bab explain / diagnose query."""
    query: str
    query_intent: str
    matched_rules: List[Dict[str, Any]] = field(default_factory=list)
    matched_scripts: List[Dict[str, Any]] = field(default_factory=list)
    shadowing_explanation: str = ""
    drift_explanation: str = ""
    actionable_recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "query_intent": self.query_intent,
            "matched_rules": self.matched_rules,
            "matched_scripts": self.matched_scripts,
            "shadowing_explanation": self.shadowing_explanation,
            "drift_explanation": self.drift_explanation,
            "actionable_recommendations": self.actionable_recommendations,
        }

"""
BetterAndBetter (BAB) Agentic Tooling Package.
"""

from .constants import (
    APP_BUNDLE_PATH,
    LIVE_PREFS_PATH,
    REPO_DIR,
    REPO_PREFS_PATH,
    RULE_CATEGORIES,
)
from .diagnostic import explain_query
from .inspector import get_status, inspect_rules, inspect_scripts, list_configured_apps
from .keycodes import format_shortcut, parse_shortcut
from .modifier import (
    add_or_update_applescript,
    add_or_update_keyboard_rule,
    clone_app_rules,
    toggle_rule,
)
from .plist_manager import diff_plists, load_plist, restart_bab, save_plist
from .sync import run_backup, sync_git_to_live, sync_live_to_git

__all__ = [
    "APP_BUNDLE_PATH",
    "LIVE_PREFS_PATH",
    "REPO_DIR",
    "REPO_PREFS_PATH",
    "RULE_CATEGORIES",
    "explain_query",
    "get_status",
    "inspect_rules",
    "inspect_scripts",
    "list_configured_apps",
    "format_shortcut",
    "parse_shortcut",
    "add_or_update_keyboard_rule",
    "add_or_update_applescript",
    "clone_app_rules",
    "toggle_rule",
    "diff_plists",
    "load_plist",
    "save_plist",
    "restart_bab",
    "sync_live_to_git",
    "sync_git_to_live",
    "run_backup",
]

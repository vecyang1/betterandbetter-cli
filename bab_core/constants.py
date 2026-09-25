"""
BetterAndBetter (BAB) CLI Constants & Schemas.
SSOT definition, paths, keycodes, modifier flags, and app mappings.
"""

import os

# Authoritative Paths (SSOT)
LIVE_PREFS_PATH = os.path.expanduser("~/Library/Preferences/cn.better365.BetterAndBetter.plist")
LIVE_HELPER_PREFS_PATH = os.path.expanduser("~/Library/Preferences/com.better365.BetterAndBetterHelper.plist")
LIVE_PRESETS_DIR = os.path.expanduser("~/Library/Application Support/BetterAndBetter/PresetGroup")

# Git Backup Repository Target (Configurable via environment variables)
_DEFAULT_SYNC_DIR = os.path.expanduser("~/Documents/A-coding/A-Sync/BetterAndBetter")
REPO_DIR = os.getenv(
    "BAB_REPO_DIR",
    _DEFAULT_SYNC_DIR if os.path.exists(os.path.join(_DEFAULT_SYNC_DIR, "cn.better365.BetterAndBetter.plist"))
    else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
REPO_PREFS_PATH = os.getenv("BAB_BACKUP_PREFS", os.path.join(REPO_DIR, "cn.better365.BetterAndBetter.plist"))
REPO_HELPER_PREFS_PATH = os.getenv("BAB_BACKUP_HELPER_PREFS", os.path.join(REPO_DIR, "com.better365.BetterAndBetterHelper.plist"))
REPO_PRESETS_DIR = os.getenv("BAB_BACKUP_PRESETS", os.path.join(REPO_DIR, "PresetGroup"))
REPO_BACKUP_SCRIPT = os.path.join(REPO_DIR, "backup.sh")

# Safety Backup Storage (for safe mutations)
BACKUP_DIR = os.path.expanduser("~/.bab_backups")

# Application Bundle
APP_BUNDLE_PATH = "/Applications/BetterAndBetter.app"
APP_PROCESS_NAME = "BetterAndBetter"
HELPER_PROCESS_NAME = "BetterAndBetterHelper"

# Rule Categories in cn.better365.BetterAndBetter.plist
RULE_CATEGORIES = {
    "keyboard": "ruleOfKeyboard",
    "trackpad": "ruleOfTrackPad",
    "magicmouse": "ruleOfMagicMouse",
    "normalmouse": "ruleOfNormalMouse",
    "hotcorners": "ruleOfHotCorners",
    "applescript": "ruleOfAppleScript",
}

RULE_CATEGORY_TITLES = {
    "ruleOfKeyboard": "键盘快捷键 (Keyboard Shortcuts)",
    "ruleOfTrackPad": "触控板手势 (Trackpad Gestures)",
    "ruleOfMagicMouse": "妙控鼠标手势 (Magic Mouse Gestures)",
    "ruleOfNormalMouse": "普通鼠标操作 (Normal Mouse Actions)",
    "ruleOfHotCorners": "屏幕触发角 (Hot Corners)",
    "ruleOfAppleScript": "AppleScript 脚本库 (AppleScript Library)",
}

# Cocoa NSEventModifierFlags bitmasks
MOD_SHIFT = 1 << 17    # 131072 (0x20000)
MOD_CONTROL = 1 << 18  # 262144 (0x40000)
MOD_OPTION = 1 << 19   # 524288 (0x80000)
MOD_COMMAND = 1 << 20  # 1048576 (0x100000)
MOD_MASK_DEVICE_INDEPENDENT = 0xFFFF0000

# Virtual Keycodes in macOS (Carbon / Cocoa)
VIRTUAL_KEYCODES = {
    'a': 0, 's': 1, 'd': 2, 'f': 3, 'h': 4, 'g': 5, 'z': 6, 'x': 7,
    'c': 8, 'v': 9, 'b': 11, 'q': 12, 'w': 13, 'e': 14, 'r': 15,
    'y': 16, 't': 17, '1': 18, '2': 19, '3': 20, '4': 21, '6': 22,
    '5': 23, '=': 24, '+': 24, 'plus': 24, 'equal': 24, 'equals': 24,
    '9': 25, '7': 26, '-': 27, 'minus': 27, 'hyphen': 27, '8': 28, '0': 29,
    ']': 30, 'bracketright': 30, 'o': 31, 'u': 32, '[': 33, 'bracketleft': 33,
    'i': 34, 'p': 35, 'return': 36, 'enter': 36, 'l': 37, 'j': 38,
    "'": 39, 'quote': 39, 'apostrophe': 39, 'k': 40, ';': 41, 'semicolon': 41,
    '\\': 42, 'backslash': 42, ',': 43, 'comma': 43, '/': 44, 'slash': 44,
    'n': 45, 'm': 46, '.': 47, 'period': 47, 'dot': 47, 'tab': 48, 'space': 49,
    '`': 50, 'backtick': 50, 'grave': 50, 'tilde': 50, 'delete': 51,
    'backspace': 51, 'del': 51, 'bs': 51, 'escape': 53, 'esc': 53,
    'f5': 96, 'f6': 97, 'f7': 98, 'f3': 99, 'f8': 100, 'f9': 101,
    'f11': 103, 'f13': 105, 'f14': 107, 'f10': 109, 'f12': 111,
    'home': 115, 'pageup': 116, 'pgup': 116, 'f4': 118, 'end': 119,
    'f2': 120, 'pagedown': 121, 'pgdn': 121, 'f1': 122,
    'left': 123, 'arrowleft': 123, 'right': 124, 'arrowright': 124,
    'down': 125, 'arrowdown': 125, 'up': 126, 'arrowup': 126
}

# Display names for keycodes
KEY_DISPLAY_NAMES = {
    0: 'A', 1: 'S', 2: 'D', 3: 'F', 4: 'H', 5: 'G', 6: 'Z', 7: 'X',
    8: 'C', 9: 'V', 11: 'B', 12: 'Q', 13: 'W', 14: 'E', 15: 'R',
    16: 'Y', 17: 'T', 18: '1', 19: '2', 20: '3', 21: '4', 22: '6',
    23: '5', 24: '=', 25: '9', 26: '7', 27: '-', 28: '8', 29: '0',
    30: ']', 31: 'O', 32: 'U', 33: '[', 34: 'I', 35: 'P', 36: '↩',
    37: 'L', 38: 'J', 39: "'", 40: 'K', 41: ';', 42: '\\',
    43: ',', 44: '/', 45: 'N', 46: 'M', 47: '.', 48: '⇥', 49: 'Space',
    50: '`', 51: '⌫', 53: '⎋',
    96: 'F5', 97: 'F6', 98: 'F7', 99: 'F3', 100: 'F8', 101: 'F9',
    103: 'F11', 105: 'F13', 107: 'F14', 109: 'F10', 111: 'F12',
    115: 'Home', 116: 'PageUp', 118: 'F4', 119: 'End', 120: 'F2',
    121: 'PageDown', 122: 'F1',
    123: '←', 124: '→', 125: '↓', 126: '↑'
}

# Well-known application aliases for intuitive resolution
KNOWN_APP_ALIASES = {
    "all": "All Applications",
    "global": "All Applications",
    "all applications": "All Applications",
    "finder": "com.apple.finder",
    "safari": "com.apple.Safari",
    "chrome": "com.google.Chrome",
    "google chrome": "com.google.Chrome",
    "arc": "company.thebrowser.Browser",
    "browser": "company.thebrowser.Browser",
    "dia": "company.thebrowser.dia",
    "obsidian": "md.obsidian",
    "path finder": "com.cocoatech.PathFinder",
    "pathfinder": "com.cocoatech.PathFinder",
    "pathfinder setapp": "com.cocoatech.PathFinder-setapp",
    "antigravity": "com.google.antigravity",
    "photoshop": "com.adobe.Photoshop",
    "final cut": "com.apple.FinalCut",
    "final cut pro": "com.apple.FinalCut",
    "spark": "com.readdle.SparkDesktop-setapp",
    "notion": "notion.id",
    "preview": "com.apple.Preview",
    "quicktime": "com.apple.QuickTimePlayerX",
    "wechat": "com.tencent.xinWeChat",
    "tana": "inc.tana.desktop",
    "boltgpt": "co.podzim.BoltGPT",
    "recut": "co.tinywins.recut",
    "elmedia": "com.eltima.elmedia6.mas",
    "pdf expert": "com.readdle.PDFExpert-Mac",
    "typinator": "com.macility.typinator2",
    "atlas": "com.openai.atlas",
    "chatgpt": "com.openai.atlas",
    "ego": "com.citrolabs.ego.lite",
    "ego lite": "com.citrolabs.ego.lite",
    "egolite": "com.citrolabs.ego.lite",
}

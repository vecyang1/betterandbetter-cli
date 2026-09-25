"""
Keycode and modifier parsing and formatting utilities for BetterAndBetter.
Supports macOS Carbon/Cocoa Virtual Keycodes and NSEventModifierFlags.
"""

import re
from typing import Optional, Tuple
from .constants import (
    VIRTUAL_KEYCODES,
    KEY_DISPLAY_NAMES,
    MOD_SHIFT,
    MOD_CONTROL,
    MOD_OPTION,
    MOD_COMMAND,
    MOD_MASK_DEVICE_INDEPENDENT,
)

# Common modifier aliases
MOD_ALIAS_MAP = {
    "cmd": MOD_COMMAND,
    "command": MOD_COMMAND,
    "⌘": MOD_COMMAND,
    "super": MOD_COMMAND,
    "opt": MOD_OPTION,
    "option": MOD_OPTION,
    "alt": MOD_OPTION,
    "⌥": MOD_OPTION,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "⌃": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "shft": MOD_SHIFT,
    "⇧": MOD_SHIFT,
}

# Invert KEY_DISPLAY_NAMES for reverse lookup
_REVERSE_DISPLAY_MAP = {v.lower(): k for k, v in KEY_DISPLAY_NAMES.items()}


def parse_shortcut(shortcut_str: str) -> Tuple[Optional[int], int]:
    """
    Parse a shortcut string (e.g. '⌘B', 'cmd+b', '⇧⌘N', 'ctrl+opt+space', 'opt+f1')
    into (keyCode, modifierFlags).
    Returns (None, flags) if the key cannot be identified.
    """
    if not shortcut_str or not shortcut_str.strip():
        return None, 0

    s = shortcut_str.strip()
    flags = 0

    # 1. Extract prefix symbols (⌃⌥⇧⌘)
    while s and s[0] in "⌃⌥⇧⌘":
        if s[0] == "⌃":
            flags |= MOD_CONTROL
        elif s[0] == "⌥":
            flags |= MOD_OPTION
        elif s[0] == "⇧":
            flags |= MOD_SHIFT
        elif s[0] == "⌘":
            flags |= MOD_COMMAND
        s = s[1:].strip()

    # If all symbols consumed and remainder is empty
    if not s:
        return None, flags

    # 2. Tokenize remainder by +, -, or whitespace
    # Handle single special characters like '+', '-', etc.
    key_token = None
    if s in ("+", "-", "++", "--", "=", "=="):
        key_token = s[-1]
        tokens = []
    elif s.endswith("++") or s.endswith("+-") or s.endswith("+="):
        key_token = s[-1]
        tokens = [t.strip().lower() for t in re.split(r"[\+\-\s]+", s[:-1]) if t.strip()]
    elif s.endswith("+") and len(s) > 1 and s[-2] not in "⌃⌥⇧⌘":
        key_token = "+"
        tokens = [t.strip().lower() for t in re.split(r"[\+\-\s]+", s[:-1]) if t.strip()]
    else:
        tokens = [t.strip().lower() for t in re.split(r"[\+\-\s]+", s) if t.strip()]

    for token in tokens:
        if token in MOD_ALIAS_MAP:
            flags |= MOD_ALIAS_MAP[token]
        else:
            key_token = token

    if key_token is None and not tokens and s:
        key_token = s.lower()

    if not key_token:
        return None, flags

    # 3. Resolve keycode
    kc = VIRTUAL_KEYCODES.get(key_token.lower())
    if kc is None:
        kc = _REVERSE_DISPLAY_MAP.get(key_token.lower())

    # Raw keycode pattern: e.g. "keycode:11" or "11" (if purely numeric and not a single digit 0-9)
    if kc is None and key_token.startswith("keycode:"):
        try:
            kc = int(key_token.split(":", 1)[1])
        except ValueError:
            pass

    return kc, flags


def format_shortcut(keycode: Optional[int], modifier_flags: Optional[int]) -> str:
    """
    Format keyCode and modifierFlags into a human-readable macOS shortcut string.
    e.g. format_shortcut(11, 1048576) -> '⌘B'
    e.g. format_shortcut(45, 1179648) -> '⇧⌘N'
    """
    mods = ""
    if modifier_flags:
        # Standard macOS order: Control -> Option -> Shift -> Command
        if modifier_flags & MOD_CONTROL:
            mods += "⌃"
        if modifier_flags & MOD_OPTION:
            mods += "⌥"
        if modifier_flags & MOD_SHIFT:
            mods += "⇧"
        if modifier_flags & MOD_COMMAND:
            mods += "⌘"

    if keycode is None:
        return mods if mods else "<None>"

    key_name = KEY_DISPLAY_NAMES.get(keycode, f"Key({keycode})")
    return f"{mods}{key_name}"


def format_modifier_name(modifier_flags: Optional[int]) -> str:
    """
    Format modifierFlags into BetterAndBetter's internal modifierFlagsName string.
    e.g. 'Left_ShiftLeft_Command', 'Left_Command'
    """
    if not modifier_flags:
        return ""
    parts = []
    if modifier_flags & MOD_CONTROL:
        parts.append("Left_Control")
    if modifier_flags & MOD_OPTION:
        parts.append("Left_Option")
    if modifier_flags & MOD_SHIFT:
        parts.append("Left_Shift")
    if modifier_flags & MOD_COMMAND:
        parts.append("Left_Command")
    return "".join(parts)


def normalize_flags(flags: Optional[int]) -> int:
    """Mask out device-dependent bits (lower 16 bits)."""
    if flags is None:
        return 0
    return flags & MOD_MASK_DEVICE_INDEPENDENT


def flags_match(flag1: Optional[int], flag2: Optional[int]) -> bool:
    """Check if two modifier flags have identical semantic modifiers."""
    return normalize_flags(flag1) == normalize_flags(flag2)


def shortcut_matches(
    rule_gesture: dict,
    target_keycode: Optional[int],
    target_flags: Optional[int],
    exact_flags: bool = True
) -> bool:
    """
    Check if a rule gesture dictionary matches the given target keycode and flags.
    When exact_flags is True, modifier flags must match exactly, including zero modifiers.
    """
    if not isinstance(rule_gesture, dict):
        return False

    r_kc = rule_gesture.get("keyCode")
    r_flags = rule_gesture.get("modifierFlags")

    if target_keycode is not None and r_kc != target_keycode:
        return False

    if exact_flags:
        return flags_match(r_flags, target_flags if target_flags is not None else 0)
    else:
        if target_flags is not None and target_flags > 0:
            r_norm = normalize_flags(r_flags)
            t_norm = normalize_flags(target_flags)
            return (r_norm & t_norm) == t_norm
        return True

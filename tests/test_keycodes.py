"""
Unit tests for bab_core.keycodes
"""

import unittest
from bab_core.constants import (
    MOD_COMMAND,
    MOD_CONTROL,
    MOD_OPTION,
    MOD_SHIFT,
)
from bab_core.keycodes import (
    flags_match,
    format_modifier_name,
    format_shortcut,
    normalize_flags,
    parse_shortcut,
    shortcut_matches,
)


class TestKeycodes(unittest.TestCase):

    def test_parse_shortcut_single_keys(self):
        # Letters
        kc, flags = parse_shortcut("b")
        self.assertEqual(kc, 11)
        self.assertEqual(flags, 0)

        kc, flags = parse_shortcut("A")
        self.assertEqual(kc, 0)
        self.assertEqual(flags, 0)

        # Numbers
        kc, flags = parse_shortcut("1")
        self.assertEqual(kc, 18)
        self.assertEqual(flags, 0)

        # Special keys
        kc, flags = parse_shortcut("Space")
        self.assertEqual(kc, 49)
        kc, flags = parse_shortcut("Tab")
        self.assertEqual(kc, 48)
        kc, flags = parse_shortcut("Escape")
        self.assertEqual(kc, 53)
        kc, flags = parse_shortcut("Esc")
        self.assertEqual(kc, 53)
        kc, flags = parse_shortcut("Return")
        self.assertEqual(kc, 36)
        kc, flags = parse_shortcut("Enter")
        self.assertEqual(kc, 36)
        kc, flags = parse_shortcut("Up")
        self.assertEqual(kc, 126)
        kc, flags = parse_shortcut("Down")
        self.assertEqual(kc, 125)
        kc, flags = parse_shortcut("Left")
        self.assertEqual(kc, 123)
        kc, flags = parse_shortcut("Right")
        self.assertEqual(kc, 124)

    def test_parse_shortcut_with_symbols(self):
        kc, flags = parse_shortcut("⌘B")
        self.assertEqual(kc, 11)
        self.assertEqual(flags, MOD_COMMAND)

        kc, flags = parse_shortcut("⇧⌘N")
        self.assertEqual(kc, 45)
        self.assertEqual(flags, MOD_COMMAND | MOD_SHIFT)

        kc, flags = parse_shortcut("⌃⌥⌘X")
        self.assertEqual(kc, 7)
        self.assertEqual(flags, MOD_COMMAND | MOD_OPTION | MOD_CONTROL)

    def test_parse_shortcut_with_text_modifiers(self):
        kc, flags = parse_shortcut("cmd+b")
        self.assertEqual(kc, 11)
        self.assertEqual(flags, MOD_COMMAND)

        kc, flags = parse_shortcut("command+shift+n")
        self.assertEqual(kc, 45)
        self.assertEqual(flags, MOD_COMMAND | MOD_SHIFT)

        kc, flags = parse_shortcut("ctrl+alt+delete")
        self.assertEqual(kc, 51)
        self.assertEqual(flags, MOD_CONTROL | MOD_OPTION)

        kc, flags = parse_shortcut("opt+space")
        self.assertEqual(kc, 49)
        self.assertEqual(flags, MOD_OPTION)

    def test_format_shortcut(self):
        self.assertEqual(format_shortcut(11, MOD_COMMAND), "⌘B")
        self.assertEqual(format_shortcut(45, MOD_COMMAND | MOD_SHIFT), "⇧⌘N")
        self.assertEqual(format_shortcut(7, MOD_COMMAND | MOD_OPTION | MOD_CONTROL), "⌃⌥⌘X")
        self.assertEqual(format_shortcut(49, MOD_OPTION), "⌥Space")
        self.assertEqual(format_shortcut(126, 0), "↑")
        self.assertEqual(format_shortcut(None, MOD_COMMAND), "⌘")

    def test_format_modifier_name(self):
        self.assertEqual(format_modifier_name(MOD_COMMAND), "Left_Command")
        self.assertEqual(format_modifier_name(MOD_COMMAND | MOD_SHIFT), "Left_ShiftLeft_Command")
        self.assertEqual(
            format_modifier_name(MOD_COMMAND | MOD_OPTION | MOD_CONTROL),
            "Left_ControlLeft_OptionLeft_Command"
        )
        self.assertEqual(format_modifier_name(0), "")

    def test_flags_match_and_device_bits(self):
        # 1179914 has lower 16-bit device flags (0x10A), while 1179648 is pure Command+Shift
        flag_with_device_bits = 1179914
        flag_pure = MOD_COMMAND | MOD_SHIFT
        self.assertTrue(flags_match(flag_with_device_bits, flag_pure))

        # Command vs Option
        self.assertFalse(flags_match(MOD_COMMAND, MOD_OPTION))

    def test_shortcut_matches(self):
        gesture = {
            "keyCode": 11,
            "modifierFlags": 1048840,  # Command with device bit
        }
        self.assertTrue(shortcut_matches(gesture, 11, MOD_COMMAND))
        self.assertFalse(shortcut_matches(gesture, 11, MOD_OPTION))
        self.assertFalse(shortcut_matches(gesture, 12, MOD_COMMAND))

    def test_shortcut_matches_zero_flags(self):
        # A rule with Command modifier must NOT match target_flags=0 when exact_flags is True
        gesture_cmd_b = {"keyCode": 11, "modifierFlags": 1048576}
        self.assertFalse(shortcut_matches(gesture_cmd_b, 11, 0, exact_flags=True))

        # A rule with 0 modifiers must match target_flags=0
        gesture_plain_b = {"keyCode": 11, "modifierFlags": 0}
        self.assertTrue(shortcut_matches(gesture_plain_b, 11, 0, exact_flags=True))
        self.assertFalse(shortcut_matches(gesture_plain_b, 11, MOD_COMMAND, exact_flags=True))

    def test_parse_shortcut_plus_minus(self):
        # Zoom in / out shortcuts
        kc, flags = parse_shortcut("cmd++")
        self.assertEqual(kc, 24)
        self.assertEqual(flags, MOD_COMMAND)

        kc, flags = parse_shortcut("cmd+-")
        self.assertEqual(kc, 27)
        self.assertEqual(flags, MOD_COMMAND)

        kc, flags = parse_shortcut("cmd+plus")
        self.assertEqual(kc, 24)
        self.assertEqual(flags, MOD_COMMAND)

        kc, flags = parse_shortcut("cmd+minus")
        self.assertEqual(kc, 27)
        self.assertEqual(flags, MOD_COMMAND)

        kc, flags = parse_shortcut("cmd+equal")
        self.assertEqual(kc, 24)
        self.assertEqual(flags, MOD_COMMAND)

        kc, flags = parse_shortcut("⌘+")
        self.assertEqual(kc, 24)
        self.assertEqual(flags, MOD_COMMAND)

        kc, flags = parse_shortcut("⌘-")
        self.assertEqual(kc, 27)
        self.assertEqual(flags, MOD_COMMAND)

    def test_empty_and_invalid_inputs(self):
        kc, flags = parse_shortcut("")
        self.assertIsNone(kc)
        self.assertEqual(flags, 0)

        kc, flags = parse_shortcut("UnknownKeyXYZ")
        self.assertIsNone(kc)


if __name__ == "__main__":
    unittest.main()

"""
Edge cases and boundary tests for BetterAndBetter tooling.
"""

import os
import plistlib
import subprocess
import tempfile
import unittest

from bab_core.constants import MOD_COMMAND, MOD_CONTROL, MOD_OPTION, MOD_SHIFT
from bab_core.diagnostic import explain_query
from bab_core.inspector import inspect_rules
from bab_core.keycodes import (
    format_shortcut,
    parse_shortcut,
    shortcut_matches,
)
from bab_core.modifier import (
    add_or_update_keyboard_rule,
    toggle_rule,
)
from bab_core.plist_manager import diff_plists, load_plist, save_plist


class TestEdgeCases(unittest.TestCase):

    def test_all_modifier_combinations(self):
        # All 4 modifiers combined: Control + Option + Shift + Command + C
        flags_all = MOD_CONTROL | MOD_OPTION | MOD_SHIFT | MOD_COMMAND
        kc, flags = parse_shortcut("ctrl+opt+shift+cmd+c")
        self.assertEqual(kc, 8)  # 'c'
        self.assertEqual(flags, flags_all)
        self.assertEqual(format_shortcut(kc, flags), "⌃⌥⇧⌘C")

    def test_unicode_and_special_symbol_parsing(self):
        # Bracket keys
        kc, _ = parse_shortcut("]")
        self.assertEqual(kc, 30)
        kc, _ = parse_shortcut("[")
        self.assertEqual(kc, 33)

        # Backslash
        kc, _ = parse_shortcut("\\")
        self.assertEqual(kc, 42)

        # Semicolon and Quote
        kc, _ = parse_shortcut(";")
        self.assertEqual(kc, 41)
        kc, _ = parse_shortcut("'")
        self.assertEqual(kc, 39)

        # Backtick
        kc, _ = parse_shortcut("`")
        self.assertEqual(kc, 50)

    def test_empty_plist_handling(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plist_path = os.path.join(tmp_dir, "empty.plist")
            with open(plist_path, "wb") as f:
                plistlib.dump({}, f)

            # Load empty plist
            data = load_plist(plist_path)
            self.assertEqual(data, {})

            # Explain on empty data
            res = explain_query("⌘B", data, data)
            self.assertEqual(len(res.matched_rules), 0)

            # Add rule to empty plist
            res_add = add_or_update_keyboard_rule(
                plist_path=plist_path,
                app_name="TestApp",
                key_str="⌘B",
                action_type="Preset",
                action_value="LockScreen",
                reload_bab=False,
            )
            self.assertEqual(res_add["status"], "success")
            self.assertEqual(res_add["operation"], "added")

            reloaded = load_plist(plist_path)
            self.assertIn("ruleOfKeyboard", reloaded)
            self.assertEqual(len(reloaded["ruleOfKeyboard"]), 1)

    def test_diff_with_empty_and_corrupt_entries(self):
        live = {
            "ruleOfKeyboard": [
                {"AppName": "App1", "All Rules": [{"Gesture": None, "Action": None}]}
            ]
        }
        git = {
            "ruleOfKeyboard": []
        }
        diff = diff_plists(live, git)
        self.assertFalse(diff["is_synced"])
        self.assertIn("App1", diff["categories"]["ruleOfKeyboard"]["apps_only_in_live"])

    def test_modifier_invalid_shortcut_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plist_path = os.path.join(tmp_dir, "test.plist")
            with open(plist_path, "wb") as f:
                plistlib.dump({"ruleOfKeyboard": []}, f)

            with self.assertRaises(ValueError):
                add_or_update_keyboard_rule(
                    plist_path=plist_path,
                    app_name="App",
                    key_str="NonExistentKeyString",
                    action_type="Preset",
                    action_value="Sleep",
                    reload_bab=False,
                )

    def test_hotcorners_and_mouse_rules_inspection(self):
        mock_data = {
            "ruleOfHotCorners": [
                {
                    "AppName": "All Applications",
                    "All Rules": [
                        {
                            "Gesture": "LeftMouse Click at TopRight Corner",
                            "Action": {"ActionType": "Preset", "Action": "LockScreen"},
                            "Enable": "1",
                            "Note": "",
                        }
                    ]
                }
            ],
            "ruleOfNormalMouse": [
                {
                    "AppName": "All Applications",
                    "All Rules": [
                        {
                            "Gesture": "RightMouse",
                            "Action": {"ActionType": "Preset", "Action": "Center"},
                            "Enable": 1,
                            "Note": "",
                        }
                    ]
                }
            ]
        }
        hc_rules = inspect_rules(mock_data, category_filter="hotcorners")
        self.assertEqual(len(hc_rules), 1)
        self.assertEqual(hc_rules[0].gesture_display, "LeftMouse Click at TopRight Corner")
        self.assertTrue(hc_rules[0].enabled)

        mouse_rules = inspect_rules(mock_data, category_filter="normalmouse")
        self.assertEqual(len(mouse_rules), 1)
        self.assertEqual(mouse_rules[0].gesture_display, "RightMouse")


if __name__ == "__main__":
    unittest.main()

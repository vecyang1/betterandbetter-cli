"""
Unit tests for bab_core.inspector
"""

import unittest
from bab_core.inspector import (
    get_status,
    inspect_rules,
    inspect_scripts,
    list_configured_apps,
    resolve_app_name,
)


class TestInspector(unittest.TestCase):

    def setUp(self):
        self.mock_data = {
            "ruleOfKeyboard": [
                {
                    "AppName": "All Applications",
                    "All Rules": [
                        {
                            "Gesture": {"keyCode": 11, "modifierFlags": 1048576},
                            "Action": {"ActionType": "Preset", "Action": "Half_of_Top"},
                            "Enable": 1,
                            "Note": "Global top half",
                        },
                        {
                            "Gesture": {"keyCode": 12, "modifierFlags": 1048576},
                            "Action": {"ActionType": "Shortcut Keys", "Action": {"keyCode": 12, "modifierFlags": 1048576, "ShortcutName": "⌘Q"}},
                            "Enable": 0,
                            "Note": "Disabled rule",
                        }
                    ]
                },
                {
                    "AppName": "md.obsidian",
                    "All Rules": [
                        {
                            "Gesture": {"keyCode": 15, "modifierFlags": 1048576},
                            "Action": {"ActionType": "Shortcut Keys", "Action": {"keyCode": 30, "modifierFlags": 1179914, "ShortcutName": "⇧⌘]"}},
                            "Enable": 1,
                            "Note": "Obsidian switch tab",
                        }
                    ]
                },
                {
                    "AppName": "com.citrolabs.ego.lite",
                    "All Rules": [
                        {
                            "Gesture": {"keyCode": 11, "modifierFlags": 1048576},
                            "Action": {"ActionType": "Preset", "Action": "Click the menu title \"/Tab/Duplicate Tab\""},
                            "Enable": 1,
                            "Note": "",
                        }
                    ]
                }
            ],
            "ruleOfTrackPad": [
                {
                    "AppName": "md.obsidian",
                    "All Rules": [
                        {
                            "Gesture": "3Finger_Tap",
                            "Action": {"ActionType": "Shortcut Keys", "Action": {"keyCode": 51, "modifierFlags": 256, "ShortcutName": "⌫"}},
                            "Enable": 1,
                            "Note": "",
                        }
                    ]
                }
            ],
            "ruleOfAppleScript": [
                {
                    "Id": "SCRIPT-WECHAT",
                    "Name": "Open WeChat",
                    "AppleScript": "tell application \"WeChat\" to activate",
                    "Edited": False,
                    "Note": "",
                }
            ]
        }

    def test_resolve_app_name(self):
        # Known aliases
        app, configured = resolve_app_name(self.mock_data, "obsidian")
        self.assertEqual(app, "md.obsidian")
        self.assertTrue(configured)

        app, configured = resolve_app_name(self.mock_data, "ego lite")
        self.assertEqual(app, "com.citrolabs.ego.lite")
        self.assertTrue(configured)

        # Unconfigured app
        app, configured = resolve_app_name(self.mock_data, "UnknownAppXYZ")
        self.assertEqual(app, "UnknownAppXYZ")
        self.assertFalse(configured)

    def test_inspect_rules_filters(self):
        # All rules
        all_rules = inspect_rules(self.mock_data)
        self.assertEqual(len(all_rules), 5)  # 4 keyboard + 1 trackpad

        # Filter by category
        kb_rules = inspect_rules(self.mock_data, category_filter="keyboard")
        self.assertEqual(len(kb_rules), 4)

        # Filter by app
        obs_rules = inspect_rules(self.mock_data, app_filter="obsidian")
        self.assertEqual(len(obs_rules), 2)  # 1 kb + 1 trackpad

        # Filter enabled only
        enabled_rules = inspect_rules(self.mock_data, enabled_only=True)
        self.assertEqual(len(enabled_rules), 4)

    def test_inspect_scripts(self):
        scripts = inspect_scripts(self.mock_data)
        self.assertEqual(len(scripts), 1)
        self.assertEqual(scripts[0].name, "Open WeChat")

        # Search matching
        res = inspect_scripts(self.mock_data, search="wechat")
        self.assertEqual(len(res), 1)

        # Search non-matching
        res = inspect_scripts(self.mock_data, search="nonexistent")
        self.assertEqual(len(res), 0)

    def test_list_configured_apps(self):
        apps = list_configured_apps(self.mock_data)
        # All Applications should be first
        self.assertEqual(apps[0].app_name, "All Applications")
        app_names = [a.app_name for a in apps]
        self.assertIn("md.obsidian", app_names)
        self.assertIn("com.citrolabs.ego.lite", app_names)


if __name__ == "__main__":
    unittest.main()

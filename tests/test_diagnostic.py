"""
Unit tests for bab_core.diagnostic
"""

import unittest
from bab_core.diagnostic import explain_query


class TestDiagnostic(unittest.TestCase):

    def setUp(self):
        self.live_data = {
            "ruleOfKeyboard": [
                {
                    "AppName": "All Applications",
                    "All Rules": [
                        {
                            "Gesture": {"keyCode": 11, "modifierFlags": 1048576},
                            "Action": {"ActionType": "Preset", "Action": "Half_of_Top"},
                            "Enable": 1,
                            "Note": "Global top half",
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
                    "AppName": "All Applications",
                    "All Rules": [
                        {
                            "Gesture": "3Finger_Tap",
                            "Action": {"ActionType": "Preset", "Action": "Sleep"},
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

        # Git data without ego.lite to test drift detection
        self.git_data = {
            "ruleOfKeyboard": [
                {
                    "AppName": "All Applications",
                    "All Rules": [
                        {
                            "Gesture": {"keyCode": 11, "modifierFlags": 1048576},
                            "Action": {"ActionType": "Preset", "Action": "Half_of_Top"},
                            "Enable": 1,
                            "Note": "Global top half",
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
                }
            ],
            "ruleOfTrackPad": self.live_data["ruleOfTrackPad"],
            "ruleOfAppleScript": self.live_data["ruleOfAppleScript"],
        }

    def test_explain_shortcut_with_shadowing(self):
        # ⌘B exists in both All Applications and com.citrolabs.ego.lite
        res = explain_query("⌘B", self.live_data, self.git_data)
        self.assertEqual(res.query_intent, "SHORTCUT")
        self.assertEqual(len(res.matched_rules), 2)

        apps = [r["app"] for r in res.matched_rules]
        self.assertIn("All Applications", apps)
        self.assertIn("com.citrolabs.ego.lite", apps)

        # Precedence explanation must mention shadowing
        self.assertIn("优先接管", res.shadowing_explanation)
        self.assertIn("All Applications", res.shadowing_explanation)

        # Drift detection must identify that ego.lite is ONLY_IN_LIVE
        ego_rule = next(r for r in res.matched_rules if r["app"] == "com.citrolabs.ego.lite")
        self.assertEqual(ego_rule["drift_status"], "ONLY_IN_LIVE")

    def test_explain_configured_app(self):
        res = explain_query("Obsidian", self.live_data, self.git_data)
        self.assertEqual(res.query_intent, "APP")
        self.assertEqual(len(res.matched_rules), 1)
        self.assertEqual(res.matched_rules[0]["app"], "md.obsidian")
        self.assertIn("md.obsidian", res.shadowing_explanation)

    def test_explain_unconfigured_app(self):
        res = explain_query("UnconfiguredApp", self.live_data, self.git_data)
        self.assertEqual(len(res.matched_rules), 0)
        self.assertIn("All Applications", res.shadowing_explanation)
        self.assertTrue(len(res.actionable_recommendations) > 0)

    def test_explain_gesture(self):
        res = explain_query("3Finger_Tap", self.live_data, self.git_data)
        self.assertEqual(res.query_intent, "GESTURE")
        self.assertEqual(len(res.matched_rules), 1)
        self.assertEqual(res.matched_rules[0]["trigger"], "3Finger_Tap")

    def test_explain_action_keyword(self):
        res = explain_query("WeChat", self.live_data, self.git_data)
        self.assertTrue(len(res.matched_scripts) > 0)
        self.assertEqual(res.matched_scripts[0]["name"], "Open WeChat")


if __name__ == "__main__":
    unittest.main()

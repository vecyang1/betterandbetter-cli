"""
Unit tests for bab_core.plist_manager
"""

import os
import plistlib
import tempfile
import unittest

from bab_core.plist_manager import (
    diff_plists,
    load_plist,
    save_plist,
)


class TestPlistManager(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_plist = os.path.join(self.tmp_dir.name, "test.plist")
        self.sample_data = {
            "ruleOfKeyboard": [
                {
                    "AppName": "All Applications",
                    "All Rules": [
                        {
                            "Gesture": {"keyCode": 11, "modifierFlags": 1048576},
                            "Action": {"ActionType": "Preset", "Action": "Half_of_Top"},
                            "Enable": 1,
                            "Note": "Top half",
                        }
                    ]
                }
            ],
            "ruleOfAppleScript": [
                {
                    "Id": "SCRIPT-1",
                    "Name": "Open Safari",
                    "AppleScript": "tell app \"Safari\" to activate",
                    "Edited": False,
                    "Note": "",
                }
            ]
        }
        with open(self.test_plist, "wb") as f:
            plistlib.dump(self.sample_data, f)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_load_and_save_plist(self):
        data = load_plist(self.test_plist)
        self.assertIn("ruleOfKeyboard", data)
        self.assertEqual(len(data["ruleOfKeyboard"]), 1)

        # Modify and save
        data["new_key"] = "test_value"
        save_plist(self.test_plist, data, backup=False)

        reloaded = load_plist(self.test_plist)
        self.assertEqual(reloaded.get("new_key"), "test_value")

    def test_save_plist_with_backup(self):
        data = load_plist(self.test_plist)
        data["ruleOfKeyboard"][0]["All Rules"][0]["Enable"] = 0
        backup_path = save_plist(self.test_plist, data, backup=True)

        self.assertTrue(os.path.exists(backup_path))
        old_data = load_plist(backup_path)
        self.assertEqual(old_data["ruleOfKeyboard"][0]["All Rules"][0]["Enable"], 1)

    def test_diff_plists_identical(self):
        diff = diff_plists(self.sample_data, self.sample_data)
        self.assertTrue(diff["is_synced"])
        self.assertEqual(len(diff["categories"]), 0)

    def test_diff_plists_modified_enable(self):
        modified_data = {
            "ruleOfKeyboard": [
                {
                    "AppName": "All Applications",
                    "All Rules": [
                        {
                            "Gesture": {"keyCode": 11, "modifierFlags": 1048576},
                            "Action": {"ActionType": "Preset", "Action": "Half_of_Top"},
                            "Enable": 0,  # Toggled to 0
                            "Note": "Top half",
                        }
                    ]
                }
            ],
            "ruleOfAppleScript": self.sample_data["ruleOfAppleScript"],
        }
        diff = diff_plists(modified_data, self.sample_data)
        self.assertFalse(diff["is_synced"])
        self.assertIn("ruleOfKeyboard", diff["categories"])
        chg = diff["categories"]["ruleOfKeyboard"]["apps_with_changes"]["All Applications"]
        self.assertEqual(chg["modified_count"], 1)

    def test_diff_plists_app_added(self):
        modified_data = dict(self.sample_data)
        modified_data["ruleOfKeyboard"] = list(self.sample_data["ruleOfKeyboard"]) + [
            {
                "AppName": "md.obsidian",
                "All Rules": []
            }
        ]
        diff = diff_plists(modified_data, self.sample_data)
        self.assertFalse(diff["is_synced"])
        self.assertIn("md.obsidian", diff["categories"]["ruleOfKeyboard"]["apps_only_in_live"])

    def test_diff_plists_script_changed(self):
        modified_data = dict(self.sample_data)
        modified_data["ruleOfAppleScript"] = [
            {
                "Id": "SCRIPT-1",
                "Name": "Open Safari",
                "AppleScript": "tell app \"Safari\" to activate -- modified",
                "Edited": True,
                "Note": "updated",
            }
        ]
        diff = diff_plists(modified_data, self.sample_data)
        self.assertFalse(diff["is_synced"])
        self.assertEqual(len(diff["scripts"]["modified"]), 1)

    def test_diff_plists_with_duplicate_and_empty_gestures(self):
        # Multiple rules with empty gesture {} or same gesture string
        base_data = {
            "ruleOfKeyboard": [
                {
                    "AppName": "com.example.TestApp",
                    "All Rules": [
                        {"Gesture": {}, "Action": {"ActionType": "Preset", "Action": "Action1"}, "Enable": 1, "Note": "Slot 1"},
                        {"Gesture": {}, "Action": {"ActionType": "Preset", "Action": "Action2"}, "Enable": 1, "Note": "Slot 2"},
                        {"Gesture": "3Finger_Tap", "Action": "A", "Enable": 1, "Note": ""},
                        {"Gesture": "3Finger_Tap", "Action": "B", "Enable": 0, "Note": ""},
                    ]
                }
            ]
        }
        # Identical plists must report synchronized
        diff_same = diff_plists(base_data, base_data)
        self.assertTrue(diff_same["is_synced"])

        # Modifying the FIRST empty-gesture rule's enable MUST be detected, not dropped by key collision
        modified_data = {
            "ruleOfKeyboard": [
                {
                    "AppName": "com.example.TestApp",
                    "All Rules": [
                        {"Gesture": {}, "Action": {"ActionType": "Preset", "Action": "Action1"}, "Enable": 0, "Note": "Slot 1"}, # Toggled
                        {"Gesture": {}, "Action": {"ActionType": "Preset", "Action": "Action2"}, "Enable": 1, "Note": "Slot 2"},
                        {"Gesture": "3Finger_Tap", "Action": "A", "Enable": 1, "Note": ""},
                        {"Gesture": "3Finger_Tap", "Action": "B", "Enable": 0, "Note": ""},
                    ]
                }
            ]
        }
        diff_mod = diff_plists(modified_data, base_data)
        self.assertFalse(diff_mod["is_synced"])
        chg = diff_mod["categories"]["ruleOfKeyboard"]["apps_with_changes"]["com.example.TestApp"]
        self.assertEqual(chg["modified_count"], 1)

    def test_save_real_binary_plist_with_control_characters(self):
        # BetterAndBetter plists contain binary data and control characters
        data_with_ctrl = {
            "ruleOfKeyboard": [
                {
                    "AppName": "AppWithControlChars",
                    "All Rules": [
                        {"Gesture": {"keyCode": 11, "modifierFlags": 1048576}, "Action": "Key\x1b\x03Test", "Enable": 1}
                    ]
                }
            ]
        }
        test_bin_path = os.path.join(self.tmp_dir.name, "binary_test.plist")
        # Save must succeed as binary plist without throwing XML control character error
        save_plist(test_bin_path, data_with_ctrl, backup=False)
        self.assertTrue(os.path.exists(test_bin_path))
        reloaded = load_plist(test_bin_path)
        self.assertEqual(reloaded["ruleOfKeyboard"][0]["All Rules"][0]["Action"], "Key\x1b\x03Test")


if __name__ == "__main__":
    unittest.main()

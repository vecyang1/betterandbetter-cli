"""
Unit tests for bab_core.modifier
"""

import os
import plistlib
import tempfile
import unittest

from bab_core.modifier import (
    add_or_update_applescript,
    add_or_update_keyboard_rule,
    add_or_update_rule,
    clone_app_rules,
    export_app_rules,
    import_app_rules,
    remove_applescript,
    remove_rule,
    toggle_rule,
)
from bab_core.plist_manager import load_plist


class TestModifier(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_plist = os.path.join(self.tmp_dir.name, "test_prefs.plist")
        self.sample_data = {
            "ruleOfKeyboard": [
                {
                    "AppName": "All Applications",
                    "All Rules": [
                        {
                            "Gesture": {"keyCode": 11, "modifierFlags": 1048576},
                            "Action": {"ActionType": "Preset", "Action": "Half_of_Top"},
                            "Enable": 1,
                            "Note": "Original rule",
                        }
                    ]
                }
            ],
            "ruleOfAppleScript": [
                {
                    "Id": "SCRIPT-EXISTING",
                    "Name": "Original Script",
                    "AppleScript": "display dialog \"Hello\"",
                    "Edited": False,
                    "Note": "",
                }
            ]
        }
        with open(self.test_plist, "wb") as f:
            plistlib.dump(self.sample_data, f)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_add_keyboard_rule(self):
        res = add_or_update_keyboard_rule(
            plist_path=self.test_plist,
            app_name="md.obsidian",
            key_str="⌘K",
            action_type="Preset",
            action_value="Center",
            enable=True,
            note="Center window",
            reload_bab=False,
        )
        self.assertEqual(res["operation"], "added")
        self.assertEqual(res["app"], "md.obsidian")

        data = load_plist(self.test_plist)
        app_item = next(item for item in data["ruleOfKeyboard"] if item["AppName"] == "md.obsidian")
        self.assertEqual(len(app_item["All Rules"]), 1)
        r = app_item["All Rules"][0]
        self.assertEqual(r["Action"]["Action"], "Center")
        self.assertEqual(r["Enable"], 1)

    def test_update_existing_keyboard_rule(self):
        # Update ⌘B in All Applications
        res = add_or_update_keyboard_rule(
            plist_path=self.test_plist,
            app_name="All Applications",
            key_str="⌘B",
            action_type="Preset",
            action_value="Maximization",
            enable=False,
            note="Updated rule",
            reload_bab=False,
        )
        self.assertEqual(res["operation"], "updated")

        data = load_plist(self.test_plist)
        r = data["ruleOfKeyboard"][0]["All Rules"][0]
        self.assertEqual(r["Action"]["Action"], "Maximization")
        self.assertEqual(r["Enable"], 0)
        self.assertEqual(r["Note"], "Updated rule")

    def test_toggle_rule_by_shortcut(self):
        # ⌘B was Enable=1, toggling should set it to 0
        res = toggle_rule(
            plist_path=self.test_plist,
            app_name="All Applications",
            category="keyboard",
            key_or_index="⌘B",
            reload_bab=False,
        )
        self.assertTrue(res["previous_enable"])
        self.assertFalse(res["new_enable"])

        data = load_plist(self.test_plist)
        self.assertEqual(data["ruleOfKeyboard"][0]["All Rules"][0]["Enable"], 0)

    def test_toggle_rule_by_index(self):
        res = toggle_rule(
            plist_path=self.test_plist,
            app_name="All Applications",
            category="keyboard",
            key_or_index=0,
            enable=True,
            reload_bab=False,
        )
        self.assertTrue(res["new_enable"])

    def test_toggle_out_of_range(self):
        with self.assertRaises(IndexError):
            toggle_rule(
                plist_path=self.test_plist,
                app_name="All Applications",
                category="keyboard",
                key_or_index=999,
                reload_bab=False,
            )

    def test_add_and_update_applescript(self):
        # Add new
        res = add_or_update_applescript(
            plist_path=self.test_plist,
            name="New Script",
            code="tell app \"Finder\" to sleep",
            note="Sleep Finder",
            reload_bab=False,
        )
        self.assertEqual(res["operation"], "added")

        data = load_plist(self.test_plist)
        self.assertEqual(len(data["ruleOfAppleScript"]), 2)

        # Update existing
        res2 = add_or_update_applescript(
            plist_path=self.test_plist,
            name="New Script",
            code="tell app \"Finder\" to sleep -- updated",
            reload_bab=False,
        )
        self.assertEqual(res2["operation"], "updated")

        data2 = load_plist(self.test_plist)
        s = next(x for x in data2["ruleOfAppleScript"] if x["Name"] == "New Script")
        self.assertIn("-- updated", s["AppleScript"])

    def test_remove_rule_by_shortcut(self):
        # ⌘B exists in All Applications
        res = remove_rule(
            plist_path=self.test_plist,
            app_name="All Applications",
            category="keyboard",
            key_or_index="⌘B",
            reload_bab=False,
        )
        self.assertEqual(res["operation"], "removed")
        data = load_plist(self.test_plist)
        rules = data["ruleOfKeyboard"][0]["All Rules"]
        self.assertEqual(len(rules), 0)

    def test_remove_rule_by_index(self):
        res = remove_rule(
            plist_path=self.test_plist,
            app_name="All Applications",
            category="keyboard",
            index=0,
            reload_bab=False,
        )
        self.assertEqual(res["operation"], "removed")
        data = load_plist(self.test_plist)
        rules = data["ruleOfKeyboard"][0]["All Rules"]
        self.assertEqual(len(rules), 0)

    def test_remove_applescript(self):
        # Remove by ID
        res = remove_applescript(
            plist_path=self.test_plist,
            name_or_id="SCRIPT-EXISTING",
            reload_bab=False,
        )
        self.assertEqual(res["operation"], "removed")
        data = load_plist(self.test_plist)
        self.assertEqual(len(data["ruleOfAppleScript"]), 0)

        # Non-existent script raises ValueError
        with self.assertRaises(ValueError):
            remove_applescript(
                plist_path=self.test_plist,
                name_or_id="non_existent",
                reload_bab=False,
            )

    def test_app_alias_resolution(self):
        # Use alias 'obsidian' which resolves to 'md.obsidian'
        add_or_update_keyboard_rule(
            plist_path=self.test_plist,
            app_name="obsidian",
            key_str="⌘P",
            action_type="Preset",
            action_value="Center",
            reload_bab=False,
        )
        data = load_plist(self.test_plist)
        app_item = next((item for item in data["ruleOfKeyboard"] if item["AppName"] == "md.obsidian"), None)
        self.assertIsNotNone(app_item)

        # Toggle using alias
        res = toggle_rule(
            plist_path=self.test_plist,
            app_name="obsidian",
            key_or_index="⌘P",
            enable=False,
            reload_bab=False,
        )
        self.assertFalse(res["new_enable"])

        # Remove using alias
        rm_res = remove_rule(
            plist_path=self.test_plist,
            app_name="obsidian",
            key_or_index="⌘P",
            reload_bab=False,
        )
        self.assertEqual(rm_res["operation"], "removed")

    def test_numeric_shortcut_vs_index(self):
        # Create an app with shortcuts '1' and '2'
        add_or_update_keyboard_rule(
            plist_path=self.test_plist,
            app_name="NumTest",
            key_str="1",
            action_type="Preset",
            action_value="Action1",
            reload_bab=False,
        )
        add_or_update_keyboard_rule(
            plist_path=self.test_plist,
            app_name="NumTest",
            key_str="2",
            action_type="Preset",
            action_value="Action2",
            reload_bab=False,
        )

        # Toggle shortcut '2' by key string - must NOT fail with IndexError(2) on 2-item list
        res = toggle_rule(
            plist_path=self.test_plist,
            app_name="NumTest",
            key_or_index="2",
            enable=False,
            reload_bab=False,
        )
        self.assertFalse(res["new_enable"])

        data = load_plist(self.test_plist)
        num_app = next(item for item in data["ruleOfKeyboard"] if item["AppName"] == "NumTest")
        # Rule 0 is '1' (enabled=1), Rule 1 is '2' (enabled=0)
        self.assertEqual(num_app["All Rules"][0]["Enable"], 1)
        self.assertEqual(num_app["All Rules"][1]["Enable"], 0)

        # Remove shortcut '1' by key string - must delete rule '1', leaving rule '2'
        rm_res = remove_rule(
            plist_path=self.test_plist,
            app_name="NumTest",
            key_or_index="1",
            reload_bab=False,
        )
        self.assertEqual(rm_res["operation"], "removed")

        data2 = load_plist(self.test_plist)
        num_app2 = next(item for item in data2["ruleOfKeyboard"] if item["AppName"] == "NumTest")
        self.assertEqual(len(num_app2["All Rules"]), 1)
        self.assertEqual(num_app2["All Rules"][0]["Action"]["Action"], "Action2")

    def test_clone_app_rules_single_target(self):
        # Add source rules for chrome
        add_or_update_keyboard_rule(
            plist_path=self.test_plist,
            app_name="com.google.Chrome",
            key_str="⌘R",
            action_type="Preset",
            action_value='Click the menu title "/Tab/Select Next Tab"',
            reload_bab=False
        )
        add_or_update_keyboard_rule(
            plist_path=self.test_plist,
            app_name="com.google.Chrome",
            key_str="⌘E",
            action_type="Preset",
            action_value='Click the menu title "/Tab/Select Previous Tab"',
            reload_bab=False
        )

        # Clone from chrome to adspower
        res = clone_app_rules(
            plist_path=self.test_plist,
            from_app="chrome",
            to_app="adspower-browser",
            categories=["keyboard"],
            reload_bab=False
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["from_app"], "com.google.Chrome")
        self.assertEqual(res["to_app"], "com.adspower.SunBrowser")
        self.assertEqual(res["added_count"], 2)

        data = load_plist(self.test_plist)
        sun_app = next((item for item in data["ruleOfKeyboard"] if item["AppName"] == "com.adspower.SunBrowser"), None)
        self.assertIsNotNone(sun_app)
        self.assertEqual(len(sun_app["All Rules"]), 2)

    def test_clone_app_rules_multi_target_with_aliases(self):
        # Add source rule for chrome
        add_or_update_keyboard_rule(
            plist_path=self.test_plist,
            app_name="com.google.Chrome",
            key_str="⇧⌘B",
            action_type="Preset",
            action_value='Click the menu title "/Tab/Duplicate Tab"',
            reload_bab=False
        )

        # Clone to comma-separated multi targets
        res = clone_app_rules(
            plist_path=self.test_plist,
            from_app="chrome",
            to_app="adspower-browser, bitbrowser, com.adspower.global, com.bitnet.bitbrowser",
            categories=["keyboard"],
            reload_bab=False
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["added_count"], 4)  # 1 rule * 4 targets
        self.assertEqual(len(res["targets"]), 4)

        target_names = [t["to_app"] for t in res["targets"]]
        self.assertIn("com.adspower.SunBrowser", target_names)
        self.assertIn("org.bitbrowser.BitBrowser", target_names)
        self.assertIn("com.adspower.global", target_names)
        self.assertIn("com.bitnet.bitbrowser", target_names)

        data = load_plist(self.test_plist)
        app_names_in_plist = [item["AppName"] for item in data["ruleOfKeyboard"]]
        self.assertIn("com.adspower.SunBrowser", app_names_in_plist)
        self.assertIn("org.bitbrowser.BitBrowser", app_names_in_plist)
        self.assertIn("com.adspower.global", app_names_in_plist)
        self.assertIn("com.bitnet.bitbrowser", app_names_in_plist)

    def test_clone_app_rules_merge_vs_overwrite(self):
        add_or_update_keyboard_rule(
            plist_path=self.test_plist,
            app_name="com.google.Chrome",
            key_str="⌘R",
            action_type="Preset",
            action_value="New Action",
            reload_bab=False
        )
        # Pre-populate target with old action
        add_or_update_keyboard_rule(
            plist_path=self.test_plist,
            app_name="TargetApp",
            key_str="⌘R",
            action_type="Preset",
            action_value="Old Action",
            reload_bab=False
        )

        # Default merge (overwrite=False) -> skips
        res_merge = clone_app_rules(
            plist_path=self.test_plist,
            from_app="com.google.Chrome",
            to_app="TargetApp",
            categories=["keyboard"],
            overwrite=False,
            reload_bab=False
        )
        self.assertEqual(res_merge["skipped_count"], 1)
        self.assertEqual(res_merge["updated_count"], 0)

        # Overwrite=True -> updates
        res_ovw = clone_app_rules(
            plist_path=self.test_plist,
            from_app="com.google.Chrome",
            to_app="TargetApp",
            categories=["keyboard"],
            overwrite=True,
            reload_bab=False
        )
        self.assertEqual(res_ovw["updated_count"], 1)

        data = load_plist(self.test_plist)
        target = next(item for item in data["ruleOfKeyboard"] if item["AppName"] == "TargetApp")
        self.assertEqual(target["All Rules"][0]["Action"]["Action"], "New Action")

    def test_clone_app_rules_validation_errors(self):
        with self.assertRaises(ValueError):
            clone_app_rules(plist_path=self.test_plist, from_app="", to_app="TargetApp")
        with self.assertRaises(ValueError):
            clone_app_rules(plist_path=self.test_plist, from_app="Chrome", to_app="")
        with self.assertRaises(ValueError):
            clone_app_rules(plist_path=self.test_plist, from_app="NonExistentSourceApp12345", to_app="TargetApp")

    def test_add_and_update_trackpad_rule(self):
        # 1. Add new trackpad gesture rule
        res = add_or_update_rule(
            plist_path=self.test_plist,
            app_name="All Applications",
            category="trackpad",
            key_or_gesture="4Finger_Swipe_Right",
            action_type="Shortcut Keys",
            action_value="⇧⌘W",
            enable=True,
            note="Global voice record",
            reload_bab=False
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["operation"], "added")
        self.assertEqual(res["category"], "ruleOfTrackPad")
        self.assertEqual(res["trigger"], "4Finger_Swipe_Right")

        data = load_plist(self.test_plist)
        tp_app = next(item for item in data["ruleOfTrackPad"] if item["AppName"] == "All Applications")
        self.assertEqual(len(tp_app["All Rules"]), 1)
        r = tp_app["All Rules"][0]
        self.assertEqual(r["Gesture"], "4Finger_Swipe_Right")
        self.assertEqual(r["Action"]["ActionType"], "Shortcut Keys")
        self.assertEqual(r["Action"]["Action"]["ShortcutName"], "⇧⌘W")
        self.assertEqual(r["Enable"], 1)

        # 2. Update existing trackpad gesture rule
        res_upd = add_or_update_rule(
            plist_path=self.test_plist,
            app_name="All Applications",
            category="trackpad",
            key_or_gesture="4Finger_Swipe_Right",
            action_type="Preset",
            action_value="BetterAndBetter Preferences",
            enable=False,
            note="Changed to preferences",
            reload_bab=False
        )
        self.assertEqual(res_upd["operation"], "updated")
        self.assertEqual(res_upd["action_type"], "Preset")

        data2 = load_plist(self.test_plist)
        tp_app2 = next(item for item in data2["ruleOfTrackPad"] if item["AppName"] == "All Applications")
        self.assertEqual(len(tp_app2["All Rules"]), 1)
        self.assertEqual(tp_app2["All Rules"][0]["Action"]["Action"], "BetterAndBetter Preferences")
        self.assertEqual(tp_app2["All Rules"][0]["Enable"], 0)

        # 3. Toggle trackpad rule
        res_tog = toggle_rule(
            plist_path=self.test_plist,
            app_name="All Applications",
            category="trackpad",
            key_or_index="4Finger_Swipe_Right",
            enable=True,
            reload_bab=False
        )
        self.assertTrue(res_tog["new_enable"])

        # 4. Remove trackpad rule
        res_rm = remove_rule(
            plist_path=self.test_plist,
            app_name="All Applications",
            category="trackpad",
            key_or_index="4Finger_Swipe_Right",
            reload_bab=False
        )
        self.assertEqual(res_rm["status"], "success")
        data3 = load_plist(self.test_plist)
        tp_app3 = next(item for item in data3["ruleOfTrackPad"] if item["AppName"] == "All Applications")
        self.assertEqual(len(tp_app3["All Rules"]), 0)

    def test_add_normalmouse_and_hotcorners_rule(self):
        # Normal mouse
        res_mouse = add_or_update_rule(
            plist_path=self.test_plist,
            app_name="com.apple.finder",
            category="normalmouse",
            key_or_gesture="ClickOf4Key",
            action_type="Preset",
            action_value="Back",
            enable=True,
            reload_bab=False
        )
        self.assertEqual(res_mouse["category"], "ruleOfNormalMouse")
        self.assertEqual(res_mouse["operation"], "added")

        # Hot corners
        res_hc = add_or_update_rule(
            plist_path=self.test_plist,
            app_name="All Applications",
            category="hotcorners",
            key_or_gesture="LeftMouse Click at TopLeft Corner",
            action_type="Preset",
            action_value="LockScreen",
            enable=True,
            reload_bab=False
        )
        self.assertEqual(res_hc["category"], "ruleOfHotCorners")

        data = load_plist(self.test_plist)
        hc_app = next(item for item in data["ruleOfHotCorners"] if item["AppName"] == "All Applications")
        self.assertEqual(hc_app["All Rules"][0]["Gesture"], "LeftMouse Click at TopLeft Corner")

    def test_add_open_action_rule(self):
        res_open = add_or_update_rule(
            plist_path=self.test_plist,
            app_name="All Applications",
            category="keyboard",
            key_or_gesture="⇧⌘G",
            action_type="Open...",
            action_value="https://google.com",
            enable=True,
            reload_bab=False
        )
        self.assertEqual(res_open["action_type"], "Open...")

        data = load_plist(self.test_plist)
        kb_app = next(item for item in data["ruleOfKeyboard"] if item["AppName"] == "All Applications")
        r = next(item for item in kb_app["All Rules"] if item.get("Action", {}).get("Action") == "Open...")
        self.assertEqual(r["Action"]["OpenArr"], ["https://google.com"])

    def test_add_rule_validation_errors(self):
        # Invalid category
        with self.assertRaises(ValueError):
            add_or_update_rule(
                plist_path=self.test_plist,
                category="invalid_category",
                key_or_gesture="⌘A",
                reload_bab=False
            )
        # Empty gesture for trackpad
        with self.assertRaises(ValueError):
            add_or_update_rule(
                plist_path=self.test_plist,
                category="trackpad",
                key_or_gesture="",
                reload_bab=False
            )
        # Invalid keyboard shortcut
        with self.assertRaises(ValueError):
            add_or_update_rule(
                plist_path=self.test_plist,
                category="keyboard",
                key_or_gesture="not_a_shortcut_xyz",
                reload_bab=False
            )

    def test_export_and_import_app_rules(self):
        # First add a rule pointing to the sample AppleScript
        add_or_update_rule(
            plist_path=self.test_plist,
            app_name="com.google.Chrome",
            category="keyboard",
            key_or_gesture="⇧⌘U",
            action_type="AppleScript",
            action_value="Original Script",
            enable=True,
            reload_bab=False
        )

        # Also add a trackpad rule with raw binary bytes in Data to verify bytes roundtrip
        raw_bytes = b"\x00\x01\x02\x03\xff\xfe\xfd"
        data_before = load_plist(self.test_plist)
        tp_container = next((item for item in data_before.setdefault("ruleOfTrackPad", []) if item["AppName"] == "com.google.Chrome"), None)
        if not tp_container:
            tp_container = {"AppName": "com.google.Chrome", "All Rules": []}
            data_before["ruleOfTrackPad"].append(tp_container)
        tp_container["All Rules"].append({
            "Gesture": "Custom_Drawing_Gesture",
            "Data": raw_bytes,
            "Action": {"ActionType": "Preset", "Action": "Center"},
            "Enable": 1
        })
        with open(self.test_plist, "wb") as f:
            plistlib.dump(data_before, f)

        export_path = os.path.join(self.tmp_dir.name, "chrome_export.json")
        exp = export_app_rules(
            plist_path=self.test_plist,
            app_name="com.google.Chrome",
            output_path=export_path
        )
        self.assertEqual(exp["app"], "com.google.Chrome")
        self.assertGreaterEqual(exp["total_rules"], 2)
        self.assertEqual(len(exp["referenced_scripts"]), 1)
        self.assertTrue(os.path.exists(export_path))

        # Import into Ego Browser
        imp = import_app_rules(
            plist_path=self.test_plist,
            app_name="com.citrolabs.ego.lite",
            input_file_or_data=export_path,
            overwrite=False,
            reload_bab=False
        )
        self.assertEqual(imp["status"], "success")
        self.assertEqual(imp["added_count"], 2)

        data = load_plist(self.test_plist)
        ego_app = next(item for item in data["ruleOfKeyboard"] if item["AppName"] == "com.citrolabs.ego.lite")
        self.assertEqual(len(ego_app["All Rules"]), 1)
        self.assertEqual(ego_app["All Rules"][0]["Action"]["ActionType"], "AppleScript")

        ego_tp = next(item for item in data["ruleOfTrackPad"] if item["AppName"] == "com.citrolabs.ego.lite")
        self.assertEqual(len(ego_tp["All Rules"]), 1)
        self.assertEqual(ego_tp["All Rules"][0]["Data"], raw_bytes)



if __name__ == "__main__":
    unittest.main()

"""
Unit tests for bab_core.doctor
"""

import os
import plistlib
import tempfile
import unittest

from bab_core.doctor import (
    clean_orphaned_rules,
    run_doctor,
)
from bab_core.plist_manager import load_plist


class TestDoctor(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_live = os.path.join(self.tmp_dir.name, "live.plist")
        self.test_git = os.path.join(self.tmp_dir.name, "git.plist")

        self.healthy_data = {
            "ruleOfKeyboard": [
                {
                    "AppName": "All Applications",
                    "All Rules": [
                        {
                            "Gesture": {"keyCode": 11, "modifierFlags": 1048576},
                            "Action": {"ActionType": "Preset", "Action": "Center"},
                            "Enable": 1,
                            "Note": "Valid rule",
                        }
                    ]
                }
            ],
            "ruleOfAppleScript": [
                {
                    "Id": "VALID-UUID-1",
                    "Name": "Valid Script",
                    "AppleScript": "display dialog \"Hello\"",
                    "Edited": False,
                }
            ],
            "ruleOfTrackPad": [],
            "ruleOfMagicMouse": [],
            "ruleOfNormalMouse": [],
            "ruleOfHotCorners": [],
        }

        with open(self.test_live, "wb") as f:
            plistlib.dump(self.healthy_data, f)
        with open(self.test_git, "wb") as f:
            plistlib.dump(self.healthy_data, f)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_doctor_healthy_structure(self):
        report = run_doctor(live_path=self.test_live, git_path=self.test_git)
        # Process/Daemon checks might generate warnings in sandbox/CI if not installed,
        # but PLIST, SYNC, and SCRIPTS must have 0 errors/warnings on healthy structure.
        script_findings = [f for f in report.findings if f.category in ("PLIST", "SCRIPTS")]
        self.assertEqual(len(script_findings), 0)

    def test_doctor_missing_plist(self):
        missing_path = os.path.join(self.tmp_dir.name, "nonexistent.plist")
        report = run_doctor(live_path=missing_path, git_path=self.test_git)
        self.assertEqual(report.verdict, "CRITICAL")
        self.assertTrue(any(f.category == "PLIST" and f.severity == "CRITICAL" for f in report.findings))

    def test_doctor_corrupt_empty_plist(self):
        empty_path = os.path.join(self.tmp_dir.name, "empty.plist")
        with open(empty_path, "wb") as f:
            pass  # 0 bytes
        report = run_doctor(live_path=empty_path, git_path=self.test_git)
        self.assertEqual(report.verdict, "CRITICAL")
        self.assertTrue(any("损坏" in f.message for f in report.findings))

    def test_doctor_orphaned_script_detection(self):
        corrupt_data = {
            "ruleOfKeyboard": [
                {
                    "AppName": "All Applications",
                    "All Rules": [
                        {
                            "Gesture": {"keyCode": 15, "modifierFlags": 1048576},
                            "Action": {"ActionType": "AppleScript", "Action": "NON-EXISTENT-SCRIPT-UUID"},
                            "Enable": 1,
                        }
                    ]
                }
            ],
            "ruleOfAppleScript": [],
            "ruleOfTrackPad": [],
            "ruleOfMagicMouse": [],
            "ruleOfNormalMouse": [],
            "ruleOfHotCorners": [],
        }
        with open(self.test_live, "wb") as f:
            plistlib.dump(corrupt_data, f)

        report = run_doctor(live_path=self.test_live, git_path=self.test_git)
        orphan_finding = next((f for f in report.findings if f.category == "SCRIPTS"), None)
        self.assertIsNotNone(orphan_finding)
        self.assertEqual(orphan_finding.severity, "WARNING")
        self.assertIn("Ghost Triggers", orphan_finding.message)

    def test_doctor_clean_orphaned_rules_disable_and_remove(self):
        data = {
            "ruleOfKeyboard": [
                {
                    "AppName": "All Applications",
                    "All Rules": [
                        {
                            "Gesture": {"keyCode": 15, "modifierFlags": 1048576},
                            "Action": {"ActionType": "AppleScript", "Action": "DEAD-UUID-1"},
                            "Enable": 1,
                        }
                    ]
                }
            ],
            "ruleOfAppleScript": [],
            "ruleOfTrackPad": [],
            "ruleOfMagicMouse": [],
            "ruleOfNormalMouse": [],
            "ruleOfHotCorners": [],
        }
        with open(self.test_live, "wb") as f:
            plistlib.dump(data, f)

        # 1. Clean with disable_only=True
        res_dis = clean_orphaned_rules(plist_path=self.test_live, disable_only=True, reload_bab=False)
        self.assertEqual(res_dis["modified_count"], 1)
        self.assertEqual(res_dis["operation"], "disabled")
        loaded1 = load_plist(self.test_live)
        self.assertEqual(loaded1["ruleOfKeyboard"][0]["All Rules"][0]["Enable"], 0)

        # 2. Clean with disable_only=False (remove)
        res_rm = clean_orphaned_rules(plist_path=self.test_live, disable_only=False, reload_bab=False)
        self.assertEqual(res_rm["modified_count"], 1)
        self.assertEqual(res_rm["operation"], "removed")
        loaded2 = load_plist(self.test_live)
        self.assertEqual(len(loaded2["ruleOfKeyboard"][0]["All Rules"]), 0)


if __name__ == "__main__":
    unittest.main()

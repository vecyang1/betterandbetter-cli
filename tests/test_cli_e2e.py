"""
E2E tests for the bab CLI executable
"""

import json
import os
import subprocess
import unittest

CLI_PATH = os.path.expanduser("~/.local/bin/bab")


class TestCLIE2E(unittest.TestCase):

    def test_cli_exists_and_executable(self):
        self.assertTrue(os.path.exists(CLI_PATH))
        self.assertTrue(os.access(CLI_PATH, os.X_OK))

    def test_cli_status(self):
        res = subprocess.run([CLI_PATH, "status", "--json"], capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        self.assertIn("app_version", data)
        self.assertIn("category_stats", data)
        self.assertEqual(data["app_version"], "2.7.9")

    def test_cli_inspect_apps(self):
        res = subprocess.run([CLI_PATH, "inspect", "apps", "--json"], capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        self.assertTrue(isinstance(data, list))
        self.assertTrue(len(data) > 0)
        app_names = [a["app_name"] for a in data]
        self.assertIn("All Applications", app_names)

    def test_cli_inspect_keyboard(self):
        res = subprocess.run(
            [CLI_PATH, "inspect", "keyboard", "--app", "obsidian", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(res.stdout)
        self.assertTrue(isinstance(data, list))
        self.assertTrue(len(data) >= 5)

    def test_cli_explain_shortcut(self):
        res = subprocess.run(
            [CLI_PATH, "explain", "⌘B", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(res.stdout)
        self.assertEqual(data["query_intent"], "SHORTCUT")
        self.assertTrue(len(data["matched_rules"]) >= 1)

    def test_cli_explain_app(self):
        res = subprocess.run(
            [CLI_PATH, "explain", "Obsidian", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(res.stdout)
        self.assertEqual(data["query_intent"], "APP")
        self.assertTrue(len(data["matched_rules"]) >= 1)

    def test_cli_diff(self):
        res = subprocess.run(
            [CLI_PATH, "diff", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(res.stdout)
        self.assertIn("is_synced", data)
        self.assertIn("categories", data)

    def test_cli_sync_dry_run(self):
        res = subprocess.run(
            [CLI_PATH, "sync", "--to-git", "--dry-run", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "success")
        self.assertTrue(data["dry_run"])

    def test_cli_explain_path_finder_zero_false_drift(self):
        # Path Finder has duplicate gestures and empty gesture slots; must report 0 false drift
        res = subprocess.run(
            [CLI_PATH, "explain", "Path Finder", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(res.stdout)
        self.assertEqual(data["query_intent"], "APP")
        self.assertGreaterEqual(len(data["matched_rules"]), 20)
        # Verify no false MODIFIED_ACTION on identical rules
        for r in data["matched_rules"]:
            self.assertEqual(r["drift_status"], "SYNCHRONIZED", f"Rule {r['trigger']} unexpectedly drifted: {r['drift_desc']}")

    def test_cli_set_validation_errors(self):
        # Missing key/index for remove-rule
        res_rm = subprocess.run(
            [CLI_PATH, "set", "remove-rule", "--app", "All Applications"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res_rm.returncode, 0)
        self.assertIn("请通过 --key 或 --index 指定要删除的规则", res_rm.stderr)

        # Missing name/id for remove-script
        res_rms = subprocess.run(
            [CLI_PATH, "set", "remove-script"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res_rms.returncode, 0)
        self.assertIn("请通过 --name 或 --id 指定要删除的 AppleScript", res_rms.stderr)


if __name__ == "__main__":
    unittest.main()

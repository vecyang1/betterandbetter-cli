"""
Unit and Integration Tests for BetterAndBetter Daemon (LaunchAgent) Manager.
Tests daemon status, plist dictionary generation, receipt parsing, and CLI observability.
"""

import json
import os
import plistlib
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from bab_core.constants import LAUNCHD_LABEL
from bab_core.daemon import (
    generate_launchd_plist_dict,
    get_daemon_status,
    install_daemon,
    uninstall_daemon,
)


class TestDaemonManager(unittest.TestCase):

    def test_generate_launchd_plist_dict(self):
        """Test default LaunchAgent plist dictionary generation."""
        plist = generate_launchd_plist_dict("/tmp/custom-backup.sh")
        self.assertEqual(plist["Label"], LAUNCHD_LABEL)
        self.assertEqual(plist["ProgramArguments"], ["/bin/bash", "/tmp/custom-backup.sh"])
        self.assertIn("WatchPaths", plist)
        self.assertGreaterEqual(len(plist["WatchPaths"]), 2)
        self.assertEqual(plist["ThrottleInterval"], 30)
        self.assertEqual(plist["StartCalendarInterval"]["Hour"], 11)
        self.assertEqual(plist["StartCalendarInterval"]["Minute"], 0)

    @patch("bab_core.daemon.os.path.exists")
    @patch("bab_core.daemon.subprocess.run")
    def test_get_daemon_status_loaded(self, mock_run, mock_exists):
        """Test get_daemon_status when daemon is loaded and running."""
        mock_exists.return_value = True

        mock_res = MagicMock()
        mock_res.stdout = f"12345\t0\t{LAUNCHD_LABEL}\n"
        mock_run.return_value = mock_res

        with tempfile.NamedTemporaryFile(suffix=".plist", delete=False) as f_plist:
            plist_path = f_plist.name
            plist_data = {
                "Label": LAUNCHD_LABEL,
                "WatchPaths": ["/tmp/test.plist"],
                "ThrottleInterval": 30,
                "StartCalendarInterval": {"Hour": 11, "Minute": 0},
                "ProgramArguments": ["/bin/bash", "/tmp/test.sh"],
            }
            plistlib.dump(plist_data, f_plist)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as f_receipt:
            receipt_path = f_receipt.name
            receipt_data = {
                "schema_version": 1,
                "lane": "betterandbetter-backup",
                "status": "success",
                "completed_at": "2026-09-26T00:00:00Z",
                "commit": "abcdef123",
                "message": "BetterAndBetter backup pushed",
            }
            json.dump(receipt_data, f_receipt)

        try:
            with patch("bab_core.daemon.LAUNCHD_PLIST_PATH", plist_path), \
                 patch("bab_core.daemon.BACKUP_RECEIPT_PATH", receipt_path), \
                 patch("bab_core.daemon.BACKUP_LOG_PATH", "/nonexistent/log"):
                status = get_daemon_status()
                self.assertTrue(status["installed"])
                self.assertTrue(status["plist_valid"])
                self.assertTrue(status["loaded"])
                self.assertEqual(status["pid"], 12345)
                self.assertEqual(status["last_exit_code"], 0)
                self.assertEqual(len(status["watch_paths"]), 1)
                self.assertIsNotNone(status["receipt"])
                self.assertEqual(status["receipt"]["status"], "success")
        finally:
            if os.path.exists(plist_path):
                os.remove(plist_path)
            if os.path.exists(receipt_path):
                os.remove(receipt_path)

    @patch("bab_core.daemon.os.chmod")
    @patch("bab_core.daemon.get_daemon_status")
    @patch("bab_core.daemon.os.path.exists")
    def test_install_daemon_already_installed_without_force(self, mock_exists, mock_st, mock_chmod):
        """Test install_daemon prevents re-install when already loaded without force."""
        mock_exists.return_value = True
        mock_st.return_value = {"loaded": True, "label": LAUNCHD_LABEL}

        res = install_daemon(backup_script="/tmp/test.sh", force=False)
        self.assertEqual(res["status"], "already_installed")
        self.assertIn("已处于加载激活状态", res["message"])


if __name__ == "__main__":
    unittest.main()

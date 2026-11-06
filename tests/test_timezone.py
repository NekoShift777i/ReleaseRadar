import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config_validation import ConfigError, validate_config
from status import format_last_check, get_status_messages


class TimezoneTests(unittest.TestCase):
    def test_kamchatka_conversion(self):
        self.assertEqual(
            format_last_check("2026-11-06T04:49:06+00:00", "Asia/Kamchatka"),
            "06.11.2026 16:49:06 (Asia/Kamchatka)",
        )

    def test_naive_database_timestamp_is_utc(self):
        self.assertEqual(
            format_last_check("2026-11-06T04:49:06", "Asia/Kamchatka"),
            "06.11.2026 16:49:06 (Asia/Kamchatka)",
        )

    def test_default_timezone_utc(self):
        self.assertEqual(format_last_check("2026-11-06T04:49:06+00:00"),
                         "06.11.2026 04:49:06 (UTC)")

    def test_invalid_timezone_rejected(self):
        with self.assertRaisesRegex(ConfigError, "timezone"):
            validate_config({"software": [], "timezone": "Mars/Olympus"})

    def test_timezone_default_is_accepted(self):
        self.assertEqual(validate_config({"software": []}), {"software": []})

    def test_status_uses_configured_timezone(self):
        config = {"timezone": "Asia/Kamchatka", "software": [{
            "id": "frigate", "name": "Frigate NVR", "channel": "stable",
            "current_version": "v0.18.2", "enabled": True,
        }]}
        state = {"current_version": "v0.18.2", "latest_version": "v0.18.2",
                 "last_checked_at": "2026-11-06T04:49:06+00:00"}
        with patch("status.get_software_state", return_value=state), \
             patch("status.get_check_interval", return_value=60):
            message = "\n".join(get_status_messages(config))
        self.assertIn("06.11.2026 16:49:06 (Asia/Kamchatka)", message)

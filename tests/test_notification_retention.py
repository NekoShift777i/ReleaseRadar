import unittest
from datetime import timedelta

from config_validation import (
    ConfigError,
    parse_notification_button_retention,
)


class NotificationRetentionTests(unittest.TestCase):
    def test_valid_durations(self):
        cases = {
            "336h": 14,
            "2w": 14,
            "14d": 14,
            "30d": 30,
            "120d": 120,
        }

        for value, days in cases.items():
            with self.subTest(value=value):
                self.assertEqual(
                    parse_notification_button_retention(value),
                    timedelta(days=days),
                )

    def test_invalid_durations(self):
        values = [
            "7d",
            "18w",
            "335h",
            "2881h",
            "30",
            "30D",
            "0d",
            "-14d",
            " 30d",
            "30d ",
            "",
            None,
            30,
            True,
        ]

        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(ConfigError):
                    parse_notification_button_retention(value)


if __name__ == "__main__":
    unittest.main()

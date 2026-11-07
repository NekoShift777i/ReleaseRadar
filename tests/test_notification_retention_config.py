import unittest

from config_validation import ConfigError, validate_config


class NotificationRetentionConfigTests(unittest.TestCase):
    def test_valid_retention_values(self):
        for value in ("14d", "2w", "336h", "30d", "120d"):
            with self.subTest(value=value):
                config = {
                    "software": [],
                    "notification_button_retention": value,
                }

                result = validate_config(config)
                self.assertEqual(
                    result["notification_button_retention"],
                    value,
                )

    def test_invalid_retention_values(self):
        for value in ("7d", "18w", "30", "", None, 30, True):
            with self.subTest(value=value):
                config = {
                    "software": [],
                    "notification_button_retention": value,
                }

                with self.assertRaises(ConfigError) as context:
                    validate_config(config)

                self.assertIn(
                    "notification_button_retention",
                    str(context.exception),
                )

    def test_default_retention(self):
        config = {"software": []}

        result = validate_config(config)

        self.assertNotIn("notification_button_retention", result)


if __name__ == "__main__":
    unittest.main()

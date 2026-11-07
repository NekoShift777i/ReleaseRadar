import unittest

from config_validation import ConfigError, validate_config


class ParallelConfigTests(unittest.TestCase):
    def test_default_is_four_without_mutating_config(self):
        config = {"software": []}
        self.assertEqual(validate_config(config).get("max_parallel_checks", 4), 4)
        self.assertEqual(config, {"software": []})

    def test_four_is_accepted(self):
        self.assertEqual(validate_config({"software": [], "max_parallel_checks": 4})["max_parallel_checks"], 4)

    def test_other_positive_integer_is_accepted(self):
        self.assertEqual(validate_config({"software": [], "max_parallel_checks": 2})["max_parallel_checks"], 2)

    def test_invalid_values_are_rejected(self):
        for value in (0, -1, True, False, 1.5, "4", None, [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ConfigError, "max_parallel_checks"):
                validate_config({"software": [], "max_parallel_checks": value})

    def test_upper_bound_is_accepted(self):
        self.assertEqual(validate_config({"software": [], "max_parallel_checks": 16})["max_parallel_checks"], 16)

    def test_excessive_limit_is_rejected(self):
        for value in (17, 100, 10000):
            with self.subTest(value=value), self.assertRaisesRegex(ConfigError, "от 1 до 16"):
                validate_config({"software": [], "max_parallel_checks": value})

    def test_unknown_fields_still_rejected(self):
        with self.assertRaisesRegex(ConfigError, "неизвестное поле"):
            validate_config({"software": [], "max_parallel_checks": 4, "unexpected": 1})


if __name__ == "__main__":
    unittest.main()

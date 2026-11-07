
import unittest

from version_comparison import VersionComparison, compare_versions
from update_logic import is_newer_version, should_notify


class VersionComparisonTests(unittest.TestCase):

    def test_standard_versions(self):
        self.assertEqual(
            compare_versions("1.2.3", "1.2.4"),
            VersionComparison.NEWER,
        )
        self.assertEqual(
            compare_versions("1.2.4", "1.2.3"),
            VersionComparison.NOT_NEWER,
        )
        self.assertEqual(
            compare_versions("1.2.3", "1.2.3"),
            VersionComparison.NOT_NEWER,
        )

    def test_version_prefix(self):
        self.assertEqual(
            compare_versions("v1.2.3", "v1.2.4"),
            VersionComparison.NEWER,
        )

    def test_prereleases(self):
        self.assertEqual(
            compare_versions("2.0rc1", "2.0"),
            VersionComparison.NEWER,
        )
        self.assertEqual(
            compare_versions("2.0", "2.1rc1"),
            VersionComparison.NEWER,
        )
        self.assertEqual(
            compare_versions("2.0", "2.0rc1"),
            VersionComparison.NOT_NEWER,
        )

    def test_nonstandard_versions(self):
        self.assertEqual(
            compare_versions("release-blue", "release-green"),
            VersionComparison.UNKNOWN,
        )
        self.assertEqual(
            compare_versions("release-blue", "release-blue"),
            VersionComparison.NOT_NEWER,
        )

    def test_invalid_values(self):
        self.assertEqual(
            compare_versions("", "2.0"),
            VersionComparison.UNKNOWN,
        )
        self.assertEqual(
            compare_versions("1.0", None),
            VersionComparison.UNKNOWN,
        )

    def test_no_lexicographical_fallback(self):
        self.assertEqual(
            compare_versions("build-9", "build-10"),
            VersionComparison.UNKNOWN,
        )

    
    def test_update_logic_integration(self):
        self.assertTrue(is_newer_version("1.2.3", "1.2.4"))
        self.assertFalse(is_newer_version("1.2.4", "1.2.3"))
        self.assertFalse(is_newer_version("build-9", "build-10"))

    def test_unknown_version_does_not_notify(self):
        self.assertFalse(
            should_notify("release-blue", "release-green", None)
        )
        self.assertTrue(
            should_notify("1.2.3", "1.2.4", None)
        )
        self.assertFalse(
            should_notify("1.2.3", "1.2.4", "1.2.4")
        )

    def test_unknown_versions_never_trigger_updates(self):
        cases = [
            ("build-9", "build-10"),
            ("release-blue", "release-green"),
            ("2026-custom", "2027-custom"),
            ("1.0", "unknown-release"),
        ]

        for current, latest in cases:
            with self.subTest(current=current, latest=latest):
                self.assertEqual(
                    compare_versions(current, latest),
                    VersionComparison.UNKNOWN,
                )
                self.assertFalse(
                    is_newer_version(current, latest)
                )
                self.assertFalse(
                    should_notify(current, latest, None)
                )


if __name__ == "__main__":
    unittest.main()

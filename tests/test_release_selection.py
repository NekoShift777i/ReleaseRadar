
import unittest

from providers.base import Release
from providers.release_selection import select_latest_release


class ReleaseSelectionTests(unittest.TestCase):

    def test_select_highest_version(self):
        releases = [
            Release("v1.9.0", "https://example.com/1.9", False),
            Release("v2.0.0", "https://example.com/2.0", False),
            Release("v1.8.0", "https://example.com/1.8", False),
        ]

        result = select_latest_release(releases)

        self.assertEqual(result.version, "v2.0.0")

    def test_exclude_prereleases(self):
        releases = [
            Release("v3.0rc1", "https://example.com/rc", True),
            Release("v2.0", "https://example.com/2", False),
        ]

        result = select_latest_release(releases)

        self.assertEqual(result.version, "v2.0")

    def test_include_prereleases(self):
        releases = [
            Release("v3.0rc1", "https://example.com/rc", True),
            Release("v2.0", "https://example.com/2", False),
        ]

        result = select_latest_release(
            releases,
            include_prerelease=True,
        )

        self.assertEqual(result.version, "v3.0rc1")

    def test_published_order(self):
        releases = [
            Release("v1.5", "https://example.com/new", False),
            Release("v2.0", "https://example.com/old", False),
        ]

        result = select_latest_release(
            releases,
            selection_mode="published",
        )

        self.assertEqual(result.version, "v1.5")

    def test_nonstandard_versions(self):
        releases = [
            Release("release-blue", "https://example.com/a", False),
            Release("release-green", "https://example.com/b", False),
        ]

        with self.assertLogs(
            "providers.release_selection",
            level="WARNING",
        ):
            result = select_latest_release(releases)

        self.assertEqual(result.version, "release-blue")

    def test_no_candidates(self):
        with self.assertRaises(ValueError):
            select_latest_release([])

    def test_invalid_selection_mode(self):
        with self.assertRaises(ValueError):
            select_latest_release(
                [Release("1.0", "https://example.com", False)],
                selection_mode="unknown",
            )


if __name__ == "__main__":
    unittest.main()

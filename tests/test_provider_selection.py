
import unittest
from unittest.mock import MagicMock, patch

from providers.base import Release
from providers.github import get_latest_release as github_latest
from providers.gitlab import get_latest_release as gitlab_latest

from update_logic import is_newer_version, should_notify


class ProviderSelectionTests(unittest.TestCase):

    @patch("providers.github.select_latest_release")
    @patch("providers.github.httpx.Client")
    def test_github_uses_shared_selection(self, client_class, select):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = [
            {
                "tag_name": "v1.0",
                "html_url": "https://example.com/1",
                "prerelease": False,
                "draft": False,
            }
        ]

        client_class.return_value.__enter__.return_value.get.return_value = response
        select.return_value = Release("v1.0", "https://example.com/1", False)

        result = github_latest("owner/project")

        self.assertEqual(result.version, "v1.0")
        select.assert_called_once()
        self.assertEqual(
            select.call_args.kwargs["selection_mode"],
            "version",
        )

    @patch("providers.gitlab.select_latest_release")
    @patch("providers.gitlab.httpx.get")
    def test_gitlab_uses_shared_selection(self, get, select):
        response = MagicMock()
        response.json.return_value = [
            {
                "tag_name": "v1.0",
                "released_at": "2025-01-01T00:00:00Z",
                "_links": {"self": "https://example.com/1"},
            }
        ]
        response.links = {}
        response.headers = {}
        get.return_value = response

        select.return_value = Release("v1.0", "https://example.com/1", False)

        result = gitlab_latest("owner/project")

        self.assertEqual(result.version, "v1.0")
        select.assert_called_once()
        self.assertEqual(
            select.call_args.kwargs["selection_mode"],
            "published",
        )

    
    @patch("providers.github.httpx.Client")
    def test_github_pagination(self, client_class):
        first_page = MagicMock()
        first_page.status_code = 200
        first_page.json.return_value = [
            {
                "tag_name": f"v1.0.{i}",
                "html_url": f"https://example.com/{i}",
                "prerelease": False,
                "draft": False,
            }
            for i in range(100)
        ]

        second_page = MagicMock()
        second_page.status_code = 200
        second_page.json.return_value = [
            {
                "tag_name": "v2.0.0",
                "html_url": "https://example.com/2",
                "prerelease": False,
                "draft": False,
            }
        ]

        client = client_class.return_value.__enter__.return_value
        client.get.side_effect = [first_page, second_page]

        result = github_latest("owner/project")

        self.assertEqual(result.version, "v2.0.0")
        self.assertEqual(client.get.call_count, 2)
        self.assertEqual(
            client.get.call_args.kwargs["params"]["page"],
            2,
        )

    
    @patch("providers.gitlab.httpx.get")
    def test_gitlab_pagination(self, get):
        first_page = MagicMock()
        first_page.json.return_value = [
            {
                "tag_name": "v3.0-rc1",
                "released_at": "2025-01-02T00:00:00Z",
                "_links": {"self": "https://example.com/rc"},
            }
        ]
        first_page.links = {}
        first_page.headers = {"x-next-page": "2"}

        second_page = MagicMock()
        second_page.json.return_value = [
            {
                "tag_name": "v2.0",
                "released_at": "2025-01-01T00:00:00Z",
                "_links": {"self": "https://example.com/2"},
            }
        ]
        second_page.links = {}
        second_page.headers = {}

        get.side_effect = [first_page, second_page]

        result = gitlab_latest(
            "owner/project",
            include_prerelease=False,
        )

        self.assertEqual(result.version, "v2.0")
        self.assertEqual(get.call_count, 2)
        self.assertEqual(
            get.call_args.kwargs["params"]["page"],
            2,
        )

    
    @patch("providers.github.httpx.Client")
    def test_github_prerelease_filter(self, client_class):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = [
            {
                "tag_name": "v3.0rc1",
                "html_url": "https://example.com/rc",
                "prerelease": True,
                "draft": False,
            },
            {
                "tag_name": "v2.0",
                "html_url": "https://example.com/stable",
                "prerelease": False,
                "draft": False,
            },
        ]

        client = client_class.return_value.__enter__.return_value
        client.get.return_value = response

        stable = github_latest(
            "owner/project",
            include_prerelease=False,
        )

        self.assertEqual(stable.version, "v2.0")

        prerelease = github_latest(
            "owner/project",
            include_prerelease=True,
        )

        self.assertEqual(prerelease.version, "v3.0rc1")

    
    def test_nonstandard_release_does_not_trigger_notification(self):
        releases = [
            Release(
                "release-green",
                "https://example.com/green",
                False,
            ),
            Release(
                "release-blue",
                "https://example.com/blue",
                False,
            ),
        ]

        from providers.release_selection import select_latest_release

        with self.assertLogs(
            "providers.release_selection",
            level="WARNING",
        ):
            selected = select_latest_release(releases)

        self.assertEqual(selected.version, "release-green")

        self.assertFalse(
            is_newer_version("release-blue", selected.version)
        )

        self.assertFalse(
            should_notify("release-blue", selected.version, None)
        )




if __name__ == "__main__":
    unittest.main()

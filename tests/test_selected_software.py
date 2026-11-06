import unittest
from unittest.mock import patch

from main import check_updates


class SelectedSoftwareCheckTests(unittest.TestCase):
    def setUp(self):
        self.config = {"software": [
            {"id": "first", "name": "First", "enabled": True, "current_version": "v1"},
            {"id": "second", "name": "Second", "enabled": True, "current_version": "v1"},
        ]}

    def test_selected_software_does_not_touch_other_entries(self):
        with patch("main.get_or_create_software_state", return_value={"current_version": "v1"}) as get_state, \
             patch("main.get_latest_release") as get_release, \
             patch("main.get_software_state", return_value={"current_version": "v1", "last_notified_version": None}), \
             patch("main.update_software_check") as update_check:
            get_release.return_value.version = "v1"
            get_release.return_value.url = "https://example.invalid/release"
            results = check_updates(self.config, software_id="second")
        self.assertEqual([result.software_id for result in results], ["second"])
        get_state.assert_called_once_with("second", "v1")
        get_release.assert_called_once()
        update_check.assert_called_once()

    def test_unknown_selection_does_not_check_anything(self):
        with patch("main.get_or_create_software_state") as get_state, \
             patch("main.get_latest_release") as get_release:
            results = check_updates(self.config, software_id="missing")
        self.assertEqual(results, [])
        get_state.assert_not_called()
        get_release.assert_not_called()

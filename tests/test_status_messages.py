import unittest
from unittest.mock import patch

from status import get_status_messages, split_status_blocks


class StatusMessageSplitTests(unittest.TestCase):
    def test_keeps_program_block_together_at_boundary(self):
        blocks = ["Отчёт", "A" * 25, "Frigate NVR (frigate)\nКанал: stable\nВерсия: v0.18.2"]
        messages = split_status_blocks(blocks, limit=55)
        self.assertEqual(messages, ["Отчёт\n\n" + "A" * 25, blocks[2]])

    def test_packs_multiple_programs_in_one_message(self):
        self.assertEqual(split_status_blocks(["Заголовок", "Программа A", "Программа B"]),
                         ["Заголовок\n\nПрограмма A\n\nПрограмма B"])

    def test_counts_emoji_as_two_utf16_units(self):
        self.assertEqual(split_status_blocks(["😀😀", "X"], limit=5), ["😀😀", "X"])

    def test_rejects_oversized_single_block(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            split_status_blocks(["A" * 11], limit=10)

    def test_status_keeps_each_program_intact(self):
        config = {"software": [{"id": "frigate", "name": "Frigate NVR", "channel": "stable",
                                "current_version": "v0.18.2", "enabled": True}]}
        with patch("status.get_software_state", return_value=None), \
             patch("status.get_check_interval", return_value=60):
            messages = get_status_messages(config)
        self.assertEqual(len(messages), 1)
        self.assertIn("Frigate NVR (frigate)\nКанал: stable", messages[0])

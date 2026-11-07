
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram_handlers import handle_skipped


class SkippedCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = SimpleNamespace(
            reply_text=AsyncMock(),
        )

        self.update = SimpleNamespace(
            effective_message=self.message,
        )

        self.context = SimpleNamespace(
            bot_data={
                "config": {
                    "software": [
                        {"id": "xray", "name": "Xray"},
                        {"id": "other", "name": "Другая программа"},
                    ],
                },
            },
        )

    async def test_empty_history(self):
        with (
            patch(
                "telegram_handlers.is_authorized",
                return_value=True,
            ),
            patch(
                "telegram_handlers.get_skipped_releases",
                return_value=[],
            ),
        ):
            await handle_skipped(self.update, self.context)

        self.message.reply_text.assert_awaited_once_with(
            "История пропущенных выпусков пуста.",
            parse_mode=None,
        )

    async def test_history_contains_release_details(self):
        releases = [
            {
                "software_id": "xray",
                "version": "v2.0",
                "reason": "Ожидание исправлений",
                "skipped_at": "2026-11-07 12:00:00",
            },
            {
                "software_id": "other",
                "version": "v3.0",
                "reason": "Не требуется",
                "skipped_at": "2026-11-06 10:00:00",
            },
        ]

        with (
            patch(
                "telegram_handlers.is_authorized",
                return_value=True,
            ),
            patch(
                "telegram_handlers.get_skipped_releases",
                return_value=releases,
            ),
        ):
            await handle_skipped(self.update, self.context)

        self.assertEqual(
            self.message.reply_text.await_count,
            2,
        )

        first_message = (
            self.message.reply_text.await_args_list[0].args[0]
        )

        self.assertIn("Xray", first_message)
        self.assertIn("v2.0", first_message)
        self.assertIn("Ожидание исправлений", first_message)
        self.assertIn(
            "Дата пропуска: 08.11.2026 00:00:00 (Камчатка)",
            first_message,
        )

        second_message = (
            self.message.reply_text.await_args_list[1].args[0]
        )

        self.assertIn("Другая программа", second_message)
        self.assertIn("v3.0", second_message)
        self.assertIn("Не требуется", second_message)

    async def test_unauthorized_user(self):
        with patch(
            "telegram_handlers.is_authorized",
            return_value=False,
        ):
            await handle_skipped(self.update, self.context)

        self.message.reply_text.assert_not_awaited()


    async def test_history_is_limited_to_twenty_releases(self):
        releases = [
            {
                "software_id": "xray",
                "version": f"v{i}",
                "reason": f"Причина {i}",
                "skipped_at": "2026-11-07 12:00:00",
            }
            for i in range(25)
        ]

        with (
            patch(
                "telegram_handlers.is_authorized",
                return_value=True,
            ),
            patch(
                "telegram_handlers.get_skipped_releases",
                return_value=releases,
            ),
        ):
            await handle_skipped(self.update, self.context)

        # 20 записей и одно итоговое сообщение.
        self.assertEqual(
            self.message.reply_text.await_count,
            21,
        )

        messages = [
            call.args[0]
            for call in self.message.reply_text.await_args_list
        ]

        # Первые 20 записей отображены.
        self.assertIn("Версия: v0", messages[0])
        self.assertIn("Версия: v19", messages[19])

        # Остальные записи не отправлены.
        self.assertFalse(
            any("Версия: v20\n" in text for text in messages)
        )

        # Пользователь видит общее количество.
        self.assertEqual(
            messages[-1],
            "Показаны последние 20 из 25 пропущенных выпусков.",
        )

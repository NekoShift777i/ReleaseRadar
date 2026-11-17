
import tempfile
import unittest
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from telegram.error import BadRequest

from telegram_handlers import handle_confirm_apply, handle_confirm_selection, CONFIRM_REQUEST_TTL

import database as db


class ConfirmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp.name) / "test.db"

        db.initialize_database()
        db.create_software_state("xray", "v1.0")
        db.update_software_check(
            "xray",
            "v2.0",
            "2026-11-07T00:00:00+00:00",
        )

    def tearDown(self):
        db.DATABASE_PATH = self.old_path
        self.temp.cleanup()

    def test_skipped_version_can_be_confirmed(self):
        self.assertTrue(
            db.skip_release("xray", "v2.0", "Отложено")
        )

        self.assertTrue(
            db.mark_version_updated("xray", "v2.0")
        )

        state = db.get_software_state("xray")

        self.assertEqual(state["current_version"], "v2.0")
        self.assertTrue(
            db.is_release_skipped("xray", "v2.0")
        )


class ConfirmHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_confirmation_is_rejected(self):
        token = "a" * 32

        query = SimpleNamespace(
            data=f"confirm_apply:v1:{token}",
            answer=AsyncMock(),
        )

        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=123456789),
        )

        requests = {
            token: {
                "software_id": "xray",
                "version": "v2.0",
                "created_at": time.time() - CONFIRM_REQUEST_TTL - 1,
            }
        }

        context = SimpleNamespace(
            user_data={"confirm_requests": requests},
        )

        with (
            patch("telegram_handlers.is_authorized", return_value=True),
            patch("telegram_handlers.mark_version_updated") as mark_updated,
            self.assertLogs("telegram_handlers", level="INFO") as captured_logs,
        ):
            await handle_confirm_apply(update, context)

        mark_updated.assert_not_called()
        self.assertNotIn(token, requests)

        query.answer.assert_awaited_once_with(
            "Срок подтверждения истёк. Откройте /confirm заново.",
            show_alert=True,
        )


    async def test_confirmation_cannot_be_reused(self):
        token = "b" * 32

        query = SimpleNamespace(
            data=f"confirm_apply:v1:{token}",
            answer=AsyncMock(),
        )

        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=123456789),
        )

        requests = {
            token: {
                "software_id": "xray",
                "version": "v2.0",
                "created_at": time.time(),
            }
        }

        context = SimpleNamespace(
            user_data={"confirm_requests": requests},
            bot_data={
                "config": {
                    "software": [
                        {
                            "id": "xray",
                            "name": "Xray",
                            "enabled": True,
                        }
                    ]
                }
            },
        )

        with (
            patch("telegram_handlers.is_authorized", return_value=True),
            patch(
                "telegram_handlers.get_software_state",
                return_value={
                    "current_version": "v1.0",
                    "latest_version": "v2.0",
                },
            ),
            patch(
                "telegram_handlers.mark_version_updated",
                return_value=True,
            ) as mark_updated,
            patch(
                "telegram_handlers.edit_callback_message",
                new_callable=AsyncMock,
            ),
        ):
            await handle_confirm_apply(update, context)
            await handle_confirm_apply(update, context)

        mark_updated.assert_called_once_with(
            "xray",
            "v2.0",
            source="telegram_confirm",
            actor_id=123456789,
        )
        self.assertNotIn(token, requests)

        self.assertEqual(query.answer.await_count, 2)

        self.assertEqual(
            query.answer.await_args_list[1].args[0],
            "Подтверждение недействительно. Откройте /confirm заново.",
        )

    
    async def test_cancel_invalidates_confirmation(self):
        token = "c" * 32

        query = SimpleNamespace(
            data="confirm_cancel",
            answer=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)

        context = SimpleNamespace(
            user_data={
                "confirm_selection_requests": {
                    "d" * 32: "xray",
                },
                "confirm_requests": {
                    token: {
                        "software_id": "xray",
                        "version": "v2.0",
                        "created_at": time.time(),
                    }
                },
            }
        )

        with (
            patch("telegram_handlers.is_authorized", return_value=True),
            patch(
                "telegram_handlers.edit_callback_message",
                new_callable=AsyncMock,
            ) as edit_message,
        ):
            await handle_confirm_selection(update, context)

        self.assertIn(
            "confirm_selection_requests",
            context.user_data,
        )
        self.assertIn(
            "confirm_requests",
            context.user_data,
        )
        self.assertIn(
            "d" * 32,
            context.user_data["confirm_selection_requests"],
        )
        self.assertIn(
            token,
            context.user_data["confirm_requests"],
        )

        query.answer.assert_awaited_once_with(
            "Выбор программы отменён."
        )
        edit_message.assert_awaited_once()

    
    async def test_cancel_only_selected_confirmation(self):
        first_token = "a" * 32
        second_token = "b" * 32

        query = SimpleNamespace(
            data=f"confirm_cancel:v1:{first_token}",
            answer=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)

        requests = {
            first_token: {
                "software_id": "xray",
                "version": "v2.0",
                "created_at": time.time(),
            },
            second_token: {
                "software_id": "nextcloud",
                "version": "v35.0",
                "created_at": time.time(),
            },
        }

        context = SimpleNamespace(
            user_data={"confirm_requests": requests},
        )

        with (
            patch("telegram_handlers.is_authorized", return_value=True),
            patch(
                "telegram_handlers.edit_callback_message",
                new_callable=AsyncMock,
            ) as edit_message,
        ):
            await handle_confirm_selection(update, context)

        self.assertNotIn(first_token, requests)
        self.assertIn(second_token, requests)

        query.answer.assert_awaited_once_with(
            "Подтверждение отменено."
        )
        edit_message.assert_awaited_once()

    async def test_answer_failure_after_manual_confirmation(self):
        token = "e" * 32

        query = SimpleNamespace(
            data=f"confirm_apply:v1:{token}",
            answer=AsyncMock(
                side_effect=BadRequest("Query is too old")
            ),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=123456789),
        )

        requests = {
            token: {
                "software_id": "xray",
                "version": "v2.0",
                "created_at": time.time(),
            }
        }

        context = SimpleNamespace(
            user_data={"confirm_requests": requests},
            bot_data={
                "config": {
                    "software": [
                        {
                            "id": "xray",
                            "name": "Xray",
                            "enabled": True,
                        }
                    ]
                }
            },
        )

        with (
            patch(
                "telegram_handlers.is_authorized",
                return_value=True,
            ),
            patch(
                "telegram_handlers.get_software_state",
                return_value={
                    "current_version": "v1.0",
                    "latest_version": "v2.0",
                },
            ),
            patch(
                "telegram_handlers.mark_version_updated",
                return_value=True,
            ) as mark_updated,
            patch(
                "telegram_handlers.edit_callback_message",
                new_callable=AsyncMock,
            ) as edit_message,
            self.assertLogs("telegram_handlers", level="WARNING"),
        ):
            await handle_confirm_apply(update, context)

        mark_updated.assert_called_once_with(
            "xray",
            "v2.0",
            source="telegram_confirm",
            actor_id=123456789,
        )
        edit_message.assert_awaited_once()
        self.assertNotIn(token, requests)

    async def test_missing_confirmation_is_logged(self):
        token = "f" * 32

        query = SimpleNamespace(
            data=f"confirm_apply:v1:{token}",
            answer=AsyncMock(),
        )

        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=123456789),
        )

        context = SimpleNamespace(
            user_data={"confirm_requests": {}},
        )

        with (
            patch("telegram_handlers.is_authorized", return_value=True),
            patch("telegram_handlers.mark_version_updated") as mark_updated,
            self.assertLogs("telegram_handlers", level="INFO") as captured_logs,
        ):
            await handle_confirm_apply(update, context)

        mark_updated.assert_not_called()

        query.answer.assert_awaited_once_with(
            "Подтверждение недействительно. Откройте /confirm заново.",
            show_alert=True,
        )

        self.assertTrue(
            any(
                "reason=request_not_found" in message
                and "actor_id=123456789" in message
                for message in captured_logs.output
            )
        )

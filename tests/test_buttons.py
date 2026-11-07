import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import database as db
from telegram.error import BadRequest
from telegram_handlers import handle_version_updated, is_authorized, handle_version_skip, handle_version_skip_cancel
from telegram_notifier import send_update_notification
from update_logic import UpdateResult


class ButtonTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp.name) / "test.db"
        db.initialize_database()
        db.create_software_state("xray", "v1")
        db.update_software_check("xray", "v2", "now")

    def tearDown(self):
        db.DATABASE_PATH = self.old_path
        self.temp.cleanup()

    async def press(self, data, edit_error=None, user_id=12345, chat_id=12345, chat_type="private", authorized_id=12345):
        query = SimpleNamespace(
            data=data, answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(side_effect=edit_error),
            message=SimpleNamespace(text="Уведомление", reply_markup=object()),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=user_id) if user_id is not None else None,
            effective_chat=SimpleNamespace(id=chat_id, type=chat_type) if chat_id is not None else None,
        )
        context = SimpleNamespace(
                user_data={},
                bot_data={
                "telegram_chat_id": authorized_id,
                "config": {
                    "notification_button_retention": "30d",
                },
            }
        )
        await handle_version_updated(update, context)
        return query

    def button(self, version="v2"):
        return "version_updated:v1:" + db.create_notification_button("xray", version)

    async def test_unauthorized_user_cannot_confirm(self):
        data = self.button()
        query = await self.press(data, user_id=99999)
        self.assertEqual(db.get_software_state("xray")["current_version"], "v1")
        query.answer.assert_awaited_once_with("Доступ запрещён.", show_alert=True)
        query.edit_message_reply_markup.assert_not_awaited()

    async def test_unauthorized_chat_cannot_confirm(self):
        data = self.button()
        query = await self.press(data, chat_id=99999)
        self.assertEqual(db.get_software_state("xray")["current_version"], "v1")
        query.answer.assert_awaited_once_with("Доступ запрещён.", show_alert=True)
        query.edit_message_reply_markup.assert_not_awaited()

    async def test_group_chat_cannot_confirm(self):
        data = self.button()
        query = await self.press(data, chat_type="supergroup")
        self.assertEqual(db.get_software_state("xray")["current_version"], "v1")
        query.answer.assert_awaited_once_with("Доступ запрещён.", show_alert=True)
        query.edit_message_reply_markup.assert_not_awaited()

    async def test_missing_identity_cannot_confirm(self):
        for options in ({"user_id": None}, {"chat_id": None}, {"authorized_id": None}):
            with self.subTest(options=options):
                query = await self.press(self.button(), **options)
                self.assertEqual(db.get_software_state("xray")["current_version"], "v1")
                query.answer.assert_awaited_once_with("Доступ запрещён.", show_alert=True)
                query.edit_message_reply_markup.assert_not_awaited()

    def test_authorization_requires_owner_private_chat(self):
        context = SimpleNamespace(bot_data={"telegram_chat_id": 12345})
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=12345),
            effective_chat=SimpleNamespace(id=12345, type="private"),
        )
        self.assertTrue(is_authorized(update, context))
        update.effective_chat.type = "group"
        self.assertFalse(is_authorized(update, context))

    async def test_current_and_duplicate(self):
        data = self.button()
        query = await self.press(data)
        self.assertEqual(db.get_software_state("xray")["current_version"], "v2")
        self.assertFalse(query.answer.call_args.kwargs["show_alert"])
        query = await self.press(data)
        self.assertTrue(query.answer.call_args.kwargs["show_alert"])

    async def test_stale_release(self):
        data = self.button()
        db.update_software_check("xray", "v3", "later")
        query = await self.press(data)
        self.assertEqual(db.get_software_state("xray")["current_version"], "v1")
        self.assertTrue(query.answer.call_args.kwargs["show_alert"])
        await self.press(self.button("v3"))
        self.assertEqual(db.get_software_state("xray")["current_version"], "v3")

    async def test_legacy_malformed_unknown(self):
        for data in ("version_updated:xray", "version_updated:v1:bad", "version_updated:v1:" + "0" * 32):
            query = await self.press(data)
            self.assertTrue(query.answer.call_args.kwargs["show_alert"])
            self.assertEqual(db.get_software_state("xray")["current_version"], "v1")

    async def test_deleted_software(self):
        data = self.button()
        with db.get_connection() as conn:
            conn.execute("DELETE FROM software_state")
        query = await self.press(data)
        self.assertTrue(query.answer.call_args.kwargs["show_alert"])

    async def test_restart(self):
        data = self.button()
        db.mark_version_notified("xray", "v2")
        db.initialize_database()
        self.assertEqual(db.get_software_state("xray")["last_notified_version"], "v2")
        await self.press(data)
        self.assertEqual(db.get_software_state("xray")["current_version"], "v2")

    async def test_not_modified_does_not_undo_confirmation(self):
        query = await self.press(self.button(), BadRequest("Message is not modified"))
        self.assertEqual(db.get_software_state("xray")["current_version"], "v2")
        query.answer.assert_awaited_once()
        query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)

    async def test_deleted_notification_does_not_undo_confirmation(self):
        with self.assertLogs("message_editing", level="WARNING"):
            query = await self.press(self.button(), BadRequest("Message to edit not found"))
        self.assertEqual(db.get_software_state("xray")["current_version"], "v2")
        query.answer.assert_awaited_once()

    async def test_notification_long_unicode_version(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        version = "релиз:" * 100
        result = UpdateResult("xray", "Xray", "v1", version, "https://example.com", True, True)
        await send_update_notification(bot, 1, result)
        data = bot.send_message.call_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
        self.assertLessEqual(len(data.encode("utf-8")), 64)
        token = data.removeprefix("version_updated:v1:")
        self.assertEqual(db.get_notification_button(token)["version"], version)

    def test_atomic_guard(self):
        db.update_software_check("xray", "v3", "later")
        self.assertFalse(db.mark_version_updated("xray", "v2"))
        self.assertFalse(db.mark_version_updated("missing", "v3"))
        self.assertEqual(db.get_software_state("xray")["current_version"], "v1")

    def test_legacy_migration_once(self):
        with db.get_connection() as conn:
            conn.execute("DROP TABLE notification_buttons")
        db.mark_version_notified("xray", "v2")
        db.initialize_database()
        self.assertIsNone(db.get_software_state("xray")["last_notified_version"])
        db.mark_version_notified("xray", "v2")
        db.initialize_database()
        self.assertEqual(db.get_software_state("xray")["last_notified_version"], "v2")

    
    async def test_expired_button_cannot_confirm(self):
        data = self.button()
        token = data.removeprefix("version_updated:v1:")

        expired_at = (
            datetime.now(timezone.utc) - timedelta(days=31)
        ).isoformat()

        with db.get_connection() as connection:
            connection.execute(
                """
                UPDATE notification_buttons
                SET created_at = ?
                WHERE token = ?
                """,
                (expired_at, token),
            )

        query = await self.press(data)

        self.assertEqual(
            db.get_software_state("xray")["current_version"],
            "v1",
        )
        query.answer.assert_awaited_once_with(
            "Эта кнопка устарела. Используйте новое уведомление.",
            show_alert=True,
        )
        query.edit_message_reply_markup.assert_awaited_once_with(
            reply_markup=None,
        )

    
    async def test_database_error_does_not_confirm_update(self):
        data = self.button()

        with patch(
            "telegram_handlers.mark_version_updated",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            query = await self.press(data)

        self.assertEqual(
            db.get_software_state("xray")["current_version"],
            "v1",
        )
        query.answer.assert_awaited_once_with(
            "Не удалось обновить базу. Попробуйте ещё раз.",
            show_alert=True,
        )
        query.edit_message_reply_markup.assert_not_awaited()

    
    async def test_duplicate_skip_button_does_not_repeat_prompt(self):
        token = db.create_notification_button("xray", "v2")
        data = f"version_skip:v1:{token}"

        query = SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            message=SimpleNamespace(
                chat_id=12345,
                message_id=100,
                reply_text=AsyncMock(),
            ),
        )

        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(
            user_data={},
            bot_data={
                "config": {
                    "notification_button_retention": "30d",
                }
            },
        )

        with patch(
            "telegram_handlers.is_authorized",
            return_value=True,
        ):
            await handle_version_skip(update, context)

            self.assertEqual(
                query.message.reply_text.await_count,
                1,
            )

            first_pending = context.user_data[
                "pending_version_skip"
            ].copy()

            await handle_version_skip(update, context)

        self.assertEqual(
            query.message.reply_text.await_count,
            1,
        )

        self.assertEqual(
            context.user_data["pending_version_skip"],
            first_pending,
        )

        self.assertFalse(
            db.is_release_skipped("xray", "v2")
        )

        
    async def test_second_skip_request_does_not_replace_first(self):
        db.create_software_state("other", "v1")
        db.update_software_check("other", "v2", "now")

        first_token = db.create_notification_button("xray", "v2")
        second_token = db.create_notification_button("other", "v2")

        def make_query(token, message_id):
            return SimpleNamespace(
                data=f"version_skip:v1:{token}",
                answer=AsyncMock(),
                message=SimpleNamespace(
                    chat_id=12345,
                    message_id=message_id,
                    reply_text=AsyncMock(),
                ),
            )

        context = SimpleNamespace(
            user_data={},
            bot_data={
                "config": {
                    "notification_button_retention": "30d",
                },
            },
        )

        first_query = make_query(first_token, 100)
        second_query = make_query(second_token, 101)

        with patch(
            "telegram_handlers.is_authorized",
            return_value=True,
        ):
            await handle_version_skip(
                SimpleNamespace(callback_query=first_query),
                context,
            )

            first_pending = context.user_data[
                "pending_version_skip"
            ].copy()

            await handle_version_skip(
                SimpleNamespace(callback_query=second_query),
                context,
            )

        self.assertEqual(
            context.user_data["pending_version_skip"],
            first_pending,
        )

        self.assertEqual(
            first_query.message.reply_text.await_count,
            1,
        )

        second_query.message.reply_text.assert_not_awaited()

        second_query.answer.assert_awaited_once_with(
            "Сначала завершите или отмените предыдущий пропуск.",
            show_alert=True,
        )

        self.assertFalse(db.is_release_skipped("xray", "v2"))
        self.assertFalse(db.is_release_skipped("other", "v2"))


    async def test_skip_cancel_allows_new_request(self):
        first_token = db.create_notification_button("xray", "v2")

        context = SimpleNamespace(
            user_data={},
            bot_data={
                "config": {
                    "notification_button_retention": "30d",
                },
            },
        )

        def make_query(data, message_id):
            return SimpleNamespace(
                data=data,
                answer=AsyncMock(),
                message=SimpleNamespace(
                    chat_id=12345,
                    message_id=message_id,
                    reply_text=AsyncMock(),
                ),
            )

        first_query = make_query(
            f"version_skip:v1:{first_token}",
            100,
        )

        with (
            patch(
                "telegram_handlers.is_authorized",
                return_value=True,
            ),
            patch(
                "telegram_handlers.edit_callback_message",
                new_callable=AsyncMock,
            ),
        ):
            await handle_version_skip(
                SimpleNamespace(callback_query=first_query),
                context,
            )

            request_token = context.user_data[
                "pending_version_skip"
            ]["request_token"]

            cancel_query = make_query(
                f"version_skip_cancel:v1:{request_token}",
                101,
            )

            self.assertIn(
                "pending_version_skip",
                context.user_data,
            )

            await handle_version_skip_cancel(
                SimpleNamespace(callback_query=cancel_query),
                context,
            )

            self.assertNotIn(
                "pending_version_skip",
                context.user_data,
            )

            cancel_query.answer.assert_awaited_once_with(
                "Пропуск отменён."
            )

            second_query = make_query(
                f"version_skip:v1:{first_token}",
                102,
            )

            await handle_version_skip(
                SimpleNamespace(callback_query=second_query),
                context,
            )

        self.assertIn(
            "pending_version_skip",
            context.user_data,
        )

        self.assertEqual(
            context.user_data["pending_version_skip"]["message_id"],
            102,
        )

        second_query.message.reply_text.assert_awaited_once()

        self.assertFalse(
            db.is_release_skipped("xray", "v2")
        )

    
    async def test_old_cancel_does_not_cancel_new_skip_request(self):
        token = db.create_notification_button("xray", "v2")

        context = SimpleNamespace(
            user_data={},
            bot_data={
                "config": {
                    "notification_button_retention": "30d",
                },
            },
        )

        def make_query(data, message_id):
            return SimpleNamespace(
                data=data,
                answer=AsyncMock(),
                message=SimpleNamespace(
                    chat_id=12345,
                    message_id=message_id,
                    reply_text=AsyncMock(),
                ),
            )

        skip_data = f"version_skip:v1:{token}"

        with (
            patch(
                "telegram_handlers.is_authorized",
                return_value=True,
            ),
            patch(
                "telegram_handlers.edit_callback_message",
                new_callable=AsyncMock,
            ),
        ):
            # Первый запрос.
            await handle_version_skip(
                SimpleNamespace(
                    callback_query=make_query(skip_data, 100)
                ),
                context,
            )

            old_request_token = context.user_data[
                "pending_version_skip"
            ]["request_token"]

            cancel_data = f"version_skip_cancel:v1:{old_request_token}"

            # Отменяем первый запрос.
            await handle_version_skip_cancel(
                SimpleNamespace(
                    callback_query=make_query(cancel_data, 101)
                ),
                context,
            )

            # Создаём новый запрос для того же выпуска.
            await handle_version_skip(
                SimpleNamespace(
                    callback_query=make_query(skip_data, 100)
                ),
                context,
            )

            second_pending = context.user_data[
                "pending_version_skip"
            ].copy()

            # Нажимаем старую кнопку отмены.
            old_cancel = make_query(cancel_data, 101)

            await handle_version_skip_cancel(
                SimpleNamespace(callback_query=old_cancel),
                context,
            )

        # Новый запрос должен сохраниться.
        self.assertEqual(
            context.user_data.get("pending_version_skip"),
            second_pending,
        )

        self.assertFalse(
            db.is_release_skipped("xray", "v2")
        )
    
    async def test_skip_cancel_button_uses_request_token(self):
        token = db.create_notification_button("xray", "v2")

        query = SimpleNamespace(
            data=f"version_skip:v1:{token}",
            answer=AsyncMock(),
            message=SimpleNamespace(
                chat_id=12345,
                message_id=100,
                reply_text=AsyncMock(),
            ),
        )

        context = SimpleNamespace(
            user_data={},
            bot_data={
                "config": {
                    "notification_button_retention": "30d",
                },
            },
        )

        with patch(
            "telegram_handlers.is_authorized",
            return_value=True,
        ):
            await handle_version_skip(
                SimpleNamespace(callback_query=query),
                context,
            )

        pending = context.user_data["pending_version_skip"]
        request_token = pending["request_token"]

        self.assertNotEqual(request_token, token)

        query.message.reply_text.assert_awaited_once()

        kwargs = query.message.reply_text.await_args.kwargs
        keyboard = kwargs["reply_markup"]

        button = keyboard.inline_keyboard[0][0]

        self.assertEqual(
            button.callback_data,
            f"version_skip_cancel:v1:{request_token}",
        )


if __name__ == "__main__":
    unittest.main()

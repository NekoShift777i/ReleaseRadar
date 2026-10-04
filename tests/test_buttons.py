import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from types import SimpleNamespace

import database as db
from telegram.error import BadRequest
from telegram_handlers import handle_version_updated
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

    async def press(self, data, edit_error=None):
        query = SimpleNamespace(
            data=data, answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(side_effect=edit_error),
        )
        await handle_version_updated(SimpleNamespace(callback_query=query), None)
        return query

    def button(self, version="v2"):
        return "version_updated:v1:" + db.create_notification_button("xray", version)

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

    async def test_edit_failure_does_not_undo_confirmation(self):
        query = await self.press(self.button(), BadRequest("Message is not modified"))
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


if __name__ == "__main__":
    unittest.main()

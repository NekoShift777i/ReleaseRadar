import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.error import BadRequest, TimedOut
from message_editing import edit_callback_message


class MessageEditingTests(unittest.IsolatedAsyncioTestCase):
    def make_query(self, text="Menu", markup="old"):
        return SimpleNamespace(
            message=SimpleNamespace(text=text, reply_markup=markup),
            edit_message_text=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
        )

    async def test_text_and_keyboard_updated(self):
        query = self.make_query()
        self.assertTrue(await edit_callback_message(
            query, text="New menu", reply_markup="new", edit_text=True))
        query.edit_message_text.assert_awaited_once_with(
            text="New menu", reply_markup="new", parse_mode=None)

    async def test_keyboard_only_updated(self):
        query = self.make_query()
        self.assertTrue(await edit_callback_message(query, reply_markup="new"))
        query.edit_message_reply_markup.assert_awaited_once_with(reply_markup="new")
        query.edit_message_text.assert_not_awaited()

    async def test_unchanged_message_skipped(self):
        query = self.make_query()
        self.assertTrue(await edit_callback_message(
            query, text="Menu", reply_markup="old", edit_text=True))
        query.edit_message_text.assert_not_awaited()

    async def test_unchanged_keyboard_skipped(self):
        query = self.make_query()
        self.assertTrue(await edit_callback_message(query, reply_markup="old"))
        query.edit_message_reply_markup.assert_not_awaited()

    async def test_not_modified_is_harmless(self):
        query = self.make_query()
        query.edit_message_text.side_effect = BadRequest("Message is not modified")
        self.assertTrue(await edit_callback_message(
            query, text="New menu", edit_text=True))

    async def test_deleted_message_does_not_crash(self):
        query = self.make_query()
        query.edit_message_reply_markup.side_effect = BadRequest("Message to edit not found")
        self.assertFalse(await edit_callback_message(query, reply_markup="new"))

    async def test_network_error_does_not_crash(self):
        query = self.make_query()
        query.edit_message_reply_markup.side_effect = TimedOut()
        self.assertFalse(await edit_callback_message(query, reply_markup="new"))

    async def test_inaccessible_message_attempts_edit(self):
        query = self.make_query()
        query.message = None
        self.assertTrue(await edit_callback_message(query, reply_markup="new"))
        query.edit_message_reply_markup.assert_awaited_once()

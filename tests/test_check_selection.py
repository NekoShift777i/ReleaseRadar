import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from telegram_handlers import build_check_keyboard, handle_check_selection


class CheckSelectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = {"software": [
            {"id": "one", "name": "One", "enabled": True},
            {"id": "off", "name": "Off", "enabled": False},
            {"id": "two", "name": "Two", "enabled": True},
        ]}
        self.requests = Mock()
        self.requests.request.return_value = "accepted"

    def make_context(self, data, user=123):
        query = SimpleNamespace(data=data, answer=AsyncMock(), edit_message_reply_markup=AsyncMock())
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user),
                                 effective_chat=SimpleNamespace(id=123, type="private"))
        context = SimpleNamespace(bot_data={"telegram_chat_id": 123, "config": self.config,
                                            "manual_checks": self.requests},
                                  bot=SimpleNamespace(send_message=AsyncMock()))
        return update, context

    def test_keyboard_only_enabled_and_all(self):
        keyboard = build_check_keyboard(self.config).inline_keyboard
        self.assertEqual([row[0].callback_data for row in keyboard],
                         ["check_select:0", "check_select:1", "check_all", "check_cancel"])

    async def test_selected_software(self):
        update, context = self.make_context("check_select:1")
        await handle_check_selection(update, context)
        self.assertEqual(self.requests.request.call_args.kwargs["software_id"], "two")
        update.callback_query.edit_message_reply_markup.assert_awaited_once()

    async def test_all_software(self):
        update, context = self.make_context("check_all")
        await handle_check_selection(update, context)
        self.assertIsNone(self.requests.request.call_args.kwargs["software_id"])

    async def test_unauthorized(self):
        update, context = self.make_context("check_select:0", user=999)
        await handle_check_selection(update, context)
        self.requests.request.assert_not_called()
        update.callback_query.answer.assert_awaited_once_with("Доступ запрещён.", show_alert=True)

    async def test_invalid_selection(self):
        update, context = self.make_context("check_select:100")
        await handle_check_selection(update, context)
        self.requests.request.assert_not_called()

    async def test_busy(self):
        self.requests.request.return_value = "busy"
        update, context = self.make_context("check_select:0")
        await handle_check_selection(update, context)
        update.callback_query.edit_message_reply_markup.assert_not_awaited()

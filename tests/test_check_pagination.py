import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from telegram_handlers import CHECK_PAGE_SIZE, build_check_keyboard, handle_check_selection


class CheckPaginationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = {"software": [
            {"id": f"id-{i}", "name": f"Program {i}", "enabled": True}
            for i in range(19)
        ]}
        self.config["software"][3]["enabled"] = False
        self.requests = Mock()
        self.requests.request.return_value = "accepted"

    def make_context(self, data, user=123):
        query = SimpleNamespace(data=data, answer=AsyncMock(),
                                edit_message_reply_markup=AsyncMock(),
                                edit_message_text=AsyncMock(),
                                message=SimpleNamespace(text="Выберите программу для проверки:",
                                                        reply_markup=None))
        update = SimpleNamespace(callback_query=query,
                                 effective_user=SimpleNamespace(id=user),
                                 effective_chat=SimpleNamespace(id=123, type="private"))
        context = SimpleNamespace(bot_data={"telegram_chat_id": 123,
                                            "config": self.config,
                                            "manual_checks": self.requests},
                                  bot=SimpleNamespace(send_message=AsyncMock()))
        return update, context

    def test_first_page_has_eight_entries_and_navigation(self):
        rows = build_check_keyboard(self.config).inline_keyboard
        self.assertEqual([r[0].callback_data for r in rows[:CHECK_PAGE_SIZE]],
                         [f"check_select:{i}" for i in range(8)])
        self.assertEqual([b.callback_data for b in rows[-3]],
                         ["check_page_info", "check_page:1"])
        self.assertEqual(rows[-2][0].callback_data, "check_all")
        self.assertEqual(rows[-1][0].callback_data, "check_cancel")

    def test_middle_and_last_page(self):
        middle = build_check_keyboard(self.config, 1).inline_keyboard
        self.assertEqual(middle[0][0].callback_data, "check_select:8")
        self.assertEqual([b.callback_data for b in middle[-3]],
                         ["check_page:0", "check_page_info", "check_page:2"])
        last = build_check_keyboard(self.config, 2).inline_keyboard
        self.assertEqual([r[0].callback_data for r in last[:-3]],
                         ["check_select:16", "check_select:17"])
        self.assertEqual([b.callback_data for b in last[-3]],
                         ["check_page:1", "check_page_info"])

    def test_invalid_page_rejected(self):
        with self.assertRaises(ValueError):
            build_check_keyboard(self.config, 3)
        with self.assertRaises(ValueError):
            build_check_keyboard(self.config, -1)

    async def test_navigation_does_not_start_check(self):
        update, context = self.make_context("check_page:1")
        await handle_check_selection(update, context)
        self.requests.request.assert_not_called()
        markup = update.callback_query.edit_message_reply_markup.call_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "check_select:8")

    async def test_last_page_selection_uses_correct_id(self):
        update, context = self.make_context("check_select:17")
        await handle_check_selection(update, context)
        self.assertEqual(self.requests.request.call_args.kwargs["software_id"], "id-18")

    async def test_accepted_selection_updates_text_and_removes_buttons(self):
        update, context = self.make_context("check_select:17")
        await handle_check_selection(update, context)
        update.callback_query.edit_message_text.assert_awaited_once_with(
            text="Запрошена проверка Program 18. Ожидайте результат.",
            reply_markup=None, parse_mode=None,
        )
        update.callback_query.answer.assert_awaited_once()

    async def test_accepted_all_updates_text(self):
        update, context = self.make_context("check_all")
        await handle_check_selection(update, context)
        update.callback_query.edit_message_text.assert_awaited_once_with(
            text="Запрошена проверка всех программ. Ожидайте результат.",
            reply_markup=None, parse_mode=None,
        )

    async def test_stale_page_rejected(self):
        update, context = self.make_context("check_page:99")
        await handle_check_selection(update, context)
        self.requests.request.assert_not_called()
        update.callback_query.edit_message_reply_markup.assert_not_awaited()
        self.assertTrue(update.callback_query.answer.call_args.kwargs["show_alert"])

    async def test_unauthorized_navigation(self):
        update, context = self.make_context("check_page:1", user=999)
        await handle_check_selection(update, context)
        self.requests.request.assert_not_called()
        update.callback_query.edit_message_reply_markup.assert_not_awaited()

    async def test_page_counter_does_not_start_check(self):
        update, context = self.make_context("check_page_info")
        await handle_check_selection(update, context)
        self.requests.request.assert_not_called()
        update.callback_query.edit_message_reply_markup.assert_not_awaited()


class CheckCancelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.helper = CheckPaginationTests()
        self.helper.setUp()

    async def test_cancel_does_not_schedule_check(self):
        update, context = self.helper.make_context("check_cancel")
        await handle_check_selection(update, context)
        self.helper.requests.request.assert_not_called()
        update.callback_query.answer.assert_awaited_once()
        update.callback_query.edit_message_text.assert_awaited_once_with(
            text="Выбор проверки отменён.", reply_markup=None, parse_mode=None)

    async def test_cancel_unauthorized(self):
        update, context = self.helper.make_context("check_cancel", user=999)
        await handle_check_selection(update, context)
        self.helper.requests.request.assert_not_called()
        update.callback_query.edit_message_reply_markup.assert_not_awaited()


class CheckMenuEditTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.helper = CheckPaginationTests()
        self.helper.setUp()

    async def test_repeated_page_click_does_not_edit(self):
        update, context = self.helper.make_context("check_page:1")
        update.callback_query.message.reply_markup = build_check_keyboard(
            self.helper.config, 1
        )
        await handle_check_selection(update, context)
        update.callback_query.answer.assert_awaited_once()
        update.callback_query.edit_message_reply_markup.assert_not_awaited()

    async def test_cancel_with_missing_message_does_not_crash(self):
        from telegram.error import BadRequest
        update, context = self.helper.make_context("check_cancel")
        update.callback_query.message = None
        update.callback_query.edit_message_text.side_effect = BadRequest(
            "Message to edit not found"
        )
        await handle_check_selection(update, context)
        update.callback_query.answer.assert_awaited_once()
        self.helper.requests.request.assert_not_called()

    async def test_cancel_unchanged_message_does_not_edit(self):
        update, context = self.helper.make_context("check_cancel")
        update.callback_query.message.text = "Выбор проверки отменён."
        await handle_check_selection(update, context)
        update.callback_query.answer.assert_awaited_once()
        update.callback_query.edit_message_text.assert_not_awaited()

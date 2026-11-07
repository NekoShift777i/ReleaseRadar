import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import closing

import httpx

import database
from error_messages import describe_check_error
from status import get_status_messages


class CheckErrorTests(unittest.TestCase):
    def test_http_error_does_not_expose_url(self):
        request = httpx.Request('GET', 'https://example.org/private?token=secret')
        response = httpx.Response(429, request=request)
        error = httpx.HTTPStatusError('secret', request=request, response=response)
        self.assertEqual(describe_check_error(error), 'HTTP 429: превышен лимит запросов')

    def test_database_migration_preserves_success_and_clears_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.db'
            with closing(sqlite3.connect(path)) as connection:
                with connection:
                    connection.execute('CREATE TABLE software_state (software_id TEXT PRIMARY KEY, current_version TEXT NOT NULL, latest_version TEXT, last_notified_version TEXT, last_checked_at TEXT)')
                    connection.execute("INSERT INTO software_state VALUES ('x', 'v1', 'v2', NULL, '2026-11-05T00:00:00+00:00')")
            with patch.object(database, 'DATABASE_PATH', path):
                database.initialize_database()
                database.initialize_database()
                database.record_software_error('x', 'Время ожидания истекло', '2026-11-06T00:00:00+00:00')
                state = database.get_software_state('x')
                self.assertEqual(state['last_checked_at'], '2026-11-05T00:00:00+00:00')
                self.assertEqual(state['latest_version'], 'v2')
                with patch('status.get_check_interval', return_value=60):
                    messages = get_status_messages({'software': [{'id': 'x', 'name': 'X', 'channel': 'stable', 'enabled': True, 'current_version': 'v1'}]})
                self.assertIn('⚠️ Последняя ошибка: Время ожидания истекло', messages[0])
                database.update_software_check('x', 'v3', '2026-11-06T01:00:00+00:00')
                state = database.get_software_state('x')
                self.assertIsNone(state['last_error'])
                self.assertIsNone(state['last_error_at'])
                self.assertEqual(state['latest_version'], 'v3')

    
    def test_service_unavailable_does_not_expose_url(self):
        request = httpx.Request(
            "GET",
            "https://example.org/private?token=secret",
        )
        response = httpx.Response(
            503,
            request=request,
        )
        error = httpx.HTTPStatusError(
            "secret",
            request=request,
            response=response,
        )

        message = describe_check_error(error)

        self.assertIn("503", message)
        self.assertNotIn("secret", message)
        self.assertNotIn("token=", message)
        self.assertNotIn("example.org", message)


    def test_timeout_does_not_expose_url(self):
        request = httpx.Request(
            "GET",
            "https://example.org/private?token=secret",
        )

        error = httpx.ReadTimeout(
            "secret",
            request=request,
        )

        message = describe_check_error(error)

        self.assertEqual(
            message,
            "Превышено время ожидания ответа источника",
        )


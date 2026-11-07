import ast
import re
import unittest
from pathlib import Path


class SkipCallbackRegistrationTests(unittest.TestCase):
    def test_cancel_handler_pattern(self):
        main_path = Path(__file__).resolve().parents[1] / "main.py"
        tree = ast.parse(main_path.read_text(encoding="utf-8"))

        patterns = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if not isinstance(node.func, ast.Name):
                continue

            if node.func.id != "CallbackQueryHandler":
                continue

            if not node.args:
                continue

            handler = node.args[0]

            if not (
                isinstance(handler, ast.Name)
                and handler.id == "handle_version_skip_cancel"
            ):
                continue

            for keyword in node.keywords:
                if keyword.arg == "pattern":
                    patterns.append(ast.literal_eval(keyword.value))

        self.assertEqual(len(patterns), 1)

        pattern = re.compile(patterns[0])

        valid_token = "a" * 32

        self.assertIsNotNone(
            pattern.fullmatch(
                f"version_skip_cancel:v1:{valid_token}"
            )
        )

        for invalid in (
            "version_skip_cancel",
            "version_skip_cancel:v1:invalid",
            "version_skip_cancel:v1:" + "a" * 31,
            "version_skip_cancel:v1:" + "g" * 32,
        ):
            with self.subTest(data=invalid):
                self.assertIsNone(pattern.fullmatch(invalid))

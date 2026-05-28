import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class _FakeApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class _FakeCommandResponse:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _load_command_service():
    for name in [
        "app.api.services.command_service",
        "app.api.errors",
        "app.api.schemas.command",
    ]:
        sys.modules.pop(name, None)

    fake_errors = types.ModuleType("app.api.errors")
    fake_errors.ApiError = _FakeApiError

    fake_command_schema = types.ModuleType("app.api.schemas.command")
    fake_command_schema.CommandResponse = _FakeCommandResponse

    with patch.dict(
        sys.modules,
        {
            "app.api.errors": fake_errors,
            "app.api.schemas.command": fake_command_schema,
        },
    ):
        return importlib.import_module("app.api.services.command_service")


class MobileApiCommandHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.command_service = _load_command_service()
        cls.project_root = Path(__file__).resolve().parents[1]

    def test_build_command_argv_for_bot_stop_and_start(self):
        service = self.command_service

        stop_argv, stop_stdin = service.build_command_argv({"kind": "bot_stop"})
        start_argv, start_stdin = service.build_command_argv({"kind": "bot_start"})

        self.assertEqual(stop_argv, [str(self.project_root / "stop.sh")])
        self.assertIsNone(stop_stdin)
        self.assertEqual(start_argv, [str(self.project_root / "run.sh")])
        self.assertIsNone(start_stdin)

    def test_build_command_argv_for_reset(self):
        service = self.command_service

        with patch.dict("os.environ", {"PYTHON_BIN": "/tmp/python"}, clear=False):
            argv, stdin_text = service.build_command_argv({"kind": "reset"})

        self.assertEqual(argv, ["/tmp/python", "scripts/reset_live.py"])
        self.assertIsNone(stdin_text)

    def test_build_command_argv_for_adjust_budget(self):
        service = self.command_service

        command = {
            "kind": "adjust_budget",
            "params": {"target_budget": "1234567", "force": True},
        }
        with patch.dict("os.environ", {"PYTHON_BIN": "/tmp/python"}, clear=False):
            argv, stdin_text = service.build_command_argv(command)

        self.assertEqual(
            argv,
            [
                "/tmp/python",
                "scripts/adjust_budget_live.py",
                "--target-budget",
                "1234567",
                "--force",
            ],
        )
        self.assertEqual(stdin_text, "y\n")

    def test_build_command_argv_for_reset_stop_loss(self):
        service = self.command_service

        command = {"kind": "reset_stop_loss", "params": {"force": True}}
        with patch.dict("os.environ", {"PYTHON_BIN": "/tmp/python"}, clear=False):
            argv, stdin_text = service.build_command_argv(command)

        self.assertEqual(argv, ["/tmp/python", "main.py", "reset-stop-loss", "--force"])
        self.assertIsNone(stdin_text)

    def test_build_command_argv_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            self.command_service.build_command_argv({"kind": "unknown"})

    def test_redact_log_removes_known_secret_patterns(self):
        raw_log = "\n".join(
            [
                "UPBIT_ACCESS_KEY=access-secret",
                "UPBIT_SECRET_KEY=secret-secret",
                "Authorization: Bearer jwt-token",
                "ordinary line remains",
            ]
        )

        redacted = self.command_service.redact_log(raw_log)

        self.assertNotIn("access-secret", redacted)
        self.assertNotIn("secret-secret", redacted)
        self.assertNotIn("jwt-token", redacted)
        self.assertIn("[REDACTED]", redacted)
        self.assertIn("ordinary line remains", redacted)

    def test_redact_log_keeps_tail_limit(self):
        redacted = self.command_service.redact_log("x" * 20010)

        self.assertEqual(len(redacted), 20000)


if __name__ == "__main__":
    unittest.main()

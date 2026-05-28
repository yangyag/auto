import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class SettingsEnvLoadingTest(unittest.TestCase):

    def test_settings_loads_symbol_from_env_file(self):
        project_root = Path(__file__).resolve().parents[1]
        settings_source = (project_root / "app" / "config" / "settings.py").read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "app" / "config").mkdir(parents=True)
            (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "app" / "config" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "app" / "config" / "settings.py").write_text(settings_source, encoding="utf-8")
            (tmp_path / ".env").write_text("SYMBOL=KRW-USDT\n", encoding="utf-8")

            env = os.environ.copy()
            env.pop("SYMBOL", None)

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    textwrap.dedent(
                        """
                        import sys
                        sys.path.insert(0, r'__TMPDIR__')
                        import app.config.settings as settings
                        print(settings.SYMBOL)
                        """.replace("__TMPDIR__", str(r"__TMPDIR__"))
                    ),
                ],
                cwd=tmpdir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "KRW-USDT")

    def test_settings_loads_upbit_credentials_from_project_root_env_file(self):
        project_root = Path(__file__).resolve().parents[1]
        settings_source = (project_root / "app" / "config" / "settings.py").read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "app" / "config").mkdir(parents=True)
            (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "app" / "config" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "app" / "config" / "settings.py").write_text(settings_source, encoding="utf-8")
            (tmp_path / ".env").write_text(
                "UPBIT_ACCESS_KEY=test-access\nUPBIT_SECRET_KEY=test-secret\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.pop("UPBIT_ACCESS_KEY", None)
            env.pop("UPBIT_SECRET_KEY", None)

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    textwrap.dedent(
                        """
                        import sys
                        sys.path.insert(0, r'__TMPDIR__')
                        import app.config.settings as settings
                        print(settings.API_KEY)
                        print(settings.API_SECRET)
                        """.replace("__TMPDIR__", str(r"__TMPDIR__"))
                    ),
                ],
                cwd=tmpdir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip().splitlines(), ["test-access", "test-secret"])

    def test_settings_loads_postgres_state_settings_from_env_file(self):
        project_root = Path(__file__).resolve().parents[1]
        settings_source = (project_root / "app" / "config" / "settings.py").read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "app" / "config").mkdir(parents=True)
            (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "app" / "config" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "app" / "config" / "settings.py").write_text(settings_source, encoding="utf-8")
            (tmp_path / ".env").write_text(
                "STATE_BOT_KEY=env-bot\nPGHOST=db.example\nPGPORT=5433\nPGDATABASE=grid\nPGUSER=bot\nPGPASSWORD=secret\nPGSCHEMA=custom_schema\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.pop("STATE_BOT_KEY", None)
            env.pop("PGHOST", None)
            env.pop("PGPORT", None)
            env.pop("PGDATABASE", None)
            env.pop("PGUSER", None)
            env.pop("PGPASSWORD", None)
            env.pop("PGSCHEMA", None)

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    textwrap.dedent(
                        """
                        import sys
                        sys.path.insert(0, r'__TMPDIR__')
                        import app.config.settings as settings
                        print(settings.STATE_BOT_KEY)
                        print(settings.PGHOST)
                        print(settings.PGPORT)
                        print(settings.PGDATABASE)
                        print(settings.PGUSER)
                        print(settings.PGPASSWORD)
                        print(settings.PGSCHEMA)
                        """.replace("__TMPDIR__", str(r"__TMPDIR__"))
                    ),
                ],
                cwd=tmpdir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            result.stdout.strip().splitlines(),
            ["env-bot", "db.example", "5433", "grid", "bot", "secret", "custom_schema"],
        )

    def test_settings_loads_upbit_websocket_settings_from_env_file(self):
        project_root = Path(__file__).resolve().parents[1]
        settings_source = (project_root / "app" / "config" / "settings.py").read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "app" / "config").mkdir(parents=True)
            (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "app" / "config" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "app" / "config" / "settings.py").write_text(settings_source, encoding="utf-8")
            (tmp_path / ".env").write_text(
                "UPBIT_WS_PUBLIC_ENABLED=true\n"
                "UPBIT_WS_PRICE_MAX_AGE_SECONDS=3.5\n"
                "UPBIT_WS_EVENT_LOOP_ENABLED=false\n"
                "UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS=2.5\n"
                "UPBIT_WS_CANDLE_ENABLED=true\n"
                "UPBIT_WS_CANDLE_MAX_AGE_SECONDS=12.5\n"
                "UPBIT_WS_ASSET_ENABLED=true\n"
                "UPBIT_WS_ASSET_MAX_AGE_SECONDS=7.5\n"
                "UPBIT_WS_ORDER_ENABLED=true\n"
                "UPBIT_WS_ORDER_MAX_AGE_SECONDS=4.5\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.pop("UPBIT_WS_PUBLIC_ENABLED", None)
            env.pop("UPBIT_WS_PRICE_MAX_AGE_SECONDS", None)
            env.pop("UPBIT_WS_EVENT_LOOP_ENABLED", None)
            env.pop("UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS", None)
            env.pop("UPBIT_WS_CANDLE_ENABLED", None)
            env.pop("UPBIT_WS_CANDLE_MAX_AGE_SECONDS", None)
            env.pop("UPBIT_WS_ASSET_ENABLED", None)
            env.pop("UPBIT_WS_ASSET_MAX_AGE_SECONDS", None)
            env.pop("UPBIT_WS_ORDER_ENABLED", None)
            env.pop("UPBIT_WS_ORDER_MAX_AGE_SECONDS", None)

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    textwrap.dedent(
                        """
                        import sys
                        sys.path.insert(0, r'__TMPDIR__')
                        import app.config.settings as settings
                        print(settings.UPBIT_WS_PUBLIC_ENABLED)
                        print(settings.UPBIT_WS_PRICE_MAX_AGE_SECONDS)
                        print(settings.UPBIT_WS_EVENT_LOOP_ENABLED)
                        print(settings.UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS)
                        print(settings.UPBIT_WS_CANDLE_ENABLED)
                        print(settings.UPBIT_WS_CANDLE_MAX_AGE_SECONDS)
                        print(settings.UPBIT_WS_ASSET_ENABLED)
                        print(settings.UPBIT_WS_ASSET_MAX_AGE_SECONDS)
                        print(settings.UPBIT_WS_ORDER_ENABLED)
                        print(settings.UPBIT_WS_ORDER_MAX_AGE_SECONDS)
                        """.replace("__TMPDIR__", str(r"__TMPDIR__"))
                    ),
                ],
                cwd=tmpdir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            result.stdout.strip().splitlines(),
            ["True", "3.5", "False", "2.5", "True", "12.5", "True", "7.5", "True", "4.5"],
        )

    def test_settings_defaults_enable_public_ticker_event_loop(self):
        project_root = Path(__file__).resolve().parents[1]
        settings_source = (project_root / "app" / "config" / "settings.py").read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "app" / "config").mkdir(parents=True)
            (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "app" / "config" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "app" / "config" / "settings.py").write_text(settings_source, encoding="utf-8")

            env = os.environ.copy()
            env.pop("UPBIT_WS_PUBLIC_ENABLED", None)
            env.pop("UPBIT_WS_EVENT_LOOP_ENABLED", None)
            env.pop("UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS", None)

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    textwrap.dedent(
                        """
                        import sys
                        sys.path.insert(0, r'__TMPDIR__')
                        import app.config.settings as settings
                        print(settings.UPBIT_WS_PUBLIC_ENABLED)
                        print(settings.UPBIT_WS_EVENT_LOOP_ENABLED)
                        print(settings.UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS)
                        """.replace("__TMPDIR__", str(r"__TMPDIR__"))
                    ),
                ],
                cwd=tmpdir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip().splitlines(), ["True", "True", "3.0"])


if __name__ == "__main__":
    unittest.main()

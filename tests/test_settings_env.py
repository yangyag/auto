import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class SettingsEnvLoadingTest(unittest.TestCase):

    def test_settings_loads_upbit_credentials_from_project_root_env_file(self):
        project_root = Path(__file__).resolve().parents[1]
        settings_source = (project_root / "config" / "settings.py").read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "config").mkdir()
            (tmp_path / "config" / "__init__.py").write_text("", encoding="utf-8")
            (tmp_path / "config" / "settings.py").write_text(settings_source, encoding="utf-8")
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
                        import config.settings as settings
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


if __name__ == "__main__":
    unittest.main()

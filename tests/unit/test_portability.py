"""Regressions for Windows text encoding, secrets and launcher behavior."""

from contextlib import redirect_stderr
import io
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "portable_manager", ROOT / "scripts/manage.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PortabilityTests(unittest.TestCase):
    def test_bom_crlf_and_literal_dollar(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_bytes(
                b"\xef\xbb\xbfREADER_PASSWORD=old\r\nGUEST_PASSWORD='a$b'\r\n"
            )
            m.configure(path)
            self.assertEqual(m.env_values(path)["READER_PASSWORD"], "old")
            self.assertEqual(m.env_values(path)["GUEST_PASSWORD"], "a$b")

    def test_duplicate_and_interpolation_rejected_without_secret(self):
        for content in ("X=secret\nX=secret\n", "X=$secret\n", "secret\n"):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / ".env"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError) as error:
                    m.env_values(path)
                self.assertNotIn("secret", str(error.exception))

    def test_env_overrides_do_not_select_wrong_volume(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("READER_PASSWORD=expected\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "READER_PASSWORD": "wrong",
                    "STORAGE_DATA_VOLUME": "production",
                    "COMPOSE_PROFILES": "planned",
                },
            ):
                env = m.compose_environment(path)
                self.assertNotIn("READER_PASSWORD", env)
                self.assertNotIn("STORAGE_DATA_VOLUME", env)
                self.assertNotIn("COMPOSE_PROFILES", env)
                self.assertIn("PATH", env)

    def test_launcher_preserves_path_with_spaces(self):
        with patch.object(m, "ROOT", Path("/path with spaces/Карта")):
            command = m.command(["config", "--quiet"])
            self.assertIn(str(m.ROOT / "docker-compose.yml"), command)
            self.assertEqual(command[-2:], ["config", "--quiet"])

    def test_disposable_override_only_explicit(self):
        override = str(ROOT / "tests/integration/docker-compose.disposable.yml")
        self.assertNotIn(override, m.command(["run", "probe"], probe=True))
        self.assertIn(override, m.command(["up"], probe=True, disposable=True))

    def test_failed_readiness_never_starts_backend(self):
        import subprocess

        def run(args, **kwargs):
            if "/opt/storage/verify.js" in args:
                raise subprocess.CalledProcessError(1, args)

        with patch.object(Path, "is_file", return_value=True), patch.object(
            m.shutil, "which", return_value="docker"
        ), patch.object(m, "prevent_double_mount"), patch.object(
            m, "execute", side_effect=run
        ) as call:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(m.main(["up", "--connections"]), 1)
            self.assertFalse(any("--build" in c.args[0] for c in call.call_args_list))

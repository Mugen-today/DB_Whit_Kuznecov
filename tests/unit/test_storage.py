import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.database.mongodb import MongoDB
from app.main import create_app

spec = importlib.util.spec_from_file_location("manager", ROOT / "scripts/manage.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.options = kwargs
        self.closed = False
        self.calls = []
        self.cases = self

    def __getitem__(self, name):
        return self

    def command(self, name):
        self.calls.append(name)

    def find_one(self, *args, **kwargs):
        self.calls.append("read")

    def close(self):
        self.closed = True


class StorageTests(unittest.TestCase):
    def test_tree(self):
        for name in ("backend", "storage", "dashboard", "qgis_plugin", "tests"):
            self.assertTrue((ROOT / name).is_dir())
        for name in (
            "query",
            "import_data",
            "export_data",
            "spatial",
            "sync",
            "analytics",
        ):
            self.assertTrue((ROOT / "backend/app/modules" / f"{name}.py").is_file())

    def test_schema(self):
        s = json.loads((ROOT / "storage/schema/model.json").read_text(encoding="utf-8"))
        self.assertEqual(len(s["collections"]), 17)

    def test_create_env_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / ".env"
            m.initialize(p)
            before = p.read_bytes()
            with self.assertRaises(FileExistsError):
                m.initialize(p)
            self.assertEqual(p.read_bytes(), before)
            secrets = [v for k, v in m.env_values(p).items() if k.endswith("PASSWORD")]
            self.assertEqual(len(set(secrets)), 6)

    def test_command_files(self):
        cmd = m.command(["ps"], emergency=True, probe=True, local=True)
        for name in (
            "docker-compose.yml",
            "docker-compose.emergency.yml",
            "docker-compose.local.yml",
            "tests/integration/docker-compose.test.yml",
        ):
            self.assertIn(str(ROOT / name), cmd)

    def test_default_no_ports_overlay(self):
        self.assertNotIn(str(ROOT / "docker-compose.local.yml"), m.command(["ps"]))

    def test_missing_docker_fails(self):
        with patch.object(m.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError):
                m.execute(["ps"])

    def test_old_project_same_service_blocks(self):
        with patch.object(m, "env_values", return_value={}), patch.object(
            m.subprocess, "run"
        ) as run:
            run.return_value.stdout = "disease-storage/storage\n"
            with self.assertRaises(RuntimeError):
                m.prevent_double_mount()

    def test_network_test_never_writes(self):
        with patch.object(m.shutil, "which", return_value="/docker"), patch.object(
            Path, "is_file", return_value=True
        ), patch.object(m, "execute") as run:
            self.assertEqual(m.main(["network-test"]), 0)
            self.assertIn("TEST_WRITES=0", run.call_args.args[0])

    def test_connector_five_limited_pools(self):
        store = MongoDB(
            {
                k: "secret"
                for k in [
                    "READER_PASSWORD",
                    "INGEST_PASSWORD",
                    "PROCESSOR_PASSWORD",
                    "USER_PASSWORD",
                    "GUEST_PASSWORD",
                ]
            },
            FakeClient,
        )
        self.assertEqual(len(store.clients), 5)
        for c in store.clients.values():
            self.assertEqual(c.args, ("storage", 27017))
            self.assertEqual(c.options["authSource"], "Schema")
            self.assertEqual(c.options["maxPoolSize"], 4)
            self.assertFalse(c.options["retryWrites"])
            self.assertNotEqual(c.options["username"], "storage_admin")
        store.ready()
        for c in store.clients.values():
            self.assertEqual(c.calls, ["ping", "read"])
        store.close()
        self.assertTrue(all(c.closed for c in store.clients.values()))

    def test_connector_missing_password(self):
        with self.assertRaises(ValueError):
            MongoDB({}, FakeClient)

    def test_factory_failure_closes_existing(self):
        made = []

        def factory(*a, **k):
            if made:
                raise RuntimeError("failed")
            c = FakeClient()
            made.append(c)
            return c

        with self.assertRaises(RuntimeError):
            MongoDB(
                {
                    k: "secret"
                    for k in [
                        "READER_PASSWORD",
                        "INGEST_PASSWORD",
                        "PROCESSOR_PASSWORD",
                        "USER_PASSWORD",
                        "GUEST_PASSWORD",
                    ]
                },
                factory,
            )
        self.assertTrue(made[0].closed)

    def test_unknown_role(self):
        store = MongoDB(
            {
                k: "secret"
                for k in [
                    "READER_PASSWORD",
                    "INGEST_PASSWORD",
                    "PROCESSOR_PASSWORD",
                    "USER_PASSWORD",
                    "GUEST_PASSWORD",
                ]
            },
            FakeClient,
        )
        with self.assertRaises(ValueError):
            store.database("root")

    def response(self, path, fail=False):
        class Store:
            def ready(self):
                if fail:
                    raise RuntimeError("sensitive_password")

        captured = []
        body = b"".join(
            create_app(Store())(
                {"PATH_INFO": path, "REQUEST_METHOD": "GET"},
                lambda status, headers: captured.append(status),
            )
        )
        return captured[0], body

    def test_ready(self):
        self.assertEqual(self.response("/health/ready")[0], "200 OK")

    def test_ready_failure_no_secret(self):
        status, body = self.response("/health/ready", True)
        self.assertTrue(status.startswith("503"))
        self.assertNotIn(b"sensitive_password", body)

    def test_business_unimplemented(self):
        self.assertTrue(self.response("/v1/query")[0].startswith("501"))

    def test_live_does_not_require_database(self):
        self.assertTrue(self.response("/health/live", True)[0].startswith("200"))

    def test_health_not_schema(self):
        self.assertNotIn(
            "getUser(", (ROOT / "storage/scripts/health.js").read_text(encoding="utf-8")
        )

    def test_init_order_explicit(self):
        self.assertIn(
            "['schema','roles','indexes']",
            (ROOT / "storage/init/bootstrap.js").read_text(encoding="utf-8"),
        )

    def test_module_explicit_failure(self):
        from app.modules.query import execute

        with self.assertRaises(NotImplementedError):
            execute()

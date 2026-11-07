import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.auth.ownership import Principal, Repository

spec = importlib.util.spec_from_file_location(
    "repair_manager", ROOT / "scripts/manage.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Collection:
    def __init__(self):
        self.calls = []

    def find_one(self, *args):
        self.calls.append(("find", args))
        return None

    def insert_one(self, *args):
        self.calls.append(("insert", args))

    def update_one(self, *args, **kwargs):
        self.calls.append(("update", args, kwargs))


class Store:
    def __init__(self):
        self.c = Collection()
        self.roles = []

    def database(self, role):
        self.roles.append(role)
        return self

    def __getitem__(self, key):
        return self.c


class RepairTests(unittest.TestCase):
    def test_typos_all_relationships(self):
        s = json.loads((ROOT / "storage/schema/model.json").read_text(encoding="utf-8"))
        self.assertIn("Schema.Patient", s["collections"])
        self.assertIn("Schema.Settlement", s["collections"])
        for wrong in (
            "Pdtient",
            "Setlement",
            "setlement",
            "courpus",
            "сhronic_diseases",
        ):
            self.assertNotIn(wrong, json.dumps(s, ensure_ascii=False))
        for relation in s["relationships"]:
            for endpoint in relation["relationship"]:
                self.assertIn(endpoint["ns"], s["collections"])
                for field in endpoint["fields"]:
                    schema = s["collections"][endpoint["ns"]]["jsonSchema"]
                    for segment in field.split("."):
                        schema = schema["properties"][segment]

    def test_revised_instance_focus_relationship(self):
        model = json.loads((ROOT / "storage/schema/model.json").read_text(encoding="utf-8"))
        instances = model["collections"]["Schema.Instances"]["jsonSchema"]
        foci = model["collections"]["Schema.Foci"]["jsonSchema"]
        self.assertIn("instance", instances["required"])
        self.assertEqual(instances["properties"]["instance"]["bsonType"], ["objectId"])
        self.assertNotIn("Focus_point", instances["properties"])
        self.assertNotIn("id_instance", instances["properties"])
        self.assertNotIn("instances", foci["properties"])
        self.assertEqual(foci["properties"]["id_instance"]["bsonType"], ["objectId"])
        self.assertIn(
            [("Schema.Instances", ["instance"], None), ("Schema.Foci", ["id_instance"], 1)],
            [[(e["ns"], e["fields"], e["cardinality"]) for e in link["relationship"]]
             for link in model["relationships"]],
        )


    def test_configure_preserves_secrets_and_repeats(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("READER_PASSWORD=original\n")
            m.configure(p)
            first = p.read_bytes()
            m.configure(p)
            self.assertEqual(first, p.read_bytes())
            self.assertIn(b"READER_PASSWORD=original", first)
            self.assertTrue(m.env_values(p)["GUEST_PASSWORD"])

    def test_startup_stages(self):
        with patch.object(Path, "is_file", return_value=True), patch.object(
            m.shutil, "which", return_value="/docker"
        ), patch.object(m, "prevent_double_mount"), patch.object(m, "execute") as run:
            self.assertEqual(m.main(["up", "--connections"]), 0)
            calls = [call.args[0] for call in run.call_args_list]
            self.assertEqual(calls[0], ["stop", "backend"])
            self.assertIn("/opt/storage/provision.js", calls[2])
            self.assertIn("/opt/storage/verify.js", calls[3])
            self.assertEqual(calls[-1][-1], "backend")

    def test_health_no_auth_checks_final_pid(self):
        s = (ROOT / "storage/scripts/health.js").read_text(encoding="utf-8")
        self.assertNotIn(".auth(", s)
        self.assertIn("/proc/1/comm", s)

    def test_owner_scope_get_update(self):
        s = Store()
        r = Repository(s, Principal("alice", "user"))
        r.get("Patient", "id")
        r.update("Patient", "id", {"age": 25})
        self.assertEqual(s.c.calls[0][1][0]["_owner_id"], "alice")
        self.assertEqual(s.c.calls[1][1][0]["_owner_id"], "alice")
        self.assertFalse(s.c.calls[1][2]["upsert"])

    def test_cannot_change_or_forge_owner(self):
        r = Repository(Store(), Principal("alice", "user"))
        for fields in ({"_owner_id": "bob"}, {"_id": "x"}, {"$set": {}}, {"a.b": 1}):
            with self.assertRaises((PermissionError, ValueError)):
                r.update("Patient", "id", fields)

    def test_owner_on_insert(self):
        s = Store()
        Repository(s, Principal("alice", "user")).create("Patient", {"age": 20})
        self.assertEqual(s.c.calls[0][1][0]["_owner_id"], "alice")

    def test_guest_forbidden_collections(self):
        s = Store()
        r = Repository(s, Principal("guest", "guest"))
        for name in ("Social_group", "Street", "Building", "Placement"):
            with self.assertRaises(PermissionError):
                r.get(name, "id")
        self.assertFalse(s.c.calls)

    def test_guest_cannot_write(self):
        r = Repository(Store(), Principal("guest", "guest"))
        with self.assertRaises(PermissionError):
            r.create("Patient", {"age": 20})
        with self.assertRaises(PermissionError):
            r.update("Patient", "id", {"age": 20})

    def test_guest_allowed_collection_uses_guest_pool(self):
        s = Store()
        Repository(s, Principal("guest", "guest")).get("Patient", "id")
        self.assertEqual(s.roles, ["guest"])
        self.assertNotIn("_owner_id", s.c.calls[0][1][0])

    def test_raw_cases_not_updated(self):
        with self.assertRaises(PermissionError):
            Repository(Store(), Principal("alice", "user")).update(
                "cases", "id", {"x": 1}
            )

    def test_single_schema_source(self):
        from app.models.schema import load_schema

        self.assertEqual(
            load_schema(),
            json.loads(
                (ROOT / "storage/schema/model.json").read_text(encoding="utf-8")
            ),
        )
        self.assertEqual(
            list(ROOT.rglob("model*.json")), [ROOT / "storage/schema/model.json"]
        )

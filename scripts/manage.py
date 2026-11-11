"""Root launcher and connection registry. Python 3.10+, Docker Compose v2. See backend/app/main.py for HTTP diagnostics.
It orchestrates Storage; it is NOT an HTTP proxy or a future Requests service.
"""

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def connections():
    return {
        "storage": {"status": "implemented", "address": "storage:27017"},
        "backend": {"status": "storage-diagnostics-only", "address": "backend:8000"},
        "dashboard": {"status": "planned", "address": "dashboard:8501"},
        "qgis_plugin": {
            "status": "planned-desktop-client",
            "address": "http://127.0.0.1:8000",
        },
    }


def initialize(path):
    """Create new private .env exclusively. Never rotate an existing database password."""
    values = {
        "MONGO_ROOT_USER": "storage_admin",
        **{
            key: secrets.token_hex(24)
            for key in (
                "MONGO_ROOT_PASSWORD",
                "INGEST_PASSWORD",
                "PROCESSOR_PASSWORD",
                "READER_PASSWORD",
                "USER_PASSWORD",
                "GUEST_PASSWORD",
            )
        },
        "MONGO_PORT": "27017",
        "QGIS_ADMIN_TOKEN": secrets.token_hex(32),
        "QGIS_USER_TOKEN": secrets.token_hex(32),
        "QGIS_GUEST_TOKEN": secrets.token_hex(32),
        "DASHBOARD_TOKEN": secrets.token_hex(32),
        "ROLE_READER_PASS": secrets.token_hex(16),
        "ROLE_USER_PASS": secrets.token_hex(16),
        "ROLE_GUEST_PASS": secrets.token_hex(16),
        "STORAGE_DATA_VOLUME": "gis_data_" + secrets.token_hex(8),
        "STORAGE_CONFIG_VOLUME": "gis_config_" + secrets.token_hex(8),
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("".join(f"{k}={v}\n" for k, v in values.items()))


def env_values(path):
    """Read UTF-8/BOM dotenv; reject interpolation and malformed/duplicate keys."""
    values = {}
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid .env line {number}: expected KEY=value")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key.isidentifier() or key in values:
            raise ValueError(f"Invalid or duplicate key at .env line {number}")
        if value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        elif value.startswith('"') or "$" in value or " #" in value:
            raise ValueError(f"Use plain values or single quotes at .env line {number}")
        if any(c in value for c in ("\n", "\r", "'")):
            raise ValueError(f"Unsupported value at .env line {number}")
        values[key] = value
    return values


def compose_environment(env_file=None):
    """Use the selected dotenv consistently, ignoring inherited Compose overrides."""
    values = env_values(env_file or ROOT / ".env")
    keys = set(values) | {
        "MONGO_ROOT_USER",
        "MONGO_ROOT_PASSWORD",
        "INGEST_PASSWORD",
        "PROCESSOR_PASSWORD",
        "READER_PASSWORD",
        "USER_PASSWORD",
        "GUEST_PASSWORD",
        "STORAGE_DATA_VOLUME",
        "STORAGE_CONFIG_VOLUME",
        "MONGO_PORT",
        "TEST_WRITES",
        "QGIS_ADMIN_TOKEN",
        "QGIS_IDENTITIES_JSON",
        "QGIS_USER_TOKEN",
        "QGIS_GUEST_TOKEN", "DASHBOARD_TOKEN", "ROLE_READER_PASS", "ROLE_USER_PASS", "ROLE_GUEST_PASS",
        "COMPOSE_FILE",
        "COMPOSE_PROFILES",
        "COMPOSE_PROJECT_NAME",
        "COMPOSE_ENV_FILES",
        "COMPOSE_DISABLE_ENV_FILE",
    }
    return {key: value for key, value in os.environ.items() if key not in keys}


def configure(path):
    """Add only absent new credentials, retaining all existing secrets."""
    values = env_values(path)
    missing = [
        key
        for key in (
            "USER_PASSWORD",
            "GUEST_PASSWORD",
            "QGIS_ADMIN_TOKEN",
            "QGIS_USER_TOKEN",
            "QGIS_GUEST_TOKEN", "DASHBOARD_TOKEN", "ROLE_READER_PASS", "ROLE_USER_PASS", "ROLE_GUEST_PASS",
        )
        if key not in values
    ]
    if not missing:
        return
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".env-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(path.read_text(encoding="utf-8-sig").rstrip() + "\n")
            for key in missing:
                stream.write(key + "=" + secrets.token_hex(24) + "\n")
        os.replace(temp, path)

    finally:
        Path(temp).unlink(missing_ok=True)


def prepare_volumes():
    """Explicit opt-in for NEW deployment; up itself never creates missing production volumes."""
    values = env_values(ROOT / ".env")
    existing = set(
        subprocess.run(
            ["docker", "volume", "ls", "--format", "{{.Name}}"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.splitlines()
    )
    for key, default in [
        ("STORAGE_DATA_VOLUME", "gis-mongodb_mongo_data"),
        ("STORAGE_CONFIG_VOLUME", "gis-mongodb_mongo_config"),
    ]:
        name = values.get(key) or default
        if name not in existing:
            subprocess.run(["docker", "volume", "create", name], check=True)
        else:
            print("Using existing volume:", name)


def command(
    arguments,
    *,
    env_file=None,
    project="gis-mongodb",
    emergency=False,
    probe=False,
    local=False,
    disposable=False,
):
    """Compose command in one place: absolute files, root-relative mount paths."""
    result = [
        "docker",
        "compose",
        "--project-directory",
        str(ROOT),
        "--env-file",
        str(env_file or ROOT / ".env"),
        "-p",
        project,
        "-f",
        str(ROOT / "docker-compose.yml"),
    ]
    if emergency:
        result += ["-f", str(ROOT / "docker-compose.emergency.yml")]
    if local:
        result += ["-f", str(ROOT / "docker-compose.local.yml")]
    if probe:
        result += ["-f", str(ROOT / "tests/integration/docker-compose.test.yml")]
    if disposable:
        result += ["-f", str(ROOT / "tests/integration/docker-compose.disposable.yml")]
    return result + ["--profile", "connections"] + list(arguments)


def execute(arguments, **options):
    """Run argv without a shell; failures retain a nonzero exit code."""
    if not shutil.which("docker"):
        raise RuntimeError("Docker unavailable: integration check NOT executed")
    return subprocess.run(
        command(arguments, **options),
        cwd=ROOT,
        check=True,
        env=compose_environment(options.get("env_file")),
    )


def prevent_double_mount():
    """Never start new service against volumes used by an old running Mongo service."""
    values = env_values(ROOT / ".env")
    for key, default in [
        ("STORAGE_DATA_VOLUME", "gis-mongodb_mongo_data"),
        ("STORAGE_CONFIG_VOLUME", "gis-mongodb_mongo_config"),
    ]:
        volume = values.get(key) or default
        response = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "volume=" + volume,
                "--format",
                '{{.Label "com.docker.compose.project"}}/{{.Label "com.docker.compose.service"}}',
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if any(
            line.strip() != "gis-mongodb/storage"
            for line in response.stdout.splitlines()
        ):
            raise RuntimeError(
                "Volume used by an old running service; stop the OLD stack without deleting volumes first"
            )


def integration():
    """Fresh credentials + uniquely named disposable volumes; never write to user data."""
    project = "storage-test-" + secrets.token_hex(6)
    with tempfile.TemporaryDirectory(prefix="storage-test-") as folder:
        env_file = Path(folder) / ".env"
        initialize(env_file)
        with env_file.open("a", encoding="utf-8") as stream:
            stream.write("TEST_WRITES=1\n")
        # Shell env normally overrides dotenv in Compose. Remove every project key here.
        environment = compose_environment(env_file)
        options = dict(env_file=env_file, project=project, probe=True, disposable=True)

        def run(args):
            return subprocess.run(
                command(args, **options), env=environment, cwd=ROOT, check=True
            )

        if not shutil.which("docker"):
            raise RuntimeError("Docker unavailable: isolated integration NOT executed")
        try:
            run(
                [
                    "up",
                    "-d",
                    "--build",
                    "--wait",
                    "--wait-timeout",
                    "300",
                    "storage",
                ]
            )
            run(["exec","-T","storage","mongosh","--quiet","/opt/storage/provision.js"])
            run(["up","-d","--build","--wait","backend"])
            run(
                [
                    "exec",
                    "-T",
                    "storage",
                    "mongosh",
                    "--quiet",
                    "/opt/storage/verify.js",
                ]
            )
            run(["run", "--rm", "--no-deps", "probe"])
            run(["run", "--rm", "--no-deps", "http-probe"])
            run(["run", "--rm", "--no-deps", "qgis-http-probe"])
            run(
                [
                    "exec",
                    "-T",
                    "storage",
                    "mongosh",
                    "--quiet",
                    "/opt/storage/provision.js",
                ]
            )
            run(
                [
                    "exec",
                    "-T",
                    "storage",
                    "mongosh",
                    "--quiet",
                    "/opt/storage/verify.js",
                ]
            )
            run(["stop", "backend"])
            run(
                [
                    "exec",
                    "-T",
                    "-e",
                    "ISOLATED_STORAGE_TEST=1",
                    "-e",
                    "FIXTURE_ACTION=seed",
                    "storage",
                    "mongosh",
                    "--quiet",
                    "/opt/test/legacy.js",
                ]
            )
            run(
                [
                    "exec",
                    "-T",
                    "storage",
                    "mongosh",
                    "--quiet",
                    "/opt/migrations/rename-v7.js",
                ]
            )
            for _ in range(2):
                run(
                    [
                        "exec",
                        "-T",
                        "-e",
                        "MIGRATION_APPLY=1",
                        "storage",
                        "mongosh",
                        "--quiet",
                        "/opt/migrations/rename-v7.js",
                    ]
                )
            run(
                [
                    "exec",
                    "-T",
                    "-e",
                    "ISOLATED_STORAGE_TEST=1",
                    "-e",
                    "FIXTURE_ACTION=assert",
                    "storage",
                    "mongosh",
                    "--quiet",
                    "/opt/test/legacy.js",
                ]
            )
            run(
                [
                    "exec",
                    "-T",
                    "storage",
                    "mongosh",
                    "--quiet",
                    "/opt/storage/verify.js",
                ]
            )
            run(["restart", "storage"])
            run(["up", "-d", "--wait", "--wait-timeout", "300", "storage"])
            run(["exec","-T","storage","mongosh","--quiet","/opt/storage/replica.js"])
            # Persistence: normal read check after restart; separate assertion counts test source.
            run(
                [
                    "exec",
                    "-T",
                    "storage",
                    "mongosh",
                    "--quiet",
                    "/opt/test/persistence.js",
                ]
            )
        except subprocess.CalledProcessError:
            print("FAIL integration: collecting diagnostics", flush=True)
            for args in (
                ["ps", "-a"],
                ["logs", "--no-color", "--tail", "100", "storage", "backend"],
            ):
                subprocess.run(
                    command(args, **options), env=environment, cwd=ROOT, check=False
                )
            raise
        finally:
            # Only random, newly-created test project volumes are removed.
            original_error = sys.exc_info()[0] is not None
            try:
                run(["down", "--volumes"])
            except subprocess.CalledProcessError:
                print("WARNING: test cleanup failed for " + project, file=sys.stderr)
                if not original_error:
                    raise


def offline_tests():
    start = ROOT / "tests/unit"
    if (
        not (start / "__init__.py").is_file()
        or not (ROOT / "tests/__init__.py").is_file()
    ):
        raise RuntimeError(
            "Incomplete project: extract/clone the whole project including tests/__init__.py and tests/unit/__init__.py"
        )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(start),
            "-t",
            str(ROOT),
            "-p",
            "test_*.py",
            "-v",
        ],
        cwd=ROOT,
        check=True,
    )
    if not shutil.which("node"):
        raise RuntimeError("Node.js unavailable: init mock check NOT executed")
    subprocess.run(["node", str(ROOT / "tests/unit/static.cjs")], cwd=ROOT, check=True)
    subprocess.run(
        ["node", str(ROOT / "tests/unit/migration.cjs")], cwd=ROOT, check=True
    )
    subprocess.run(["node", str(ROOT / "tests/unit/verify.cjs")], cwd=ROOT, check=True)


def doctor():
    """Print versions without environment values or database secrets."""
    print("Python:", sys.version.split()[0], "Host:", sys.platform)
    print("Project:", ROOT)
    for argv in (
        ["node", "--version"],
        ["docker", "--version"],
        ["docker", "compose", "version"],
        ["docker", "info", "--format", "{{.OSType}}/{{.Architecture}}"],
    ):
        if not shutil.which(argv[0]):
            print(argv[0] + ": unavailable")
            continue
        subprocess.run(argv, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "init",
            "plan",
            "config",
            "up",
            "status",
            "logs",
            "stop",
            "verify",
            "provision",
            "network-test",
            "test",
            "integration",
            "configure",
            "volumes",
            "migrate-plan",
            "migrate",
            "doctor",
            "geometry",
        ],
    )
    parser.add_argument(
        "--connections",
        action="store_true",
        help="Run backend Storage connector too; up/config only",
    )
    parser.add_argument(
        "--local-api",
        action="store_true",
        help="Publish backend diagnostics on localhost:8000; requires --connections",
    )
    parser.add_argument(
        "--emergency",
        action="store_true",
        help="Add localhost MongoDB port for config/up only",
    )
    args = parser.parse_args(argv)
    if args.emergency and args.action not in ("config", "up"):
        parser.error("--emergency applies to config/up only")
    if (args.connections or args.local_api) and args.action not in ("up", "config"):
        parser.error("Connection options apply to up/config only")
    if args.local_api and not args.connections:
        parser.error("--local-api requires --connections")
    try:
        if args.action == "init":
            initialize(ROOT / ".env")
            print("Created .env; keep it private")
        elif args.action == "configure":
            configure(ROOT / ".env")
            print("Missing new credentials added; existing passwords retained")
        elif args.action == "doctor":
            doctor()
        elif args.action == "plan":
            print(json.dumps(connections(), ensure_ascii=False, indent=2))
        elif args.action == "test":
            offline_tests()
        elif args.action == "integration":
            integration()
        else:
            if not (ROOT / ".env").is_file():
                raise RuntimeError(
                    "Missing .env: run init or restore your existing .env"
                )
            if not shutil.which("docker"):
                raise RuntimeError(
                    "Docker unavailable; no container operation executed"
                )
            if args.action == "volumes":
                prepare_volumes()
            elif args.action in ("migrate-plan", "migrate"):
                prevent_double_mount()
                execute(["stop", "backend"])
                execute(["up", "-d", "--wait", "--wait-timeout", "300", "storage"])
                execute(["exec","-T","storage","mongosh","--quiet","/opt/storage/replica.js"])
                execute(
                    [
                        "exec",
                        "-T",
                        "-e",
                        "MIGRATION_APPLY=" + ("1" if args.action == "migrate" else "0"),
                        "storage",
                        "mongosh",
                        "--quiet",
                        "/opt/migrations/rename-v7.js",
                    ]
                )
            elif args.action == "up":
                prevent_double_mount()
                execute(["stop", "backend"])
                execute(
                    ["up", "-d", "--wait", "--wait-timeout", "300", "storage"],
                    emergency=args.emergency,
                )
                execute(
                    [
                        "exec",
                        "-T",
                        "storage",
                        "mongosh",
                        "--quiet",
                        "/opt/storage/provision.js",
                    ]
                )
                execute(
                    [
                        "exec",
                        "-T",
                        "storage",
                        "mongosh",
                        "--quiet",
                        "/opt/storage/verify.js",
                    ]
                )
                execute(["--profile","import","build","excel-import"])
                execute(["--profile","import","run","--rm","--no-deps","excel-import","python","-m","app.modules.seed"])
                execute(["exec","-T","storage","mongosh","--quiet","/opt/storage/geospatial-index.js"])
                if args.connections:
                    execute(
                        [
                            "up",
                            "-d",
                            "--build",
                            "--no-deps",
                            "--wait",
                            "--wait-timeout",
                            "300",
                            "backend",
                            "dashboard",
                        ],
                        emergency=args.emergency,
                        local=args.local_api,
                    )
            elif args.action == "config":
                execute(
                    (["--profile", "connections"] if args.connections else [])
                    + ["config", "--quiet"],
                    emergency=args.emergency,
                    local=args.local_api,
                )
            elif args.action == "status":
                execute(["ps", "-a"])
            elif args.action == "logs":
                execute(["logs", "--tail", "100", "storage"])
            elif args.action == "stop":
                execute(["stop", "dashboard", "backend", "storage"])
            elif args.action in ("verify", "provision"):
                execute(
                    [
                        "exec",
                        "-T",
                        "storage",
                        "mongosh",
                        "--quiet",
                        "/opt/storage/" + args.action + ".js",
                    ]
                )
            elif args.action == "geometry":
                execute(["exec","-T","storage","mongosh","--quiet","/opt/storage/geospatial-index.js"])
            elif args.action == "network-test":
                # Force read-only probe even if parent shell defines TEST_WRITES=1.
                execute(
                    ["run", "--rm", "--no-deps", "-e", "TEST_WRITES=0", "probe"],
                    probe=True,
                )
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(
            "ERROR:",
            (
                str(error)
                if not isinstance(error, subprocess.CalledProcessError)
                else "Command failed; check preceding output"
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

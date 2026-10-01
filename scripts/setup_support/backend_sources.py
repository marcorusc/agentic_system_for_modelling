"""Pinned local backend sources and installed provenance; no modelling imports."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import tomllib
from urllib.parse import unquote, urlparse

from scripts.codex.ode_artifacts import read_json
from .detect import run
from .state import SetupError, atomic_write

NAMES = {"nekomata", "mcp-biomodelling-servers"}
RECEIPT = ".setup-backend-sources.json"


def validate_sources(entries: list[dict]) -> None:
    for entry in entries:
        path = Path(entry["path"])
        top = Path(run(["git", "rev-parse", "--show-toplevel"], cwd=path).stdout.strip()).resolve()
        if top != path or run(["git", "rev-parse", "HEAD"], cwd=path).stdout.strip() != entry["commit"]:
            raise SetupError(f"Backend source is not at its pinned commit: {path}")
        if run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=path).stdout.strip():
            raise SetupError(f"Backend source has uncommitted files: {path}")
        metadata = tomllib.loads((path / "pyproject.toml").read_text())
        package = metadata.get("project", metadata.get("tool", {}).get("poetry", {}))
        if package.get("name") != entry["name"] or package.get("version") != entry["version"]:
            raise SetupError(f"Backend source package identity differs from manifest: {path}")


def validate_versions(entries: list[dict], manifest: dict) -> None:
    expected = {**manifest.get("dependency_pins", {}), manifest["package"]: manifest["version"]}
    for entry in entries:
        if entry["name"] in expected and entry["version"] != expected[entry["name"]]:
            raise SetupError(f"Backend {entry['name']} version must match setup/dependencies.toml "
                             f"({expected[entry['name']]})")


def load(path: Path, manifest: dict) -> list[dict]:
    data = read_json(path)
    if set(data) != {"schema_version", "packages"} or type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise SetupError("Expected backend-source manifest schema_version=1 and packages")
    packages = data["packages"]
    if not isinstance(packages, list) or len(packages) != 2:
        raise SetupError("Pin both nekomata and mcp-biomodelling-servers")
    entries = []
    for entry in packages:
        if not isinstance(entry, dict) or set(entry) != {"name", "version", "path", "commit"}:
            raise SetupError("Each backend source requires name, version, path and commit")
        if any(not isinstance(v, str) or not v.strip() or "\x00" in v for v in entry.values()):
            raise SetupError("Backend source fields must be nonempty strings")
        if not re.fullmatch(r"[0-9a-f]{40}", entry["commit"]):
            raise SetupError("Backend commit must be a full lowercase 40-character Git ID")
        source = Path(entry["path"]).expanduser()
        source = (path.parent / source if not source.is_absolute() else source).resolve(strict=True)
        entries.append({**entry, "path": str(source)})
    if {e["name"] for e in entries} != NAMES:
        raise SetupError("Pin each supported backend exactly once")
    validate_versions(entries, manifest)
    validate_sources(entries)
    return sorted(entries, key=lambda e: e["name"])


def unpack(archive: Path, target: Path) -> None:
    """Accept only committed regular files/directories, never archive links."""
    target.mkdir()
    with tarfile.open(archive) as stream:
        for member in stream:
            relative = Path(member.name)
            if relative.is_absolute() or ".." in relative.parts or not (member.isdir() or member.isfile()):
                raise SetupError("Backend Git archive contains an unsafe member")
            destination = target / relative
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with stream.extractfile(member) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output)
                destination.chmod(0o755 if member.mode & 0o111 else 0o644)


@contextmanager
def snapshots(entries: list[dict]):
    validate_sources(entries)
    with tempfile.TemporaryDirectory(prefix="biomodelling-sources-") as temporary:
        directory = Path(temporary)
        paths = {}
        for entry in entries:
            archive = directory / (entry["name"] + ".tar")
            run(["git", "archive", "--format=tar", "--output", str(archive), entry["commit"]], cwd=Path(entry["path"]))
            target = directory / entry["name"]
            unpack(archive, target)
            paths[entry["name"]] = target
        # A changing checkout cannot silently change the user's selected inputs.
        validate_sources(entries)
        yield paths


def inspect_installed(prefix: Path) -> dict:
    helper = Path(__file__).with_name("inspect_backend_install.py")
    return json.loads(run([str(prefix / "bin/python"), "-I", "-B", str(helper)], timeout=120).stdout)


def write_receipt(prefix: Path, entries: list[dict], paths: dict[str, Path]) -> None:
    installed = inspect_installed(prefix)
    for entry in entries:
        package = installed[entry["name"]]
        url = package["direct_url"].get("url", "")
        parsed = urlparse(url)
        if (package["version"] != entry["version"] or parsed.scheme != "file"
                or parsed.netloc not in {"", "localhost"}
                or Path(unquote(parsed.path)).resolve() != paths[entry["name"]].resolve()
                or package["direct_url"].get("dir_info", {}).get("editable", False)):
            raise SetupError("Installed backend does not identify the selected committed snapshot")
    atomic_write(prefix / RECEIPT, json.dumps({"schema_version": 1, "sources": entries,
                 "installed": installed}, indent=2).encode())


def verify_receipt(prefix: Path, entries: list[dict]) -> dict:
    try:
        receipt = read_json(prefix / RECEIPT)
        if receipt.get("schema_version") != 1 or receipt.get("sources") != entries:
            raise SetupError("Installed backend source receipt differs from selected commits")
        installed = inspect_installed(prefix)
        if installed != receipt.get("installed"):
            raise SetupError("Installed backend content or provenance changed; use a new environment")
        return {"passed": True, "sources": entries, "errors": []}
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {"passed": False, "errors": [str(error)]}

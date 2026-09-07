#!/usr/bin/env python3
"""Install and configure the local biological-modelling workflow (Linux/WSL)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Also permits invocation by absolute path from outside the project.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if sys.version_info < (3, 11):
    raise SystemExit("Setup requires Python 3.11+; on Windows run it inside WSL.")

import tomllib
from scripts.setup_support import configure_claude, configure_codex, detect, environment, verify
from scripts.setup_support.state import SetupError, atomic_write, read_json, write_config


INPUT_KEYS = {"client", "env_prefix", "manager", "codex_path", "claude_path", "codex_home",
              "manager_path", "package_source"}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--client", choices=("codex", "claude", "both"))
    p.add_argument("--manager", choices=("auto", "conda", "venv"))
    for name in ("env-prefix", "codex-path", "claude-path", "codex-home", "manager-path", "package-source"):
        p.add_argument("--" + name)
    p.add_argument("--config", type=Path, help="JSON path overrides; no credentials")
    p.add_argument("--non-interactive", action="store_true")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--check", action="store_true")
    return p


def settings(args, root: Path) -> dict:
    saved = read_json(root/".setup/local.json")
    values = {key: value for key, value in saved.items() if key in INPUT_KEYS}
    original_manager = values.get("manager")
    supplied = {}
    if args.config:
        if not args.config.is_file():
            raise SetupError(f"Input configuration is missing: {args.config}")
        supplied = read_json(args.config)
        unknown = supplied.keys() - INPUT_KEYS
        if unknown:
            raise SetupError(f"Unknown setup settings: {', '.join(sorted(unknown))}")
        values.update(supplied)
    for key in INPUT_KEYS:
        if getattr(args, key, None) is not None:
            values[key] = getattr(args, key)
    if values.get("manager") != original_manager and "manager_path" not in supplied and args.manager_path is None:
        values.pop("manager_path", None)
    if any(not isinstance(value, str) or not value.strip() or "\x00" in value for value in values.values()):
        raise SetupError("Setup settings must be nonempty strings")
    if values.get("client") not in (None, "codex", "claude", "both"):
        raise SetupError("client must be codex, claude, or both")
    if values.get("manager", "auto") not in ("auto", "conda", "venv"):
        raise SetupError("manager must be auto, conda, or venv")
    return values


def plan(args, root: Path, manifest: dict) -> tuple[dict, list[str]]:
    values = settings(args, root)
    system = detect.system_info()
    errors = []
    if system["system"] not in manifest["supported_systems"]:
        errors.append("This installer supports Linux/WSL. Run inside WSL on Windows; native Windows/macOS are not validated.")
    if not detect.discover("git"):
        errors.append("Git is missing; install Git and rerun setup")
    interactive = sys.stdin.isatty() and not (args.non_interactive or args.check or args.dry_run)
    clients = {}
    for name in ("codex", "claude"):
        if values.get("client") in ("codex", "claude") and name != values["client"]:
            continue
        override = values.get(name + "_path")
        try:
            found = detect.discover(name, override)
            if found:
                clients[name] = found
        except SetupError as error:
            errors.append(str(error))
    selection = values.get("client")
    if selection is None:
        if len(clients) == 1:
            selection = next(iter(clients))
        elif interactive:
            selection = input("Configure codex, claude, or both? ").strip().lower()
        else:
            errors.append("Select --client codex, --client claude, or --client both")
    selected = ("codex", "claude") if selection == "both" else (selection,) if selection in ("codex", "claude") else ()
    if selection is not None and not selected:
        errors.append("Invalid client selection")
    versions = {}
    for name in selected:
        if name not in clients and interactive:
            entered = input(f"Path to the {name} executable: ").strip()
            if entered:
                try:
                    clients[name] = detect.discover(name, entered)
                except SetupError as error:
                    errors.append(str(error))
        if name not in clients:
            errors.append(f"{name} is missing; install it or supply --{name}-path")
        else:
            try:
                versions[name] = detect.client_version(name, clients[name])
            except SetupError as error:
                errors.append(str(error))
    clients = {name: clients[name] for name in selected if name in clients}
    prefix = Path(values.get("env_prefix", str(root/".setup/environment"))).expanduser().absolute()
    manager = values.get("manager", "auto")
    manager_path = values.get("manager_path")
    if manager == "auto":
        manager = "conda" if detect.discover("conda") else "venv"
    try:
        executable = detect.discover("conda", manager_path) if manager == "conda" else detect.discover("python", manager_path or sys.executable)
    except SetupError as error:
        errors.append(str(error))
        executable = None
    if not executable:
        errors.append(f"Missing environment manager {manager}; supply --manager-path")
    elif manager == "venv" and manager_path:
        version = detect.client_version("python", executable)
        if tuple(map(int, version.split("."))) < (3, 11):
            errors.append("The selected venv Python must be 3.11 or newer")
    if manager == "venv" and not detect.discover("dot"):
        errors.append("Graphviz dot is missing; install Graphviz or select --manager conda")
    source = values.get("package_source")
    if source:
        source_path = Path(source).expanduser().absolute()
        metadata = source_path/"pyproject.toml"
        if not metadata.is_file():
            errors.append("--package-source must be a local source directory containing pyproject.toml")
        else:
            package = tomllib.loads(metadata.read_text())["project"]
            if package.get("name") != manifest["package"] or package.get("version") != manifest["version"]:
                errors.append("Local package source does not match the pinned package name/version")
        source = str(source_path)
    home = str(Path(values.get("codex_home", os.environ.get("CODEX_HOME", str(Path.home()/".codex")))).expanduser().absolute())
    resolved = {"client": selection, "clients": clients, "client_versions": versions,
                "system": system, "env_prefix": str(prefix), "manager": manager,
                "manager_path": executable, "codex_home": home, "package_source": source,
                "package": f'{manifest["package"]}=={manifest["version"]}'}
    return resolved, errors


def execute(args, root: Path = ROOT) -> dict:
    manifest = tomllib.loads((root/"setup/dependencies.toml").read_text())
    resolved, errors = plan(args, root, manifest)
    report = {"schema_version": 1, "mode": "check" if args.check else "plan" if args.dry_run else "setup",
              "plan": resolved, "errors": errors, "passed": False}
    if errors:
        return report
    prefix = Path(resolved["env_prefix"])
    outputs = {}
    if "codex" in resolved["clients"]:
        outputs.update(configure_codex.render(root, prefix, Path(resolved["codex_home"])))
    if "claude" in resolved["clients"]:
        outputs.update(configure_claude.render(root, prefix))
    report["configuration_files"] = [str(path) for path in outputs]
    if args.dry_run:
        report["passed"] = True
        return report
    if not args.check:
        print("Preparing modelling environment…", file=sys.stderr, flush=True)
        environment.install(prefix, resolved["manager"], resolved["manager_path"], manifest, resolved["package_source"])
    report["environment"] = environment.verify_environment(prefix, manifest)
    if not report["environment"]["passed"]:
        report["errors"].extend(report["environment"]["errors"])
        return report
    if args.check:
        for path, text in outputs.items():
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                errors.append(f"Configuration missing or stale: {path}; rerun setup")
        if errors:
            return report
    else:
        report["writes"] = [write_config(path, text, root/".setup/backups") for path, text in outputs.items()]
        saved = {key: resolved[key] for key in INPUT_KEYS if resolved.get(key)}
        saved.update({name + "_path": path for name, path in resolved["clients"].items()})
        atomic_write(root/".setup/local.json", json.dumps(saved, indent=2).encode())
        atomic_write(root/".setup/generated-files.json", json.dumps(report["writes"], indent=2).encode())
    previous_home = os.environ.get("CODEX_HOME")
    try:
        os.environ["CODEX_HOME"] = resolved["codex_home"]
        if "codex" in resolved["clients"]:
            configure_codex.ensure_plugin(root, resolved["clients"]["codex"], check=args.check)
        print("Checking MCP startup and client inventories…", file=sys.stderr, flush=True)
        report["verification"] = verify.verify(root, prefix, resolved["clients"])
    finally:
        if previous_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = previous_home
    errors.extend(report["verification"]["errors"])
    report["passed"] = not errors
    if not args.check:
        atomic_write(root/".setup/report.json", json.dumps(report, indent=2).encode())
    return report


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        report = execute(args)
    except (SetupError, OSError, ValueError, KeyError) as error:
        report = {"passed": False, "errors": [str(error)]}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

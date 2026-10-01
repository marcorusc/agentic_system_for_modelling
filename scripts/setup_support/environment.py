"""Dedicated environment installation; never modify the caller's environment."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from . import backend_sources as source_support
from .detect import run
from .state import SetupError, atomic_write


def install(prefix: Path, manager: str, manager_path: str, manifest: dict,
            source: str | None = None, *, backend_sources: list[dict] | None = None) -> None:
    if prefix.is_symlink():
        raise SetupError(f"Refusing symlink environment: {prefix}")
    marker = prefix.parent / ("." + prefix.name + ".biomodelling-setup.json")
    if prefix.exists() and not marker.is_file():
        raise SetupError(f"Environment already exists and is not setup-managed: {prefix}; choose a new --env-prefix")
    desired = {"package": manifest["package"], "version": manifest["version"],
               "manager": manager, "source": source}
    if backend_sources:
        if source:
            raise SetupError("Cannot mix backend sources and package source")
        source_support.validate_sources(backend_sources)
        desired["backend_sources"] = backend_sources
    if marker.is_file() and json.loads(marker.read_text()) != desired:
        raise SetupError("Environment specification changed; choose a new --env-prefix to upgrade")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        atomic_write(marker, json.dumps(desired).encode())
    if not (prefix/"bin/python").is_file():
        if manager == "conda":
            run([manager_path, "create", "--yes", "--prefix", str(prefix),
                 "--override-channels", "--channel", "conda-forge",
                 "python=" + manifest["python_environment"], "pip", "graphviz"], timeout=1800)
        else:
            run([manager_path, "-m", "venv", str(prefix)], timeout=180)
    python = str(prefix/"bin/python")
    requirement = source or f'{manifest["package"]}=={manifest["version"]}'
    # A completed environment is reused; verification checks for drift.
    if not (prefix/".setup-installed").exists():
        if backend_sources:
            with source_support.snapshots(backend_sources) as paths:
                run([python, "-m", "pip", "install", "--index-url", manifest["index_url"],
                     *[str(paths[e["name"]]) for e in backend_sources]], timeout=1800)
                source_support.write_receipt(prefix, backend_sources, paths)
        else:
            run([python, "-m", "pip", "install", "--index-url", manifest["index_url"], requirement], timeout=1800)
        run([python, "-m", "pip", "check"], timeout=60)
        frozen = run([python, "-m", "pip", "freeze"], timeout=60).stdout
        atomic_write(prefix/"resolved-requirements.txt", frozen.encode())
        atomic_write(prefix/".setup-installed", b"installed\n")


def transport_path(prefix: Path, *, graphviz_path: str | None = None) -> str:
    """Keep explicit dependency directories without inheriting transient helpers."""
    external = [str(Path(graphviz_path).expanduser().absolute().parent)] if graphviz_path else []
    return os.pathsep.join(dict.fromkeys([str(prefix / "bin"), *external,
        "/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"]))


def runtime_env(prefix: Path, *, graphviz_path: str | None = None) -> dict:
    inherited = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    return {**inherited, "PATH": transport_path(prefix, graphviz_path=graphviz_path),
            "CONDA_PREFIX": str(prefix), "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}


def verify_environment(prefix: Path, manifest: dict, *, graphviz_path: str | None = None) -> dict:
    errors = []
    python = prefix/"bin/python"
    versions = {}
    if not python.is_file():
        return {"passed": False, "errors": [f"Missing environment Python: {python}"]}
    program = "import importlib, importlib.metadata as m, json, sys; "
    program += f"[importlib.import_module(n) for n in {manifest['imports']!r}]; "
    program += f"print(json.dumps({{'version':m.version({manifest['package']!r}), 'python':list(sys.version_info[:3])}}))"
    try:
        with tempfile.TemporaryDirectory(prefix="biomodelling-imports-") as temporary:
            versions = json.loads(run([str(python), "-I", "-B", "-c", program], cwd=Path(temporary), env={**runtime_env(prefix, graphviz_path=graphviz_path), "NUMBA_CACHE_DIR": str(Path(temporary)/"numba-cache")}, timeout=120).stdout)
        if tuple(versions["python"]) < (3, 11):
            errors.append("The modelling environment Python must be 3.11 or newer")
        if versions["version"] != manifest["version"]:
            errors.append(f"Expected {manifest['package']} {manifest['version']}, found {versions['version']}")
        run([str(python), "-m", "pip", "check"], env=runtime_env(prefix, graphviz_path=graphviz_path), timeout=60)
    except (SetupError, ValueError, KeyError, TypeError) as error:
        errors.append(str(error))
    for name in manifest["executables"]:
        file = prefix/"bin"/name
        if not file.is_file() or not os.access(file, os.X_OK):
            errors.append(f"Missing executable: {file}")
    try:
        run(["dot", "-V"], env=runtime_env(prefix, graphviz_path=graphviz_path))
    except SetupError:
        errors.append("Graphviz dot is missing; use --manager conda or install Graphviz before using venv")
    return {"passed": not errors, "errors": errors, "versions": versions}

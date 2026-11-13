"""Pinned Python environments for the data-analyst specialist."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

DATA_ENV = Path(".venv-data")
CP_ENV = Path(".venv-cellprofiler")
DATA_PYTHON_VERSION = "3.12"
LOCK = Path("setup/data-requirements.lock")
CP_REQUIREMENTS = Path("setup/data-requirements-cellprofiler.txt")
IMPORT_PROBE = "import pydeseq2, gseapy, anndata, decoupler, sklearn, statsmodels, pint, uncertainties, gget, seaborn, matplotlib, pypdf, openpyxl"
# Run with the data env's own interpreter: its Python major.minor and installed distributions.
METADATA_PROBE = (
    "import json, sys, importlib.metadata as m\n"
    "d = {}\n"
    "for x in m.distributions():\n"
    "    n = x.metadata['Name']\n"
    "    if n: d.setdefault(n, []).append(x.version)\n"
    "print(json.dumps({'python': '%d.%d' % sys.version_info[:2], 'distributions': d}))"
)
PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)")


def data_python(root: Path) -> Path:
    return Path(root)/DATA_ENV/"bin/python"


def lock_sha256(root: Path) -> str:
    return hashlib.sha256((Path(root)/LOCK).read_bytes()).hexdigest()


def _cellprofiler_python(root: Path) -> str:
    first = (Path(root)/CP_REQUIREMENTS).read_text(encoding="utf-8").splitlines()[0]
    match = re.fullmatch(r"#\s*python=(\d+\.\d+)", first.strip())
    if not match:
        raise ValueError(f"{CP_REQUIREMENTS} line 1 must be '# python=3.X'")
    return match.group(1)


def normalize(name: str) -> str:
    """PEP 503 project-name normalisation."""
    return re.sub(r"[-_.]+", "-", name).lower()


def lock_pins(root: Path) -> dict[str, str]:
    pins = {}
    for number, raw in enumerate((Path(root)/LOCK).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = PIN.fullmatch(line)
        if match is None:
            raise ValueError(f"{LOCK}:{number}: unsupported lock line (expected name==version): {raw.strip()}")
        pins[normalize(match.group(1))] = match.group(2)
    return pins


def lock_errors(root: Path, python: Path) -> list[str]:
    """Compare the installed data env with DATA_PYTHON_VERSION and every lock pin."""
    pins = lock_pins(root)
    proc = subprocess.run([str(python), "-E", "-s", "-c", METADATA_PROBE], check=True,
                          capture_output=True, text=True)
    data = json.loads(proc.stdout)
    installed: dict[str, list[str]] = {}
    for name, versions in data["distributions"].items():
        installed.setdefault(normalize(name), []).extend(versions)
    errors = []
    if data["python"] != DATA_PYTHON_VERSION:
        errors.append(f"Data environment Python is {data['python']}, expected {DATA_PYTHON_VERSION}")
    for name, version in sorted(pins.items()):
        found = installed.get(name)
        if not found:
            errors.append(f"Data environment is missing locked package {name}=={version}")
        elif found != [version]:
            errors.append(f"Data environment has {name} {', '.join(found)}, lock requires {version}")
    return errors


def ensure(root: Path, uv: str, *, check: bool, with_cellprofiler: bool) -> dict:
    root = Path(root)
    python = data_python(root)
    result = {"passed": False, "errors": [], "python": None, "lock_sha256": lock_sha256(root), "cellprofiler": None}
    try:
        if not check:
            if not python.exists():  # uv venv refuses an existing environment
                subprocess.run([uv, "venv", str(root/DATA_ENV), "--python", DATA_PYTHON_VERSION], check=True)
            subprocess.run([uv, "pip", "sync", "--python", str(python), str(root/LOCK)], check=True)
        subprocess.run([str(python), "-E", "-s", "-c", IMPORT_PROBE], check=True)
        result["errors"].extend(lock_errors(root, python))
        result["python"] = str(python)
        if with_cellprofiler:
            cp = root/CP_ENV
            if not check:
                if not (cp/"bin/python").exists():
                    subprocess.run([uv, "venv", str(cp), "--python", _cellprofiler_python(root)], check=True)
                subprocess.run([uv, "pip", "install", "--python", str(cp/"bin/python"), "-r",
                                str(root/CP_REQUIREMENTS)], check=True)
            subprocess.run([str(cp/"bin/cellprofiler"), "--version"], check=True)
            result["cellprofiler"] = str(cp/"bin/cellprofiler")
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        result["errors"].append(f"Data environment failed: {error}")
        return result
    result["passed"] = not result["errors"]
    return result

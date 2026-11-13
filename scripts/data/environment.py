"""Pinned Python environments for the data-analyst specialist."""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

DATA_ENV = Path(".venv-data")
CP_ENV = Path(".venv-cellprofiler")
DATA_PYTHON_VERSION = "3.12"
LOCK = Path("setup/data-requirements.lock")
CP_REQUIREMENTS = Path("setup/data-requirements-cellprofiler.txt")
IMPORT_PROBE = "import pydeseq2, gseapy, anndata, decoupler, sklearn, statsmodels, pint, uncertainties, gget, seaborn, matplotlib, pypdf, openpyxl"


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
    except (subprocess.CalledProcessError, OSError, ValueError) as error:
        result["errors"].append(f"Data environment failed: {error}")
        return result
    result["passed"] = True
    return result

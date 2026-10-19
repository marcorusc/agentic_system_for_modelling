"""Compatibility entry point; provider-neutral implementation is in scripts.capture."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.capture import record_neko_ode_handoff as _implementation
if __name__ == '__main__':
    raise SystemExit(_implementation.main())
sys.modules[__name__] = _implementation

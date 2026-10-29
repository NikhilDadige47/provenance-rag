"""P9-T4 dependency audit: pip-audit (Python) then npm audit (frontend).

Usage:

    python scripts/audit_deps.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend-react"


def _run(command: list[str], cwd: Path | None = None) -> int:
    print(f"+ {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, check=False)
    return result.returncode


def main() -> int:
    py = sys.executable
    status = _run(
        [py, "-m", "pip_audit", "--progress-spinner", "off", "--skip-editable", str(ROOT)]
    )
    npm = shutil.which("npm")
    if npm and FRONTEND.is_dir():
        npm_status = _run([npm, "audit", "--omit=dev"], cwd=FRONTEND)
        status = status or npm_status
    elif not npm:
        print("npm_missing skip=frontend")
    return status


if __name__ == "__main__":
    sys.exit(main())

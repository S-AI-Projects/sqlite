"""Course check for R08-T038 – Scrabble Score path validation.

This script is a thin wrapper that runs the dedicated checker
`work/R08-T038/check.py`. It exists so that the Antigravity
`tools/course_checks/` discovery can locate a callable for the task.
"""

import subprocess
import sys
from pathlib import Path

def main() -> int:
    """Execute the checker and forward its exit status.

    The checker performs all validation, generates evidence files
    under ``work/R08-T038`` and prints a short summary.  This wrapper
    simply invokes it with the same working directory.
    """
    repo_root = Path(__file__).resolve().parents[2]
    checker = repo_root / "work" / "R08-T038" / "check.py"
    if not checker.is_file():
        print("Checker script not found: {}".format(checker), file=sys.stderr)
        return 1
    result = subprocess.run([sys.executable, str(checker)], cwd=repo_root)
    return result.returncode

if __name__ == "__main__":
    sys.exit(main())

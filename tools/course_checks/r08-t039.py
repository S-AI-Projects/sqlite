"""Course check for R08‑T039 – Collatz Conjecture path validation.

This wrapper simply runs the dedicated checker in `work/R08‑T039/check.py`.
"""
import subprocess, sys, pathlib

def main():
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    checker = repo_root / 'work' / 'R08‑T039' / 'check.py'
    if not checker.is_file():
        print(f'Checker not found at {checker}', file=sys.stderr)
        return 1
    result = subprocess.run([sys.executable, str(checker)], cwd=repo_root)
    return result.returncode

if __name__ == '__main__':
    sys.exit(main())

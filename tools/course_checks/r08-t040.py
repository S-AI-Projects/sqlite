#!/usr/bin/env python3
import subprocess, sys, pathlib

def main():
    # Resolve path to the check script for R08-T040
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    check_script = repo_root / 'work' / 'R08-T040' / 'check.py'
    if not check_script.is_file():
        sys.exit(f'Check script not found: {check_script}')
    # Run the check script using the same Python interpreter
    result = subprocess.run([sys.executable, str(check_script)])
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()

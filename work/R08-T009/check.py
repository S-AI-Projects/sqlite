#!/usr/bin/env python3
"""Assignment entry point for the matching-brackets isolated runner."""

from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).resolve().parents[2] / "tools/course_checks/r08-t009.py"), run_name="__main__")

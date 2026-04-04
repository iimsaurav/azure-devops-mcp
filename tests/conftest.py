"""Pytest config for local source imports."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = str(ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

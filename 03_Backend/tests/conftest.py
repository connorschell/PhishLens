"""Puts this directory on sys.path so app_import (the package-name shim) can be
imported, and makes the repository importable for the model modules."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (HERE, ROOT, ROOT / "01_Data" / "src", ROOT / "02_Model"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

"""Pytest top-level conftest: make ``src/`` importable without installation."""
from __future__ import annotations

import os
import sys

_SRC = os.path.join(os.path.dirname(__file__), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

"""
Domain-specific adapters for CSV Getter.

Each file in this directory contains an adapter for a specific video listing site.
Adapters are auto-registered when imported.
"""

import os
import importlib
from pathlib import Path

# Auto-discover and import all domain adapters
_current_dir = Path(__file__).parent
for _file in _current_dir.glob("*.py"):
    if _file.name.startswith("_"):
        continue
    _module_name = _file.stem
    try:
        importlib.import_module(f".domains.{_module_name}", package="csv_getter.adapters")
    except ImportError:
        pass

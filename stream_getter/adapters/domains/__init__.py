"""
Domain-specific adapters.

Each file in this directory contains an adapter for a specific video site.
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
        importlib.import_module(f".domains.{_module_name}", package="stream_getter.adapters")
    except ImportError as e:
        # Skip if import fails (e.g., missing dependencies)
        pass

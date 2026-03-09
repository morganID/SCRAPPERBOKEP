"""
Scraper CLI - Command-line interface.
"""

from .parser import create_parser
from .main import run_cli

__all__ = [
    "create_parser",
    "run_cli",
]

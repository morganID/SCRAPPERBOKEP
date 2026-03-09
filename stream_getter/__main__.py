"""
Entry point for running the scraper as a module.

Usage:
    python -m scraper --url https://example.com/video
    python -m scraper --batch urls.txt
    python -m scraper --csv data.csv
"""

from stream_getter.cli import run_cli

if __name__ == '__main__':
    run_cli()

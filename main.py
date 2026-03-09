#!/usr/bin/env python3
"""
Video Scraper - Main Entry Point

This is a backward-compatible entry point that uses the new modular scraper package.
For new code, consider using `from scraper import VideoScraper` directly.
"""

from stream_getter.cli import run_cli

if __name__ == '__main__':
    run_cli()

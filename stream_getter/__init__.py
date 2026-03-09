"""
Video Scraper Package - Modular video scraping library.

A scalable, well-organized video scraping library for extracting
HLS (M3U8) streams from video pages.

Example usage:
    from scraper import VideoScraper
    
    scraper = VideoScraper()
    await scraper.start_browser()
    m3u8_urls = await scraper.scrape("https://example.com/video")
    await scraper.close()
"""

from .core import VideoScraper, BrowserManager, NetworkInterceptor
from .pipeline import BatchPipeline, CSVPipeline
from .cli import run_cli
from .utils import (
    sanitize_filename,
    unique_output,
    validate_url,
    ScraperError,
    BrowserError,
    DownloadError,
    UploadError,
    ValidationError,
)

__version__ = "2.0.0"

__all__ = [
    # Core
    "VideoScraper",
    "BrowserManager",
    "NetworkInterceptor",
    # Pipeline
    "BatchPipeline",
    "CSVPipeline",
    # CLI
    "run_cli",
    # Utils
    "sanitize_filename",
    "unique_output",
    "validate_url",
    # Exceptions
    "ScraperError",
    "BrowserError",
    "DownloadError",
    "UploadError",
    "ValidationError",
]

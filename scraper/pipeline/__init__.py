"""
Scraper Pipeline - Processing pipelines for batch and CSV operations.
"""

from .batch import BatchPipeline
from .csv import CSVPipeline
from .downloader import VideoDownloader, download_video, download_direct, pick_best_url
from .uploader import StreamtapeUploader, upload_to_streamtape, upload_multiple
from .csv_helper import (
    read_csv,
    save_csv,
    detect_url_column,
    ensure_columns,
    get_pending_rows,
    print_summary,
)

__all__ = [
    # Pipelines
    "BatchPipeline",
    "CSVPipeline",
    # Downloader
    "VideoDownloader",
    "download_video",
    "download_direct",
    "pick_best_url",
    # Uploader
    "StreamtapeUploader",
    "upload_to_streamtape",
    "upload_multiple",
    # CSV Helper
    "read_csv",
    "save_csv",
    "detect_url_column",
    "ensure_columns",
    "get_pending_rows",
    "print_summary",
]

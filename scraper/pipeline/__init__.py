"""
Scraper Pipeline - Processing pipelines for batch and CSV operations.
"""

from .batch import BatchPipeline
from .csv import CSVPipeline

__all__ = [
    "BatchPipeline",
    "CSVPipeline",
]

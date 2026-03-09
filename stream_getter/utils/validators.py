"""
Input validation utilities for the scraper.
"""

import os
import re
from pathlib import Path
from typing import Optional

from .exceptions import ValidationError


def validate_url(url: str) -> bool:
    """
    Validate if a string is a valid URL.
    
    Args:
        url: The URL string to validate.
        
    Returns:
        True if valid, raises ValidationError otherwise.
        
    Raises:
        ValidationError: If URL is invalid.
    """
    if not url or not isinstance(url, str):
        raise ValidationError("URL cannot be empty")
    
    url = url.strip()
    if not url:
        raise ValidationError("URL cannot be empty")
    
    # Basic URL pattern
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    if not url_pattern.match(url):
        raise ValidationError(f"Invalid URL format: {url}")
    
    return True


def validate_file_path(path: str, must_exist: bool = False) -> bool:
    """
    Validate a file path.
    
    Args:
        path: The file path to validate.
        must_exist: Whether the file must already exist.
        
    Returns:
        True if valid, raises ValidationError otherwise.
        
    Raises:
        ValidationError: If path is invalid.
    """
    if not path or not isinstance(path, str):
        raise ValidationError("File path cannot be empty")
    
    path = path.strip()
    if not path:
        raise ValidationError("File path cannot be empty")
    
    if must_exist and not os.path.exists(path):
        raise ValidationError(f"File does not exist: {path}")
    
    return True


def validate_csv_column(column: str, allowed_columns: list[str]) -> str:
    """
    Validate and normalize CSV column name.
    
    Args:
        column: The column name to validate.
        allowed_columns: List of allowed column names.
        
    Returns:
        The validated column name.
        
    Raises:
        ValidationError: If column is not in allowed list.
    """
    if column not in allowed_columns:
        raise ValidationError(
            f"Invalid column '{column}'. Allowed: {allowed_columns}"
        )
    return column


def validate_output_dir(path: str) -> str:
    """
    Validate output directory, creating if needed.
    
    Args:
        path: The directory path.
        
    Returns:
        The validated directory path.
        
    Raises:
        ValidationError: If path is invalid or not writable.
    """
    if not path:
        raise ValidationError("Output directory cannot be empty")
    
    path = path.strip()
    
    try:
        os.makedirs(path, exist_ok=True)
    except PermissionError:
        raise ValidationError(f"Cannot write to directory: {path}")
    except OSError as e:
        raise ValidationError(f"Invalid directory path: {path} - {e}")
    
    return path


def is_video_file(path: str) -> bool:
    """
    Check if a file is a video file based on extension.
    
    Args:
        path: The file path to check.
        
    Returns:
        True if it's a video file, False otherwise.
    """
    video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv'}
    return Path(path).suffix.lower() in video_extensions

"""
Helper utility functions for the video scraper.
"""

import os
import re
from pathlib import Path
from typing import Optional


def sanitize_filename(name: Optional[str]) -> str:
    """
    Sanitize a filename by removing invalid characters.
    
    Args:
        name: The original filename or title.
        
    Returns:
        A sanitized filename safe for filesystem use.
    """
    if not name:
        return "video"
    
    # Remove newlines and extra whitespace
    name = name.replace('\n', ' ').replace('\r', ' ')
    
    # Remove duration pattern like "03:13" at start
    name = re.sub(r'^\d{1,2}:\d{2}\s*', '', name)
    
    # Remove patterns like "114K 84%" (views/ratings)
    name = re.sub(r'\d+[KMG]?\s*\d+%?', '', name)
    
    # Remove multiple spaces
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Remove invalid characters for filenames
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    
    # Remove leading/trailing dots
    name = name.strip('.')
    
    # Truncate to reasonable length
    name = name[:100]
    
    return name if name else "video"


def unique_output(filepath: str) -> str:
    """
    Generate a unique output filepath by appending a counter if file exists.
    
    Args:
        filepath: The desired output filepath.
        
    Returns:
        A unique filepath that doesn't conflict with existing files.
    """
    if not os.path.exists(filepath):
        return filepath
    
    base, ext = os.path.splitext(filepath)
    counter = 1
    while os.path.exists(f"{base}_{counter}{ext}"):
        counter += 1
    
    return f"{base}_{counter}{ext}"


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in bytes to human-readable string.
    
    Args:
        size_bytes: Size in bytes.
        
    Returns:
        Formatted string like "1.5 MB".
    """
    mb = size_bytes / (1024 * 1024)
    return f"{mb:.1f} MB"


def ensure_directory(path: str) -> None:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        path: Directory path to ensure exists.
    """
    os.makedirs(path, exist_ok=True)


def get_video_files(directory: str) -> list[str]:
    """
    Get all video files in a directory.
    
    Args:
        directory: Directory path to search.
        
    Returns:
        List of video file paths sorted alphabetically.
    """
    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv']
    files = []
    
    for ext in video_extensions:
        files.extend([str(f) for f in Path(directory).glob(f'*{ext}')])
        files.extend([str(f) for f in Path(directory).glob(f'*{ext.upper()}')])
    
    return sorted(files)


def parse_url_list(file_path: str) -> list[str]:
    """
    Parse a text file containing URLs (one per line).
    
    Args:
        file_path: Path to the text file.
        
    Returns:
        List of non-empty, non-comment URLs.
    """
    with open(file_path, 'r') as f:
        urls = [line.strip() for line in f 
                if line.strip() and not line.startswith('#')]
    return urls

"""
CSV Helper - Read, write, and manage CSV files for video processing.

This module provides utilities for:
- Reading CSV files with auto-delimiter detection
- Writing CSV files
- Managing CSV columns
- Filtering pending rows for processing
- Generating summaries
"""

import csv
import os
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Column Detection
# =============================================================================

def detect_url_column(fieldnames: List[str], preferred: str = 'url') -> Optional[str]:
    """
    Auto-detect URL column in CSV.
    
    Args:
        fieldnames: List of CSV column names.
        preferred: Preferred column name.
        
    Returns:
        Column name if found, None otherwise.
    """
    if preferred in fieldnames:
        return preferred
    
    candidates = [
        'url', 'URL', 'Url', 'link', 'Link', 'LINK',
        'video_url', 'video_link', 'source', 'Source', 'href'
    ]
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
    
    return None


def ensure_columns(
    fieldnames: List[str],
    required: Optional[List[str]] = None,
) -> List[str]:
    """
    Ensure required columns exist in fieldnames.
    
    Args:
        fieldnames: Current list of fieldnames.
        required: List of required column names.
        
    Returns:
        List of newly added column names.
    """
    if required is None:
        required = ['title', 'status', 'streamtape']
    
    added = []
    for col in required:
        if col not in fieldnames:
            fieldnames.append(col)
            added.append(col)
    
    return added


# =============================================================================
# Read/Write Operations
# =============================================================================

def read_csv(csv_file: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Read CSV file with auto-delimiter detection.
    
    Supports:
    - Auto-detect delimiter (, ; tab |)
    - UTF-8 BOM support
    
    Args:
        csv_file: Path to CSV file.
        
    Returns:
        Tuple of (fieldnames, rows).
    """
    rows = []
    fieldnames = []
    
    with open(csv_file, 'r', newline='', encoding='utf-8-sig') as f:
        # Detect delimiter
        sample = f.read(4096)
        f.seek(0)
        
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
        except csv.Error:
            dialect = csv.excel  # default comma
        
        reader = csv.DictReader(f, dialect=dialect)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            rows.append(dict(row))
    
    logger.debug(f"CSV read: {len(rows)} rows, columns: {fieldnames}")
    return fieldnames, rows


def save_csv(
    csv_file: str,
    fieldnames: List[str],
    rows: List[Dict[str, Any]],
) -> None:
    """
    Save CSV file (overwrite).
    
    Args:
        csv_file: Path to CSV file.
        fieldnames: List of column names.
        rows: List of row dictionaries.
    """
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    
    logger.debug(f"CSV saved: {csv_file}")


# =============================================================================
# Row Filtering
# =============================================================================

def get_pending_rows(
    rows: List[Dict[str, Any]],
    url_column: str = 'url',
    done_column: str = 'streamtape',
) -> List[int]:
    """
    Get indices of rows that need processing.
    
    Skips rows where:
    - URL is empty
    - Already has a Streamtape link
    
    Args:
        rows: List of CSV row dictionaries.
        url_column: Name of URL column.
        done_column: Column to check for completion.
        
    Returns:
        List of row indices to process.
    """
    pending = []
    for i, row in enumerate(rows):
        url = row.get(url_column, '').strip()
        has_done = row.get(done_column, '').strip()
        if url and not has_done:
            pending.append(i)
    return pending


# =============================================================================
# Summary/Reporting
# =============================================================================

def print_summary(
    rows: List[Dict[str, Any]],
    skipped: int = 0,
) -> None:
    """
    Print CSV processing summary.
    
    Args:
        rows: List of CSV row dictionaries.
        skipped: Number of skipped rows.
    """
    count_ok = sum(1 for r in rows if r.get('status') == 'OK')
    count_dl = sum(1 for r in rows if r.get('status') == 'DOWNLOADED')
    count_fail = sum(1 for r in rows if r.get('status', '').startswith(
        ('ERROR', 'NO_M3U8', 'DOWNLOAD_FAILED', 'UPLOAD_FAILED')))
    
    print(f"  ✅ OK (uploaded)  : {count_ok}")
    print(f"  📥 Downloaded     : {count_dl}")
    print(f"  ⏭️  Skipped        : {skipped}")
    print(f"  ❌ Failed         : {count_fail}")
    print(f"  📄 Total baris    : {len(rows)}")
    
    # Display Streamtape links
    st_links = [
        (r.get('title', '?'), r.get('streamtape', ''))
        for r in rows if r.get('streamtape', '').strip()
    ]
    if st_links:
        print(f"\n📺 Streamtape Links:")
        for title, link in st_links:
            print(f"   {title[:40]:40s}  →  {link}")


def get_summary_stats(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Get CSV statistics as a dictionary.
    
    Args:
        rows: List of CSV row dictionaries.
        
    Returns:
        Dictionary with count statistics.
    """
    return {
        'total': len(rows),
        'ok': sum(1 for r in rows if r.get('status') == 'OK'),
        'downloaded': sum(1 for r in rows if r.get('status') == 'DOWNLOADED'),
        'failed': sum(1 for r in rows if r.get('status', '').startswith(
            ('ERROR', 'NO_M3U8', 'DOWNLOAD_FAILED', 'UPLOAD_FAILED'))),
        'pending': sum(1 for r in rows if not r.get('streamtape', '').strip()),
    }

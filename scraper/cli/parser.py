"""
CLI argument parser for the video scraper.
"""

import argparse


def create_parser() -> argparse.ArgumentParser:
    """
    Create the argument parser for the CLI.
    
    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description='Video Scraper - Intercept & Download HLS streams',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # Mutually exclusive group for main commands
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--url',
        help='Video page URL to scrape'
    )
    group.add_argument(
        '--direct',
        help='Direct M3U8 URL to download'
    )
    group.add_argument(
        '--batch',
        help='Text file containing list of URLs (one per line)'
    )
    group.add_argument(
        '--csv',
        help='CSV file with URLs (will be updated in-place)'
    )
    group.add_argument(
        '--upload-only',
        help='Upload file or folder to Streamtape'
    )
    group.add_argument(
        '--debug',
        help='Debug a page and capture info'
    )
    
    # Optional arguments
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='Output filename (for single URL)'
    )
    parser.add_argument(
        '--output-dir', '-d',
        default='.',
        help='Output directory for downloaded videos'
    )
    parser.add_argument(
        '--referer', '-r',
        default=None,
        help='Custom HTTP referer'
    )
    parser.add_argument(
        '--upload', '-u',
        action='store_true',
        help='Upload videos to Streamtape after download'
    )
    parser.add_argument(
        '--csv-column',
        default='url',
        help='Name of the URL column in CSV file'
    )
    
    return parser

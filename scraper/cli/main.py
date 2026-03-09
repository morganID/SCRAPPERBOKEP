"""
Main CLI execution logic for the video scraper.
"""

import asyncio
import logging
import os
import sys

import config
from scraper.pipeline import download_direct, download_video
from scraper.pipeline import upload_multiple, upload_to_streamtape
from .parser import create_parser
from ..core.scraper import VideoScraper
from ..core.interceptor import NetworkInterceptor
from ..pipeline.batch import BatchPipeline
from ..pipeline.csv import CSVPipeline
from ..utils.helpers import sanitize_filename, unique_output

logger = logging.getLogger(__name__)


BANNER = """
╔══════════════════════════════════════════╗
          🎬 VIDEO SCRAPER v2.0            
         ⚡ Concurrent Pipeline            
╚══════════════════════════════════════════╝
"""


async def scrape_single(url: str, output: str = None, referer: str = None, upload: bool = False) -> None:
    """
    Scrape a single URL.
    
    Args:
        url: Video page URL.
        output: Output filename.
        referer: HTTP referer.
        upload: Whether to upload after download.
    """
    scraper = VideoScraper()
    
    try:
        await scraper.start_browser()
        print(f"Scraping: {url}")
        
        m3u8_urls = await scraper.scrape(url)
        
        if m3u8_urls:
            best = NetworkInterceptor.pick_best_url(m3u8_urls)
            logger.debug(f"All M3U8: {m3u8_urls}")
            print(f"\n🏆 Best URL: {best}")
            
            if output:
                output_file = output
            else:
                title = await scraper.get_page_title()
                title = sanitize_filename(title)
                output_file = f"{title}.mp4"
                print(f"📝 Title: {title}")
            
            logger.debug(f"Output: {output_file}")
            success = download_video(
                m3u8_url=best,
                output_file=output_file,
                referer=referer or config.DEFAULT_REFERER,
            )
            
            if success and upload:
                await upload_to_streamtape(output_file)
        
        else:
            logger.warning(f"M3U8 not found: {url}")
            logger.debug(f"Captured URLs: {scraper.captured_urls}")
            print("\n❌ M3U8 not found")
    
    finally:
        await scraper.close()


async def upload_only(path: str) -> None:
    """
    Upload files to Streamtape.
    
    Args:
        path: File or folder path to upload.
    """
    from ..utils.helpers import get_video_files
    
    path = os.path.abspath(path)
    
    if not os.path.exists(path):
        logger.error(f"Path not found: {path}")
        print(f"❌ Path not found: {path}")
        return
    
    if os.path.isfile(path):
        files = [path]
    else:
        files = get_video_files(path)
    
    if not files:
        logger.warning("No video files found!")
        print("❌ No video files found!")
        return
    
    print(f"\n📁 Found {len(files)} file(s):")
    for f in files[:10]:
        size = os.path.getsize(f) / (1024 * 1024)
        print(f"   - {os.path.basename(f)} ({size:.1f} MB)")
    if len(files) > 10:
        print(f"   ... +{len(files) - 10} more")
    
    logger.info(f"Upload {len(files)} files")
    await upload_multiple(files)


async def debug_page(url: str) -> None:
    """
    Debug a page.
    
    Args:
        url: URL to debug.
    """
    scraper = VideoScraper()
    try:
        await scraper.start_browser()
        await scraper.debug(url)
    finally:
        await scraper.close()


def run_cli() -> None:
    """Run the CLI application."""
    print(BANNER)
    
    parser = create_parser()
    args = parser.parse_args()
    
    loop = asyncio.get_event_loop()
    
    # Handle direct M3U8 download
    if args.direct:
        success = download_direct(
            m3u8_url=args.direct,
            output_file=args.output or config.DEFAULT_OUTPUT,
            referer=args.referer or config.DEFAULT_REFERER,
        )
        if success and args.upload:
            loop.run_until_complete(
                upload_to_streamtape(args.output or config.DEFAULT_OUTPUT)
            )
    
    # Handle single URL scrape
    elif args.url:
        loop.run_until_complete(
            scrape_single(args.url, args.output, args.referer, args.upload)
        )
    
    # Handle batch URL file
    elif args.batch:
        if not os.path.exists(args.batch):
            logger.error(f"File not found: {args.batch}")
            print(f"❌ File not found: {args.batch}")
            sys.exit(1)
        
        with open(args.batch, 'r') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        print(f"📋 {len(urls)} URLs from {args.batch}")
        
        os.makedirs(args.output_dir, exist_ok=True)
        
        pipeline = BatchPipeline(
            output_dir=args.output_dir,
            referer=args.referer,
            upload=args.upload,
        )
        loop.run_until_complete(pipeline.run(urls))
    
    # Handle CSV file
    elif args.csv:
        pipeline = CSVPipeline(
            csv_file=args.csv,
            url_column=args.csv_column,
            output_dir=args.output_dir,
            referer=args.referer,
            upload=args.upload,
        )
        loop.run_until_complete(pipeline.run())
    
    # Handle upload only
    elif args.upload_only:
        loop.run_until_complete(upload_only(args.upload_only))
    
    # Handle debug
    elif args.debug:
        loop.run_until_complete(debug_page(args.debug))

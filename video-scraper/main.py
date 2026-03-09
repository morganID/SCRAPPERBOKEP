#!/usr/bin/env python3
"""
Video Scraper - Main Entry Point

Usage:
  python main.py --url "https://target-site.com/video"
  python main.py --url "URL" --output video.mp4
  python main.py --direct "https://xxx/index.m3u8"
  python main.py --batch urls.txt
  python main.py --debug "https://target-site.com/video"
"""

import asyncio
import argparse
import json
import sys
import os

# Fix async di Colab / Jupyter
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from scraper import VideoScraper
from downloader import download_video, download_direct, pick_best_url
import config


# ========================
#  SINGLE SCRAPE
# ========================

async def scrape_single(url, output=None, referer=None):
    """Scrape dan download satu video"""
    scraper = VideoScraper()

    try:
        await scraper.start_browser()
        m3u8_urls = await scraper.scrape(url)

        if m3u8_urls:
            best = pick_best_url(m3u8_urls)
            print(f"\n🏆 Best URL: {best}")

            download_video(
                m3u8_url=best,
                output_file=output or config.DEFAULT_OUTPUT,
                referer=referer or config.DEFAULT_REFERER,
            )
        else:
            print("\n❌ M3U8 tidak ditemukan")
            print(f"\nCaptured URLs:")
            print(json.dumps(scraper.captured_urls, indent=2, default=str))

    finally:
        await scraper.close()


# ========================
#  BATCH SCRAPE
# ========================

async def scrape_batch(urls, output_dir='.', referer=None):
    """Scrape dan download banyak video"""
    scraper = VideoScraper()
    results = []

    try:
        await scraper.start_browser()

        for i, url in enumerate(urls):
            url = url.strip()
            if not url or url.startswith('#'):
                continue

            print(f"\n\n{'#'*60}")
            print(f"# VIDEO {i+1}/{len(urls)}")
            print(f"{'#'*60}")

            scraper.reset()

            try:
                m3u8_urls = await scraper.scrape(url)

                if m3u8_urls:
                    best = pick_best_url(m3u8_urls)
                    output = os.path.join(output_dir, f'video_{i+1}.mp4')

                    success = download_video(
                        m3u8_url=best,
                        output_file=output,
                        referer=referer or config.DEFAULT_REFERER,
                    )
                    results.append({
                        'url': url,
                        'status': 'OK' if success else 'DOWNLOAD_FAILED',
                        'm3u8': best,
                    })
                else:
                    results.append({'url': url, 'status': 'NO_M3U8'})

            except Exception as e:
                results.append({'url': url, 'status': f'ERROR: {e}'})

            await asyncio.sleep(3)

    finally:
        await scraper.close()

    # Summary
    print(f"\n\n{'='*60}")
    print(f"📊 BATCH SUMMARY")
    print(f"{'='*60}")
    for r in results:
        icon = "✅" if r['status'] == 'OK' else "❌"
        print(f"  {icon} {r['status']:20s} → {r['url'][:50]}")

    return results


# ========================
#  DEBUG
# ========================

async def debug_page(url):
    """Debug halaman target"""
    scraper = VideoScraper()

    try:
        await scraper.start_browser()
        await scraper.debug(url, screenshot_path='debug_screenshot.png')
    finally:
        await scraper.close()


# ========================
#  CLI
# ========================

def parse_args():
    parser = argparse.ArgumentParser(
        description='Video Scraper - Intercept & Download HLS streams',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --url "https://site.com/video"
  python main.py --url "https://site.com/video" --output my_video.mp4
  python main.py --direct "https://xxx/index.m3u8" --output video.mp4
  python main.py --batch urls.txt --output-dir ./videos
  python main.py --debug "https://site.com/video"
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--url', help='URL halaman video untuk di-scrape')
    group.add_argument('--direct', help='URL M3U8 langsung (skip scraping)')
    group.add_argument('--batch', help='File berisi list URL (satu per baris)')
    group.add_argument('--debug', help='Debug halaman (screenshot + info)')

    parser.add_argument('--output', '-o', default=None, help='Output filename')
    parser.add_argument('--output-dir', default='.', help='Output directory untuk batch')
    parser.add_argument('--referer', '-r', default=None, help='Custom referer header')

    return parser.parse_args()


def main():
    args = parse_args()
    loop = asyncio.get_event_loop()

    print(f"""
╔══════════════════════════════════════╗
║       🎬 VIDEO SCRAPER v1.0         ║
╚══════════════════════════════════════╝
    """)

    if args.direct:
        # ── Direct download ──
        download_direct(
            m3u8_url=args.direct,
            output_file=args.output or config.DEFAULT_OUTPUT,
            referer=args.referer or config.DEFAULT_REFERER,
        )

    elif args.url:
        # ── Single scrape ──
        loop.run_until_complete(
            scrape_single(
                url=args.url,
                output=args.output,
                referer=args.referer,
            )
        )

    elif args.batch:
        # ── Batch scrape ──
        if not os.path.exists(args.batch):
            print(f"❌ File tidak ditemukan: {args.batch}")
            sys.exit(1)

        with open(args.batch, 'r') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        print(f"📋 {len(urls)} URL dari {args.batch}")

        os.makedirs(args.output_dir, exist_ok=True)

        loop.run_until_complete(
            scrape_batch(
                urls=urls,
                output_dir=args.output_dir,
                referer=args.referer,
            )
        )

    elif args.debug:
        # ── Debug ──
        loop.run_until_complete(debug_page(args.debug))


if __name__ == '__main__':
    main()
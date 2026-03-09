#!/usr/bin/env python3
"""
Video Scraper - Main Entry Point

Usage:
  python main.py --url "https://target-site.com/video"
  python main.py --url "URL" --output video.mp4
  python main.py --url "URL" --upload                    # ← NEW
  python main.py --direct "https://xxx/index.m3u8"
  python main.py --batch urls.txt
  python main.py --batch urls.txt --upload               # ← NEW
  python main.py --upload video.mp4                      # ← NEW
  python main.py --upload ./videos                       # ← NEW
  python main.py --debug "https://target-site.com/video"
"""

import asyncio
import argparse
import json
import sys
import os
from pathlib import Path

try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from scraper import VideoScraper
from downloader import download_video, download_direct, pick_best_url
from uploader import upload_to_streamtape, upload_multiple  # ← NEW
import config


# ========================
#  SINGLE SCRAPE
# ========================

async def scrape_single(url, output=None, referer=None, upload=False):
    """Scrape dan download satu video"""
    scraper = VideoScraper()
    output_file = output or config.DEFAULT_OUTPUT

    try:
        await scraper.start_browser()
        m3u8_urls = await scraper.scrape(url)

        if m3u8_urls:
            best = pick_best_url(m3u8_urls)
            print(f"\n🏆 Best URL: {best}")

            success = download_video(
                m3u8_url=best,
                output_file=output_file,
                referer=referer or config.DEFAULT_REFERER,
            )

            # Upload jika diminta
            if success and upload:
                await upload_to_streamtape(output_file)

        else:
            print("\n❌ M3U8 tidak ditemukan")
            print(f"\nCaptured URLs:")
            print(json.dumps(scraper.captured_urls, indent=2, default=str))

    finally:
        await scraper.close()


# ========================
#  BATCH SCRAPE
# ========================

async def scrape_batch(urls, output_dir='.', referer=None, upload=False):
    """Scrape dan download banyak video"""
    scraper = VideoScraper()
    results = []
    downloaded_files = []

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

                    if success:
                        downloaded_files.append(output)

                    results.append({
                        'url': url,
                        'status': 'OK' if success else 'DOWNLOAD_FAILED',
                        'm3u8': best,
                        'file': output if success else None,
                    })
                else:
                    results.append({'url': url, 'status': 'NO_M3U8', 'file': None})

            except Exception as e:
                results.append({'url': url, 'status': f'ERROR: {e}', 'file': None})

            await asyncio.sleep(3)

    finally:
        await scraper.close()

    # Upload semua file jika diminta
    if upload and downloaded_files:
        print(f"\n\n{'='*60}")
        print(f"⬆️  UPLOADING {len(downloaded_files)} FILES TO STREAMTAPE")
        print(f"{'='*60}")

        upload_results = await upload_multiple(downloaded_files)

        # Gabungkan hasil
        for r in results:
            if r.get('file'):
                for u in upload_results:
                    if u['file'] == os.path.basename(r['file']):
                        r['streamtape'] = u['url']
                        break

    # Summary
    print(f"\n\n{'='*60}")
    print(f"📊 BATCH SUMMARY")
    print(f"{'='*60}")
    for r in results:
        icon = "✅" if r['status'] == 'OK' else "❌"
        st_url = r.get('streamtape', '')
        print(f"  {icon} {r['status']:20s} → {r['url'][:40]}")
        if st_url:
            print(f"     📺 {st_url}")

    return results


# ========================
#  UPLOAD ONLY
# ========================

async def upload_only(path):
    """Upload file/folder ke Streamtape tanpa scraping"""
    path = Path(path)
    video_ext = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv']

    if not path.exists():
        print(f"❌ Path tidak ditemukan: {path}")
        return

    # Kumpulkan file
    if path.is_file():
        if path.suffix.lower() in video_ext:
            files = [str(path)]
        else:
            print(f"❌ Bukan file video: {path}")
            return
    else:
        files = []
        for ext in video_ext:
            files.extend([str(f) for f in path.glob(f'*{ext}')])
            files.extend([str(f) for f in path.glob(f'*{ext.upper()}')])
        files = sorted(files)

    if not files:
        print("❌ Tidak ada file video ditemukan!")
        return

    print(f"\n📁 Found {len(files)} file(s):")
    for f in files[:10]:
        size = os.path.getsize(f) / (1024 * 1024)
        print(f"   - {os.path.basename(f)} ({size:.1f} MB)")
    if len(files) > 10:
        print(f"   ... +{len(files) - 10} more")

    results = await upload_multiple(files)
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
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--url', help='URL halaman video untuk di-scrape')
    group.add_argument('--direct', help='URL M3U8 langsung (skip scraping)')
    group.add_argument('--batch', help='File berisi list URL (satu per baris)')
    group.add_argument('--upload-only', help='Upload file/folder ke Streamtape (tanpa scraping)')
    group.add_argument('--debug', help='Debug halaman (screenshot + info)')

    parser.add_argument('--output', '-o', default=None, help='Output filename')
    parser.add_argument('--output-dir', default='.', help='Output directory untuk batch')
    parser.add_argument('--referer', '-r', default=None, help='Custom referer header')
    
    # Flag terpisah untuk upload setelah download
    parser.add_argument('--upload', action='store_true', help='Upload ke Streamtape setelah download')

    return parser.parse_args()

def main():
    args = parse_args()
    loop = asyncio.get_event_loop()

    print(f"""
╔══════════════════════════════════════╗
║       🎬 VIDEO SCRAPER v1.1         ║
╚══════════════════════════════════════╝
    """)

    if args.direct:
        # ── Direct download ──
        success = download_direct(
            m3u8_url=args.direct,
            output_file=args.output or config.DEFAULT_OUTPUT,
            referer=args.referer or config.DEFAULT_REFERER,
        )

        # Upload jika ada flag --upload juga? 
        # (butuh modifikasi argparse kalau mau combine)

    elif args.url:
        # ── Single scrape ──
        # Cek apakah --upload dipakai sebagai flag (bukan path)
        do_upload = args.upload is True if hasattr(args, 'upload') else False

        loop.run_until_complete(
            scrape_single(
                url=args.url,
                output=args.output,
                referer=args.referer,
                upload=do_upload,
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

        do_upload = args.upload is True if hasattr(args, 'upload') else False

        loop.run_until_complete(
            scrape_batch(
                urls=urls,
                output_dir=args.output_dir,
                referer=args.referer,
                upload=do_upload,
            )
        )

    elif args.upload:
        # ── Upload only ──
        if args.upload is True:
            print("❌ Harus kasih path! Contoh: --upload video.mp4")
            sys.exit(1)

        loop.run_until_complete(upload_only(args.upload))

    elif args.debug:
        # ── Debug ──
        loop.run_until_complete(debug_page(args.debug))


if __name__ == '__main__':
    main()
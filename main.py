#!/usr/bin/env python3
"""
Video Scraper v2.0 - Concurrent Pipeline

Usage:
  python main.py --url "https://target-site.com/video"
  python main.py --url "URL" --output video.mp4 --upload
  python main.py --direct "https://xxx/index.m3u8"
  python main.py --batch urls.txt --upload --max-dl 5 --max-up 3
  python main.py --csv data.csv --upload
  python main.py --csv data.csv --csv-column link --upload
  python main.py --upload-only video.mp4
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
from uploader import upload_to_streamtape, upload_multiple
from pipeline import Pipeline, Job
from utils import sanitize_filename, get_page_title
from csv_helper import (
    read_csv, save_csv, detect_url_column,
    ensure_columns, get_pending_rows, print_summary,
)
import config


# ═══════════════════════════════════════
#  SINGLE (no pipeline needed)
# ═══════════════════════════════════════

async def scrape_single(url, output=None, referer=None, upload=False):
    scraper = VideoScraper()
    try:
        await scraper.start_browser()
        m3u8_urls = await scraper.scrape(url)

        if not m3u8_urls:
            print("\n❌ M3U8 tidak ditemukan")
            print(json.dumps(scraper.captured_urls, indent=2, default=str))
            return

        best = pick_best_url(m3u8_urls)
        print(f"\n🏆 Best URL: {best}")

        if not output:
            title = await get_page_title(scraper.page)
            output = f"{sanitize_filename(title)}.mp4"
            print(f"📝 Judul: {title}")

        success = download_video(best, output, referer or config.DEFAULT_REFERER)

        if success and upload:
            await upload_to_streamtape(output)
    finally:
        await scraper.close()


# ═══════════════════════════════════════
#  BATCH
# ═══════════════════════════════════════

def _print_job_summary(jobs):
    print(f"\n{'='*60}")
    print(f"📊 SUMMARY")
    print(f"{'='*60}")
    counts = {}
    for j in jobs:
        icon = '✅' if j.status == 'OK' else ('⬇️' if j.status == 'DOWNLOADED' else '❌')
        label = j.title[:40] or j.url[:40]
        print(f"  {icon} {label}  [{j.status}]")
        if j.streamtape:
            print(f"     📺 {j.streamtape}")
        counts[j.status] = counts.get(j.status, 0) + 1
    print(f"\n  {counts}")


async def scrape_batch(urls, output_dir='.', referer=None, upload=False,
                       max_dl=None, max_up=None):
    valid = [u.strip() for u in urls if u.strip() and not u.startswith('#')]
    jobs = [Job(url=u, id=i) for i, u in enumerate(valid)]

    pipe = Pipeline(
        max_dl=max_dl or config.MAX_CONCURRENT_DOWNLOADS,
        max_up=max_up or config.MAX_CONCURRENT_UPLOADS,
        referer=referer,
        upload=upload,
        output_dir=output_dir,
    )
    await pipe.run(jobs)
    _print_job_summary(jobs)
    return jobs


# ═══════════════════════════════════════
#  CSV  (on_update saves CSV every time)
# ═══════════════════════════════════════

async def scrape_csv(csv_file, url_column='url', output_dir='.',
                     referer=None, upload=False,
                     max_dl=None, max_up=None):

    if not os.path.exists(csv_file):
        print(f"❌ File tidak ditemukan: {csv_file}")
        return

    fieldnames, rows = read_csv(csv_file)
    if not fieldnames:
        print("❌ CSV kosong / format tidak valid!")
        return

    print(f"📄 CSV: {csv_file}  ({len(rows)} baris)")

    detected = detect_url_column(fieldnames, preferred=url_column)
    if not detected:
        print(f"❌ Kolom URL '{url_column}' tidak ditemukan!  Tersedia: {fieldnames}")
        return
    url_column = detected
    ensure_columns(fieldnames)

    to_process = get_pending_rows(rows, url_column=url_column)
    skipped = len(rows) - len(to_process)
    if skipped:
        print(f"   ⏭️  Skip {skipped} baris (sudah OK)")
    if not to_process:
        print("✅ Semua sudah selesai!")
        return

    # Build jobs → id = row index
    jobs = []
    for idx in to_process:
        row = rows[idx]
        jobs.append(Job(
            url=row[url_column].strip(),
            id=idx,
            title=row.get('title', '').strip(),
        ))

    # Callback: setiap status berubah → sync update row + save CSV
    def on_update(job: Job):
        row = rows[job.id]
        row['status'] = job.status
        if job.title:
            row['title'] = row.get('title', '').strip() or job.title
        if job.streamtape:
            row['streamtape'] = job.streamtape
        save_csv(csv_file, fieldnames, rows)

    pipe = Pipeline(
        max_dl=max_dl or config.MAX_CONCURRENT_DOWNLOADS,
        max_up=max_up or config.MAX_CONCURRENT_UPLOADS,
        referer=referer,
        upload=upload,
        output_dir=output_dir,
    )
    await pipe.run(jobs, on_update=on_update)

    save_csv(csv_file, fieldnames, rows)
    print(f"\n{'='*60}")
    print(f"📊 CSV SUMMARY — {csv_file}")
    print(f"{'='*60}")
    print_summary(rows, skipped=skipped)
    print(f"💾 Saved: {csv_file}")
    return rows


# ═══════════════════════════════════════
#  UPLOAD ONLY
# ═══════════════════════════════════════

async def upload_only(path):
    path = Path(path)
    exts = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv'}

    if not path.exists():
        print(f"❌ Path tidak ditemukan: {path}")
        return

    if path.is_file():
        files = [str(path)] if path.suffix.lower() in exts else []
    else:
        files = sorted({str(f) for f in path.iterdir()
                        if f.suffix.lower() in exts})

    if not files:
        print("❌ Tidak ada file video!")
        return

    print(f"📁 {len(files)} file(s)")
    for f in files[:10]:
        sz = os.path.getsize(f) / (1024 * 1024)
        print(f"   - {os.path.basename(f)} ({sz:.1f} MB)")

    return await upload_multiple(files)


# ═══════════════════════════════════════
#  DEBUG
# ═══════════════════════════════════════

async def debug_page(url):
    scraper = VideoScraper()
    try:
        await scraper.start_browser()
        await scraper.debug(url, screenshot_path='debug_screenshot.png')
    finally:
        await scraper.close()


# ═══════════════════════════════════════
#  CLI
# ═══════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(
        description='Video Scraper v2.0 - Concurrent Pipeline')

    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--url',         help='URL halaman video')
    g.add_argument('--direct',      help='URL M3U8 langsung')
    g.add_argument('--batch',       help='File list URL (.txt)')
    g.add_argument('--csv',         help='File CSV (update in-place)')
    g.add_argument('--upload-only', help='Upload file/folder')
    g.add_argument('--debug',       help='Debug halaman')

    p.add_argument('-o', '--output',    default=None)
    p.add_argument('--output-dir',      default='.')
    p.add_argument('-r', '--referer',   default=None)
    p.add_argument('--upload',          action='store_true')
    p.add_argument('--csv-column',      default='url')
    p.add_argument('--max-dl', type=int, default=None,
                   help=f'Concurrent downloads (default {config.MAX_CONCURRENT_DOWNLOADS})')
    p.add_argument('--max-up', type=int, default=None,
                   help=f'Concurrent uploads (default {config.MAX_CONCURRENT_UPLOADS})')
    return p.parse_args()


def main():
    args = parse_args()
    loop = asyncio.get_event_loop()

    print("""
╔══════════════════════════════════════╗
║     🎬 VIDEO SCRAPER v2.0           ║
║     ⚡ Concurrent Pipeline          ║
╚══════════════════════════════════════╝
    """)

    if args.direct:
        ok = download_direct(args.direct,
                             args.output or config.DEFAULT_OUTPUT,
                             args.referer or config.DEFAULT_REFERER)
        if ok and args.upload:
            loop.run_until_complete(
                upload_to_streamtape(args.output or config.DEFAULT_OUTPUT))

    elif args.url:
        loop.run_until_complete(
            scrape_single(args.url, args.output, args.referer, args.upload))

    elif args.batch:
        if not os.path.exists(args.batch):
            sys.exit(f"❌ File tidak ditemukan: {args.batch}")
        with open(args.batch) as f:
            urls = f.read().splitlines()
        loop.run_until_complete(
            scrape_batch(urls, args.output_dir, args.referer, args.upload,
                         args.max_dl, args.max_up))

    elif args.csv:
        loop.run_until_complete(
            scrape_csv(args.csv, args.csv_column, args.output_dir,
                       args.referer, args.upload, args.max_dl, args.max_up))

    elif args.upload_only:
        loop.run_until_complete(upload_only(args.upload_only))

    elif args.debug:
        loop.run_until_complete(debug_page(args.debug))


if __name__ == '__main__':
    main()
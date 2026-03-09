#!/usr/bin/env python3
"""
Video Scraper - Main Entry Point
"""

import asyncio
import argparse
import json
import sys
import os
import re
import logging
from pathlib import Path

try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from scraper import VideoScraper
from downloader import download_video, download_direct, pick_best_url
from uploader import upload_to_streamtape, upload_multiple
from csv_helper import (
    read_csv, save_csv, detect_url_column,
    ensure_columns, get_pending_rows, print_summary
)
import config  # ini trigger basicConfig di config.py

log = logging.getLogger(__name__)


# ========================
#  HELPER
# ========================

def sanitize_filename(name):
    if not name:
        return "video"
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = name.strip('.')
    name = name[:100]
    return name if name else "video"


async def get_page_title(page):
    try:
        title = await page.evaluate("""
            () => {
                const h1 = document.querySelector('h1');
                if (h1 && h1.innerText.trim()) return h1.innerText.trim();

                const vt = document.querySelector('.video-title, .entry-title, .title');
                if (vt && vt.innerText.trim()) return vt.innerText.trim();

                const og = document.querySelector('meta[property="og:title"]');
                if (og && og.content) return og.content.trim();

                const title = document.title;
                if (title) return title.split(/[-|–—]/)[0].trim();

                return null;
            }
        """)
        log.debug(f"Page title: {title}")
        return title
    except Exception as e:
        log.debug(f"Gagal ambil title: {e}")
        return None


def unique_output(filepath):
    if not os.path.exists(filepath):
        return filepath
    base, ext = os.path.splitext(filepath)
    counter = 1
    while os.path.exists(f"{base}_{counter}{ext}"):
        counter += 1
    return f"{base}_{counter}{ext}"


# ========================
#  SINGLE SCRAPE
# ========================

async def scrape_single(url, output=None, referer=None, upload=False):
    scraper = VideoScraper()

    try:
        await scraper.start_browser()
        log.info(f"Scraping: {url}")
        m3u8_urls = await scraper.scrape(url)

        if m3u8_urls:
            best = pick_best_url(m3u8_urls)
            log.debug(f"Semua M3U8: {m3u8_urls}")
            print(f"\n🏆 Best URL: {best}")

            if output:
                output_file = output
            else:
                title = await get_page_title(scraper.page)
                title = sanitize_filename(title)
                output_file = f"{title}.mp4"
                print(f"📝 Judul: {title}")

            log.debug(f"Output: {output_file}")
            success = download_video(
                m3u8_url=best,
                output_file=output_file,
                referer=referer or config.DEFAULT_REFERER,
            )

            if success and upload:
                await upload_to_streamtape(output_file)

        else:
            log.warning(f"M3U8 tidak ditemukan: {url}")
            log.debug(f"Captured URLs: {json.dumps(scraper.captured_urls, indent=2, default=str)}")
            print("\n❌ M3U8 tidak ditemukan")

    finally:
        await scraper.close()


# ========================
#  CONCURRENT DOWNLOAD + UPLOAD
# ========================

async def download_and_upload(job, sem_dl, sem_up, referer, upload):
    async with sem_dl:
        log.info(f"Downloading: {job['title'][:40]}")
        log.debug(f"M3U8: {job['m3u8']}")
        log.debug(f"Output: {job['output']}")

        success = await asyncio.to_thread(
            download_video,
            m3u8_url=job['m3u8'],
            output_file=job['output'],
            referer=referer,
        )

    if not success:
        job['status'] = 'DOWNLOAD_FAILED'
        log.warning(f"Download gagal: {job['title'][:40]}")
        return job

    sz = os.path.getsize(job['output']) / (1024 * 1024)
    print(f"✅ Downloaded: {job['title'][:40]} ({sz:.1f} MB)")
    log.info(f"Downloaded: {job['title'][:40]} ({sz:.1f} MB)")
    job['status'] = 'DOWNLOADED'

    if upload:
        async with sem_up:
            log.info(f"Uploading: {job['title'][:40]}")
            st_url = await upload_to_streamtape(job['output'])

        if st_url:
            job['streamtape'] = st_url
            job['status'] = 'OK'
            print(f"📺 {st_url}")
            log.info(f"Uploaded: {st_url}")
        else:
            job['status'] = 'UPLOAD_FAILED'
            log.warning(f"Upload gagal: {job['title'][:40]}")

    return job


# ========================
#  BATCH SCRAPE
# ========================

async def scrape_batch(urls, output_dir='.', referer=None, upload=False):
    scraper = VideoScraper()
    jobs = []
    tasks = []

    max_dl = getattr(config, 'MAX_CONCURRENT_DOWNLOADS', 3)
    max_up = getattr(config, 'MAX_CONCURRENT_UPLOADS', 2)
    sem_dl = asyncio.Semaphore(max_dl)
    sem_up = asyncio.Semaphore(max_up)
    ref = referer or config.DEFAULT_REFERER

    valid_urls = [u.strip() for u in urls if u.strip() and not u.startswith('#')]
    total = len(valid_urls)

    print(f"⚡ Concurrent: download(×{max_dl}), upload(×{max_up})")
    log.info(f"Batch: {total} URLs")

    try:
        await scraper.start_browser()

        for i, url in enumerate(valid_urls, 1):
            print(f"\n{'#'*60}")
            print(f"# VIDEO {i}/{total}")
            print(f"# {url}")
            print(f"{'#'*60}")

            log.info(f"[{i}/{total}] Scraping: {url}")
            scraper.reset()

            try:
                m3u8_urls = await scraper.scrape(url)

                if not m3u8_urls:
                    log.warning(f"[{i}/{total}] M3U8 tidak ditemukan")
                    log.debug(f"Captured: {scraper.captured_urls}")
                    print("❌ M3U8 tidak ditemukan")
                    jobs.append({'url': url, 'title': '', 'status': 'NO_M3U8'})
                    continue

                best = pick_best_url(m3u8_urls)
                title = await get_page_title(scraper.page)
                title = sanitize_filename(title) or f"video_{i}"
                output = unique_output(os.path.join(output_dir, f"{title}.mp4"))

                print(f"📝 Judul: {title}")
                print(f"🏆 Best: {best}")
                log.debug(f"[{i}/{total}] Semua M3U8: {m3u8_urls}")
                log.debug(f"[{i}/{total}] Output: {output}")

                job = {
                    'url': url,
                    'title': title,
                    'm3u8': best,
                    'output': output,
                    'status': 'QUEUED',
                    'streamtape': '',
                }
                jobs.append(job)

                task = asyncio.create_task(
                    download_and_upload(job, sem_dl, sem_up, ref, upload)
                )
                tasks.append(task)

            except Exception as e:
                log.error(f"[{i}/{total}] Scrape error: {e}", exc_info=True)
                print(f"❌ Error: {e}")
                jobs.append({'url': url, 'title': '', 'status': f'ERROR: {e}'})

            await asyncio.sleep(3)

    finally:
        await scraper.close()

    if tasks:
        print(f"\n⏳ Menunggu {len(tasks)} download/upload selesai...")
        await asyncio.gather(*tasks)

    # Summary
    print(f"\n\n{'='*60}")
    print(f"📊 BATCH SUMMARY")
    print(f"{'='*60}")
    for j in jobs:
        st = j.get('status', '')
        icon = "✅" if st == 'OK' else ("⬇️" if st == 'DOWNLOADED' else "❌")
        print(f"  {icon} {j.get('title','')[:40] or j['url'][:40]}")
        print(f"     Status: {st}")
        if j.get('streamtape'):
            print(f"     📺 {j['streamtape']}")

    ok = sum(1 for j in jobs if j['status'] == 'OK')
    dl = sum(1 for j in jobs if j['status'] == 'DOWNLOADED')
    fail = sum(1 for j in jobs if j['status'] not in ('OK', 'DOWNLOADED'))
    print(f"\n  ✅ OK: {ok}  ⬇️ Downloaded: {dl}  ❌ Failed: {fail}")
    log.info(f"Batch done: OK={ok}, Downloaded={dl}, Failed={fail}")

    return jobs


# ========================
#  CSV SCRAPE
# ========================

async def scrape_csv(csv_file, url_column='url', output_dir='.',
                     referer=None, upload=False):

    if not os.path.exists(csv_file):
        log.error(f"File tidak ditemukan: {csv_file}")
        print(f"❌ File tidak ditemukan: {csv_file}")
        return

    fieldnames, rows = read_csv(csv_file)
    if not fieldnames:
        log.error("CSV kosong atau format tidak valid!")
        print("❌ CSV kosong atau format tidak valid!")
        return

    print(f"📄 CSV: {csv_file}")
    print(f"   Kolom: {fieldnames}")
    print(f"   Baris: {len(rows)}")
    log.debug(f"CSV fieldnames: {fieldnames}")

    detected = detect_url_column(fieldnames, preferred=url_column)
    if not detected:
        log.error(f"Kolom URL '{url_column}' tidak ditemukan! Tersedia: {fieldnames}")
        print(f"\n❌ Kolom URL tidak ditemukan!")
        print(f"   Cari: '{url_column}'")
        print(f"   Tersedia: {fieldnames}")
        print(f"   Gunakan --csv-column NAMA_KOLOM")
        return
    url_column = detected
    print(f"   Kolom URL: '{url_column}'")

    added = ensure_columns(fieldnames)
    if added:
        log.debug(f"Kolom baru: {added}")
        print(f"   ➕ Kolom baru: {added}")

    to_process = get_pending_rows(rows, url_column=url_column)
    skipped = len(rows) - len(to_process)

    if skipped > 0:
        print(f"   ⏭️  Skip {skipped} baris (sudah ada streamtape)")

    if not to_process:
        print("\n✅ Semua baris sudah punya link streamtape!")
        return

    print(f"   🎯 Akan proses: {len(to_process)} video")

    os.makedirs(output_dir, exist_ok=True)

    max_dl = getattr(config, 'MAX_CONCURRENT_DOWNLOADS', 3)
    max_up = getattr(config, 'MAX_CONCURRENT_UPLOADS', 2)
    sem_dl = asyncio.Semaphore(max_dl)
    sem_up = asyncio.Semaphore(max_up)
    csv_lock = asyncio.Lock()
    ref = referer or config.DEFAULT_REFERER

    print(f"   ⚡ Concurrent: download(×{max_dl}), upload(×{max_up})")
    log.info(f"CSV: {len(to_process)} video, dl×{max_dl}, up×{max_up}")

    async def process_and_save(job, row_idx):
        await download_and_upload(job, sem_dl, sem_up, ref, upload)

        async with csv_lock:
            row = rows[row_idx]
            row['status'] = job['status']
            if job.get('title'):
                row['title'] = row.get('title', '').strip() or job['title']
            if job.get('streamtape'):
                row['streamtape'] = job['streamtape']
            save_csv(csv_file, fieldnames, rows)
            log.debug(f"CSV saved (baris #{row_idx + 2}, status={job['status']})")
            print(f"💾 CSV updated (baris #{row_idx + 2})")

    scraper = VideoScraper()
    tasks = []

    try:
        await scraper.start_browser()

        for seq, idx in enumerate(to_process, 1):
            row = rows[idx]
            url = row[url_column].strip()

            print(f"\n{'#'*60}")
            print(f"# [{seq}/{len(to_process)}]  Baris CSV #{idx + 2}")
            print(f"# {url}")
            print(f"{'#'*60}")

            log.info(f"[{seq}/{len(to_process)}] Scraping baris #{idx + 2}")
            scraper.reset()

            try:
                m3u8_urls = await scraper.scrape(url)

                if not m3u8_urls:
                    log.warning(f"[{seq}] M3U8 tidak ditemukan")
                    print("❌ M3U8 tidak ditemukan")
                    row['status'] = 'NO_M3U8'
                    save_csv(csv_file, fieldnames, rows)
                    await asyncio.sleep(2)
                    continue

                best = pick_best_url(m3u8_urls)
                title = await get_page_title(scraper.page)
                title = sanitize_filename(title) or f"video_{idx + 1}"
                row['title'] = row.get('title', '').strip() or title
                output = unique_output(
                    os.path.join(output_dir, f"{sanitize_filename(row['title'])}.mp4")
                )

                print(f"📝 Judul: {row['title']}")
                print(f"🏆 Best: {best}")
                log.debug(f"[{seq}] M3U8: {best}")
                log.debug(f"[{seq}] Output: {output}")

                job = {
                    'url': url,
                    'title': row['title'],
                    'm3u8': best,
                    'output': output,
                    'status': 'QUEUED',
                    'streamtape': '',
                }

                task = asyncio.create_task(process_and_save(job, idx))
                tasks.append(task)

            except Exception as e:
                log.error(f"[{seq}] Error: {e}", exc_info=True)
                print(f"❌ Error: {e}")
                row['status'] = f'ERROR: {str(e)[:80]}'
                save_csv(csv_file, fieldnames, rows)

            await asyncio.sleep(3)

    finally:
        await scraper.close()

    if tasks:
        print(f"\n⏳ Menunggu {len(tasks)} download/upload selesai...")
        await asyncio.gather(*tasks)

    save_csv(csv_file, fieldnames, rows)

    print(f"\n\n{'='*60}")
    print(f"📊 CSV SUMMARY — {csv_file}")
    print(f"{'='*60}")
    print_summary(rows, skipped=skipped)
    print(f"\n💾 CSV saved: {csv_file}")
    log.info(f"CSV done: {csv_file}")

    return rows


# ========================
#  UPLOAD ONLY
# ========================

async def upload_only(path):
    path = Path(path)
    video_ext = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv']

    if not path.exists():
        log.error(f"Path tidak ditemukan: {path}")
        print(f"❌ Path tidak ditemukan: {path}")
        return

    if path.is_file():
        if path.suffix.lower() in video_ext:
            files = [str(path)]
        else:
            log.error(f"Bukan file video: {path}")
            print(f"❌ Bukan file video: {path}")
            return
    else:
        files = []
        for ext in video_ext:
            files.extend([str(f) for f in path.glob(f'*{ext}')])
            files.extend([str(f) for f in path.glob(f'*{ext.upper()}')])
        files = sorted(files)

    if not files:
        log.warning("Tidak ada file video ditemukan!")
        print("❌ Tidak ada file video ditemukan!")
        return

    print(f"\n📁 Found {len(files)} file(s):")
    for f in files[:10]:
        size = os.path.getsize(f) / (1024 * 1024)
        print(f"   - {os.path.basename(f)} ({size:.1f} MB)")
    if len(files) > 10:
        print(f"   ... +{len(files) - 10} more")

    log.info(f"Upload {len(files)} files")
    results = await upload_multiple(files)
    return results


# ========================
#  DEBUG
# ========================

async def debug_page(url):
    scraper = VideoScraper()
    try:
        await scraper.start_browser()
        log.info(f"Debug: {url}")
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
    group.add_argument('--url', help='URL halaman video')
    group.add_argument('--direct', help='URL M3U8 langsung')
    group.add_argument('--batch', help='File list URL (txt)')
    group.add_argument('--csv', help='File CSV (update in-place)')
    group.add_argument('--upload-only', help='Upload file/folder')
    group.add_argument('--debug', help='Debug halaman')

    parser.add_argument('--output', '-o', default=None, help='Output filename')
    parser.add_argument('--output-dir', default='.', help='Output directory')
    parser.add_argument('--referer', '-r', default=None, help='Custom referer')
    parser.add_argument('--upload', action='store_true', help='Upload ke Streamtape')
    parser.add_argument('--csv-column', default='url', help='Nama kolom URL di CSV')

    return parser.parse_args()


def main():
    args = parse_args()
    loop = asyncio.get_event_loop()

    print("""
╔══════════════════════════════════════╗
║       🎬 VIDEO SCRAPER v2.0         ║
║       ⚡ Concurrent Pipeline        ║
╚══════════════════════════════════════╝
    """)

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

    elif args.url:
        loop.run_until_complete(
            scrape_single(args.url, args.output, args.referer, args.upload)
        )

    elif args.batch:
        if not os.path.exists(args.batch):
            log.error(f"File tidak ditemukan: {args.batch}")
            print(f"❌ File tidak ditemukan: {args.batch}")
            sys.exit(1)
        with open(args.batch, 'r') as f:
            urls = [l.strip() for l in f if l.strip() and not l.startswith('#')]
        print(f"📋 {len(urls)} URL dari {args.batch}")
        os.makedirs(args.output_dir, exist_ok=True)
        loop.run_until_complete(
            scrape_batch(urls, args.output_dir, args.referer, args.upload)
        )

    elif args.csv:
        loop.run_until_complete(
            scrape_csv(args.csv, args.csv_column, args.output_dir,
                       args.referer, args.upload)
        )

    elif args.upload_only:
        loop.run_until_complete(upload_only(args.upload_only))

    elif args.debug:
        loop.run_until_complete(debug_page(args.debug))


if __name__ == '__main__':
    main()
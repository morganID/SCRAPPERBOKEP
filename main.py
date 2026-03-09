#!/usr/bin/env python3
"""
Video Scraper - Main Entry Point

Usage:
  python main.py --url "https://target-site.com/video"
  python main.py --url "URL" --output video.mp4
  python main.py --url "URL" --upload
  python main.py --direct "https://xxx/index.m3u8"
  python main.py --batch urls.txt
  python main.py --batch urls.txt --upload
  python main.py --csv data.csv --upload
  python main.py --csv data.csv --csv-column link --upload
  python main.py --upload-only video.mp4
  python main.py --upload-only ./videos
  python main.py --debug "https://target-site.com/video"
"""

import asyncio
import argparse
import json
import sys
import os
import re
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
import config


# ========================
#  HELPER
# ========================

def sanitize_filename(name):
    """Bersihkan nama file dari karakter ilegal"""
    if not name:
        return "video"
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = name.strip('.')
    name = name[:100]
    return name if name else "video"


async def get_page_title(page):
    """Ambil judul dari halaman"""
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
        return title
    except:
        return None


# ========================
#  SINGLE SCRAPE
# ========================

async def scrape_single(url, output=None, referer=None, upload=False):
    """Scrape dan download satu video"""
    scraper = VideoScraper()

    try:
        await scraper.start_browser()
        m3u8_urls = await scraper.scrape(url)

        if m3u8_urls:
            best = pick_best_url(m3u8_urls)
            print(f"\n🏆 Best URL: {best}")

            if output:
                output_file = output
            else:
                title = await get_page_title(scraper.page)
                title = sanitize_filename(title)
                output_file = f"{title}.mp4"
                print(f"📝 Judul: {title}")

            success = download_video(
                m3u8_url=best,
                output_file=output_file,
                referer=referer or config.DEFAULT_REFERER,
            )

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
            print(f"# {url}")
            print(f"{'#'*60}")

            scraper.reset()

            try:
                m3u8_urls = await scraper.scrape(url)

                if m3u8_urls:
                    best = pick_best_url(m3u8_urls)

                    title = await get_page_title(scraper.page)
                    title = sanitize_filename(title) or f"video_{i+1}"
                    print(f"📝 Judul: {title}")

                    output = os.path.join(output_dir, f"{title}.mp4")
                    counter = 1
                    while os.path.exists(output):
                        output = os.path.join(output_dir, f"{title}_{counter}.mp4")
                        counter += 1

                    success = download_video(
                        m3u8_url=best,
                        output_file=output,
                        referer=referer or config.DEFAULT_REFERER,
                    )

                    if success:
                        downloaded_files.append(output)

                    results.append({
                        'url': url,
                        'title': title,
                        'status': 'OK' if success else 'DOWNLOAD_FAILED',
                        'm3u8': best,
                        'file': output if success else None,
                    })
                else:
                    results.append({
                        'url': url,
                        'title': '',
                        'status': 'NO_M3U8',
                        'file': None
                    })

            except Exception as e:
                results.append({
                    'url': url,
                    'title': '',
                    'status': f'ERROR: {e}',
                    'file': None
                })

            await asyncio.sleep(3)

    finally:
        await scraper.close()

    if upload and downloaded_files:
        print(f"\n\n{'='*60}")
        print(f"⬆️  UPLOADING {len(downloaded_files)} FILES TO STREAMTAPE")
        print(f"{'='*60}")

        upload_results = await upload_multiple(downloaded_files)

        for r in results:
            if r.get('file'):
                for u in upload_results:
                    if u['file'] == os.path.basename(r['file']):
                        r['streamtape'] = u['url']
                        break

    print(f"\n\n{'='*60}")
    print(f"📊 BATCH SUMMARY")
    print(f"{'='*60}")
    for r in results:
        icon = "✅" if r['status'] == 'OK' else "❌"
        title = r.get('title', 'Unknown')[:40] or r['url'][:40]
        st_url = r.get('streamtape', '')
        print(f"  {icon} {title}")
        print(f"     Status: {r['status']}")
        if st_url:
            print(f"     📺 {st_url}")

    return results


# ========================
#  CSV SCRAPE
# ========================

async def scrape_csv(csv_file, url_column='url', output_dir='.',
                     referer=None, upload=False):
    """
    Scrape dari CSV, download, upload, lalu UPDATE CSV in-place.

    - Kolom 'streamtape' otomatis dibuat kalau belum ada
    - Baris yang sudah punya link streamtape akan di-skip
    - CSV di-save setiap selesai 1 video (resume-safe)
    """

    # ── 1. Baca CSV ──
    if not os.path.exists(csv_file):
        print(f"❌ File tidak ditemukan: {csv_file}")
        return

    fieldnames, rows = read_csv(csv_file)

    if not fieldnames:
        print("❌ CSV kosong atau format tidak valid!")
        return

    print(f"📄 CSV: {csv_file}")
    print(f"   Kolom: {fieldnames}")
    print(f"   Baris: {len(rows)}")

    # ── 2. Detect kolom URL ──
    detected = detect_url_column(fieldnames, preferred=url_column)
    if not detected:
        print(f"\n❌ Kolom URL tidak ditemukan!")
        print(f"   Cari: '{url_column}'")
        print(f"   Tersedia: {fieldnames}")
        print(f"   Gunakan --csv-column NAMA_KOLOM")
        return
    url_column = detected
    print(f"   Kolom URL: '{url_column}'")

    # ── 3. Tambah kolom baru kalau belum ada ──
    added = ensure_columns(fieldnames)
    if added:
        print(f"   ➕ Kolom baru: {added}")

    # ── 4. Hitung yang perlu diproses ──
    to_process = get_pending_rows(rows, url_column=url_column)
    skipped = len(rows) - len(to_process)

    if skipped > 0:
        print(f"   ⏭️  Skip {skipped} baris (sudah ada streamtape)")

    if not to_process:
        print("\n✅ Semua baris sudah punya link streamtape!")
        return

    print(f"   🎯 Akan proses: {len(to_process)} video")

    # ── 5. Proses satu per satu ──
    os.makedirs(output_dir, exist_ok=True)

    scraper = VideoScraper()
    processed = 0

    try:
        await scraper.start_browser()

        for seq, idx in enumerate(to_process):
            row = rows[idx]
            url = row[url_column].strip()
            processed += 1

            print(f"\n\n{'#'*60}")
            print(f"# [{processed}/{len(to_process)}]  Baris CSV #{idx + 2}")
            print(f"# {url}")
            print(f"{'#'*60}")

            scraper.reset()

            try:
                m3u8_urls = await scraper.scrape(url)

                if not m3u8_urls:
                    print("❌ M3U8 tidak ditemukan")
                    row['status'] = 'NO_M3U8'
                    save_csv(csv_file, fieldnames, rows)
                    await asyncio.sleep(2)
                    continue

                best = pick_best_url(m3u8_urls)
                print(f"🏆 Best URL: {best}")

                # Judul
                title = await get_page_title(scraper.page)
                title = sanitize_filename(title) or f"video_{idx + 1}"
                row['title'] = row.get('title', '').strip() or title
                print(f"📝 Judul: {row['title']}")

                # Output file
                fname = sanitize_filename(row['title'])
                output = os.path.join(output_dir, f"{fname}.mp4")
                counter = 1
                while os.path.exists(output):
                    output = os.path.join(output_dir, f"{fname}_{counter}.mp4")
                    counter += 1

                # Download
                success = download_video(
                    m3u8_url=best,
                    output_file=output,
                    referer=referer or config.DEFAULT_REFERER,
                )

                if not success:
                    row['status'] = 'DOWNLOAD_FAILED'
                    save_csv(csv_file, fieldnames, rows)
                    await asyncio.sleep(2)
                    continue

                row['status'] = 'DOWNLOADED'

                # Upload
                if upload:
                    print(f"\n⬆️  Uploading ke Streamtape...")
                    st_url = await upload_to_streamtape(output)

                    if st_url:
                        row['streamtape'] = st_url
                        row['status'] = 'OK'
                        print(f"✅ Streamtape: {st_url}")
                    else:
                        row['status'] = 'UPLOAD_FAILED'
                        print("❌ Upload gagal")

            except Exception as e:
                print(f"❌ Error: {e}")
                row['status'] = f'ERROR: {str(e)[:80]}'

            # Save setiap selesai 1 video
            save_csv(csv_file, fieldnames, rows)
            print(f"💾 CSV updated ({processed}/{len(to_process)})")

            await asyncio.sleep(3)

    finally:
        await scraper.close()

    # ── 6. Final summary ──
    save_csv(csv_file, fieldnames, rows)

    print(f"\n\n{'='*60}")
    print(f"📊 CSV SUMMARY — {csv_file}")
    print(f"{'='*60}")
    print_summary(rows, skipped=skipped)
    print(f"\n💾 CSV saved: {csv_file}")

    return rows


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
        epilog="""
Examples:
  python main.py --url "https://site.com/video"
  python main.py --url "https://site.com/video" --upload
  python main.py --direct "https://xxx/index.m3u8"
  python main.py --batch urls.txt --upload
  python main.py --csv data.csv --upload
  python main.py --csv data.csv --csv-column video_link --upload
  python main.py --upload-only video.mp4
  python main.py --debug "https://site.com/video"
        """,
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
    parser.add_argument('--csv-column', default='url', help='Nama kolom URL di CSV (default: url)')

    return parser.parse_args()


def main():
    args = parse_args()
    loop = asyncio.get_event_loop()

    print(f"""
╔══════════════════════════════════════╗
║       🎬 VIDEO SCRAPER v1.3         ║
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
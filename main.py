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
import config


# ========================
#  HELPER
# ========================

def sanitize_filename(name):
    """Bersihkan nama file dari karakter ilegal"""
    if not name:
        return "video"
    # Hapus karakter ilegal
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', '', name)
    # Ganti spasi berlebih
    name = re.sub(r'\s+', ' ', name).strip()
    # Hapus titik di awal/akhir
    name = name.strip('.')
    # Batasi panjang
    name = name[:100]
    return name if name else "video"


async def get_page_title(page):
    """Ambil judul dari halaman"""
    try:
        title = await page.evaluate("""
            () => {
                // Coba h1
                const h1 = document.querySelector('h1');
                if (h1 && h1.innerText.trim()) return h1.innerText.trim();
                
                // Coba .video-title atau .entry-title
                const vt = document.querySelector('.video-title, .entry-title, .title');
                if (vt && vt.innerText.trim()) return vt.innerText.trim();
                
                // Coba og:title
                const og = document.querySelector('meta[property="og:title"]');
                if (og && og.content) return og.content.trim();
                
                // Coba title tag (hapus suffix website)
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

            # Ambil judul untuk nama file
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
            print(f"# {url}")
            print(f"{'#'*60}")

            scraper.reset()

            try:
                m3u8_urls = await scraper.scrape(url)

                if m3u8_urls:
                    best = pick_best_url(m3u8_urls)

                    # Ambil judul untuk nama file
                    title = await get_page_title(scraper.page)
                    title = sanitize_filename(title) or f"video_{i+1}"
                    print(f"📝 Judul: {title}")

                    # Cek duplikat nama file
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
        title = r.get('title', 'Unknown')[:40] or r['url'][:40]
        st_url = r.get('streamtape', '')
        print(f"  {icon} {title}")
        print(f"     Status: {r['status']}")
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
        epilog="""
Examples:
  # Scrape & download (nama file = judul video)
  python main.py --url "https://site.com/video"
  
  # Scrape & download dengan nama custom
  python main.py --url "https://site.com/video" --output custom.mp4

  # Scrape, download & upload ke Streamtape
  python main.py --url "https://site.com/video" --upload

  # Direct download M3U8
  python main.py --direct "https://xxx/index.m3u8"

  # Batch scrape (nama file = judul masing-masing)
  python main.py --batch urls.txt --output-dir ./videos
  python main.py --batch urls.txt --output-dir ./videos --upload

  # Upload saja (file sudah ada)
  python main.py --upload-only video.mp4
  python main.py --upload-only ./videos

  # Debug
  python main.py --debug "https://site.com/video"
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--url', help='URL halaman video untuk di-scrape')
    group.add_argument('--direct', help='URL M3U8 langsung (skip scraping)')
    group.add_argument('--batch', help='File berisi list URL (satu per baris)')
    group.add_argument('--upload-only', help='Upload file/folder ke Streamtape (tanpa scraping)')
    group.add_argument('--debug', help='Debug halaman (screenshot + info)')

    parser.add_argument('--output', '-o', default=None, help='Output filename (default: judul video)')
    parser.add_argument('--output-dir', default='.', help='Output directory untuk batch')
    parser.add_argument('--referer', '-r', default=None, help='Custom referer header')
    parser.add_argument('--upload', action='store_true', help='Upload ke Streamtape setelah download')

    return parser.parse_args()


def main():
    args = parse_args()
    loop = asyncio.get_event_loop()

    print(f"""
╔══════════════════════════════════════╗
║       🎬 VIDEO SCRAPER v1.2         ║
╚══════════════════════════════════════╝
    """)

    if args.direct:
        # ── Direct download ──
        success = download_direct(
            m3u8_url=args.direct,
            output_file=args.output or config.DEFAULT_OUTPUT,
            referer=args.referer or config.DEFAULT_REFERER,
        )

        # Upload jika flag --upload ada
        if success and args.upload:
            output_file = args.output or config.DEFAULT_OUTPUT
            loop.run_until_complete(upload_to_streamtape(output_file))

    elif args.url:
        # ── Single scrape ──
        loop.run_until_complete(
            scrape_single(
                url=args.url,
                output=args.output,
                referer=args.referer,
                upload=args.upload,
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
                upload=args.upload,
            )
        )

    elif args.upload_only:
        # ── Upload only ──
        loop.run_until_complete(upload_only(args.upload_only))

    elif args.debug:
        # ── Debug ──
        loop.run_until_complete(debug_page(args.debug))


if __name__ == '__main__':
    main()
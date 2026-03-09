"""Download video dari M3U8 / direct URL pakai ffmpeg"""

import subprocess
import os
import config


def pick_best_url(m3u8_urls):
    """Pilih URL terbaik dari list m3u8"""
    if not m3u8_urls:
        return None

    # Prioritas: index > master > apapun
    for keyword in ['index.m3u8', 'master.m3u8']:
        for url in m3u8_urls:
            if keyword in url.lower():
                return url

    # Ambil yang pertama
    return m3u8_urls[0]


def download_video(m3u8_url, output_file=None, referer=None):
    """Download HLS stream pakai ffmpeg"""
    output_file = output_file or config.DEFAULT_OUTPUT
    referer = referer or config.DEFAULT_REFERER

    print(f"\n⬇️  Downloading...")
    print(f"  Source : {m3u8_url}")
    print(f"  Output : {output_file}")
    print(f"  Referer: {referer}")

    cmd = ['ffmpeg', '-y']

    if referer:
        cmd += ['-headers', f'Referer: {referer}\r\n']

    cmd += [
        '-i', m3u8_url,
        '-c', 'copy',
        '-bsf:a', 'aac_adtstoasc',
        '-movflags', '+faststart',
        output_file,
    ]

    print(f"  Running ffmpeg...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.FFMPEG_TIMEOUT,
        )

        if os.path.exists(output_file):
            size_mb = os.path.getsize(output_file) / (1024 * 1024)
            print(f"\n  ✅ SUKSES!")
            print(f"  📦 File : {output_file}")
            print(f"  📏 Size : {size_mb:.1f} MB")
            return True
        else:
            print(f"\n  ❌ GAGAL!")
            print(f"  Error: {result.stderr[:500]}")
            return False

    except subprocess.TimeoutExpired:
        print(f"\n  ❌ TIMEOUT setelah {config.FFMPEG_TIMEOUT}s")
        return False
    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        return False


def download_direct(m3u8_url, output_file='video.mp4', referer=None):
    """Shortcut: langsung download tanpa scrape"""
    print(f"\n{'='*60}")
    print(f"⚡ DIRECT DOWNLOAD")
    print(f"{'='*60}")
    return download_video(m3u8_url, output_file, referer)
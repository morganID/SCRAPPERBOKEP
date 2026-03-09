"""Konfigurasi default video scraper"""
import logging

# ── Log Level ──
# DEBUG   = semua detail (development)
# INFO    = info penting saja (production)
# WARNING = hanya warning & error
LOG_LEVEL = 'INFO'

# ── Setup Logger ──
# Format: [LEVEL] time | message
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='[%(levelname)s] %(message)s',
)
# Browser
BROWSER_ARGS = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-blink-features=AutomationControlled',
    '--disable-web-security',
]

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

VIEWPORT = {'width': 1920, 'height': 1080}

# Anti-detection
STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
window.chrome = { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
    Promise.resolve({ state: Notification.permission }) :
    originalQuery(parameters)
);
"""

# Scraping
PAGE_TIMEOUT = 60000        # 60 detik
PLAY_ATTEMPTS = 5           # Berapa kali coba klik play
BUFFER_WAIT = 5             # Detik tunggu buffer
WAIT_AFTER_CLICK = 3        # Detik tunggu setelah klik

# Download
FFMPEG_TIMEOUT = 600        # 10 menit
DEFAULT_OUTPUT = 'video.mp4'
DEFAULT_REFERER = 'https://fem.pemersatu.link/'

# Play button selectors (urut prioritas)
PLAY_SELECTORS = [
    '.plyr__control--overlaid',
    '[data-plyr="play"]',
    'button[aria-label="Play"]',
    '.plyr__video-wrapper',
    '#video_player',
]

# Ad selectors yang akan dihapus
AD_SELECTORS = [
    '[id*="ad"]', '[class*="ad-"]', '[class*="ads"]',
    '[id*="pop"]', '[class*="pop"]',
    '[id*="overlay"]', '[class*="overlay"]',
    'iframe[src*="ad"]', 'iframe[src*="click"]',
    'div[onclick]', '[class*="banner"]', '[id*="banner"]',
]

STREAMTAPE_LOGIN = "03180fa90a4113de396a"      # ← Ganti
STREAMTAPE_KEY = "RX032YQkbdSdvv4"      # ← Ganti
CONCURRENT_UPLOAD = 3
STREAMTAPE_FOLDER = "H2fH6LGMOMk"  # ← Tambah ini


MAX_CONCURRENT_DOWNLOADS = 3
MAX_CONCURRENT_UPLOADS = 2

# ── File Management ──
DELETE_AFTER_UPLOAD = True  # Hapus file video setelah upload sukses
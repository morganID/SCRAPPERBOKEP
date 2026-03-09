"""
Video Scraper Configuration
==========================

Categories:
- LOGGING     : Log settings
- BROWSER     : Browser/stealth settings  
- SCRAPING    : Page scraping settings
- DOWNLOAD    : Download settings
- UPLOAD      : Streamtape upload settings
- CONCURRENT  : Concurrency limits
- FILES       : File management
"""

import logging


# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

LOG_LEVEL = 'INFO'  # DEBUG | INFO | WARNING


# ═══════════════════════════════════════════════════════════════════════════════
# BROWSER
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# SCRAPING
# ═══════════════════════════════════════════════════════════════════════════════

PAGE_TIMEOUT = 60000        # milliseconds
PLAY_ATTEMPTS = 5           # Retry count for play button
BUFFER_WAIT = 5             # Seconds to wait for buffer
WAIT_AFTER_CLICK = 3       # Seconds after clicking play

PLAY_SELECTORS = [
    '.plyr__control--overlaid',
    '[data-plyr="play"]',
    'button[aria-label="Play"]',
    '.plyr__video-wrapper',
    '#video_player',
]

AD_SELECTORS = [
    '[id*="ad"]', '[class*="ad-"]', '[class*="ads"]',
    '[id*="pop"]', '[class*="pop"]',
    '[id*="overlay"]', '[class*="overlay"]',
    'iframe[src*="ad"]', 'iframe[src*="click"]',
    'div[onclick]', '[class*="banner"]', '[id*="banner"]',
]


# ═══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════════════

FFMPEG_TIMEOUT = 600        # seconds (10 minutes)
DEFAULT_OUTPUT = 'video.mp4'
DEFAULT_REFERER = 'https://fem.pemersatu.link/'


# ═══════════════════════════════════════════════════════════════════════════════
# UPLOAD (Streamtape)
# ═══════════════════════════════════════════════════════════════════════════════

STREAMTAPE_LOGIN = "03180fa90a4113de396a"
STREAMTAPE_KEY = "RX032YQkbdSdvv4"
STREAMTAPE_FOLDER = "H2fH6LGMOMk"


# ═══════════════════════════════════════════════════════════════════════════════
# CONCURRENT
# ═══════════════════════════════════════════════════════════════════════════════

MAX_CONCURRENT_DOWNLOADS = 10
MAX_CONCURRENT_UPLOADS = 2


# ═══════════════════════════════════════════════════════════════════════════════
# FILES
# ═══════════════════════════════════════════════════════════════════════════════

DELETE_AFTER_UPLOAD = True


# ═══════════════════════════════════════════════════════════════════════════════
# SETUP LOGGER (run once)
# ═══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)

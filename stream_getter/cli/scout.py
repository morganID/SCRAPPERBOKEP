"""
Adapter Scout - Analyze website and generate adapter code automatically.

Usage:
    async with AdapterScout() as scout:
        result = await scout.analyze("https://example.com/video")
        print_report(result)
        code = generate_adapter_code(result)
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, List, Set
from urllib.parse import urlparse

from playwright.async_api import (
    async_playwright,
    Page,
    Request,
    Response,
    Playwright,
    Browser,
    BrowserContext,
)

import config

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STREAM_EXTENSIONS = (".m3u8", ".mpd", ".mp4", ".ts", ".webm", ".flv")

STREAM_URL_KEYWORDS = (
    "/playlist", "/manifest", "/chunk", "/segment",
    "master.m3u8", "index.m3u8", "/hls/", "/dash/",
)

STREAM_CONTENT_TYPES = (
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "application/dash+xml",
    "video/mp2t",
    "video/mp4",
    "video/webm",
)

VIDEO_EMBED_KEYWORDS = (
    "youtube", "vimeo", "dailymotion", "streamtape",
    "doodstream", "vidoza", "mixdrop", "filemoon",
    "streamwish", "vidhide", "embed", "player",
    "streamsb", "upstream", "mp4upload",
    "/e/", "/v/",
)

# (selector, type, confidence)
TITLE_CANDIDATES = [
    ("meta[property='og:title']", "meta", 10),
    ("h1",                        "text",  9),
    (".video-title",              "text",  8),
    (".entry-title",              "text",  7),
    ("meta[name='title']",        "meta",  6),
    ("h2",                        "text",  5),
    (".title",                    "text",  4),
    ("[class*='title']",          "text",  3),
]

# (selector, confidence)
PLAY_CANDIDATES = [
    (".jw-icon-playback",    10),
    (".vjs-big-play-button", 10),
    (".plyr__control--play",  9),
    ("button.play",           8),
    ("#playbutton",           8),
    (".play-button",          7),
    (".btn-play",             7),
    ("[class*='play']",       4),
    (".video-player button",  3),
]

# category -> selectors
AD_CANDIDATES = {
    "ad": [
        ".ads", ".ad", ".advertisement", "#ads",
        "[class*='ads-']", "[class*='ad-container']",
        "[id*='ads']", "[id*='banner']",
        "ins.adsbygoogle", "[id*='google_ads']",
        "iframe[src*='doubleclick']",
        "iframe[src*='googlesyndication']",
    ],
    "popup": [
        ".popup", ".modal", ".overlay",
        "[class*='popup']", "[class*='overlay']",
        "[class*='modal']",
    ],
    "close_button": [
        ".close-btn", ".dismiss",
        "[aria-label='Close']",
        "button[class*='close']",
        ".close",
        "[class*='close']",
    ],
    "anti_adblock": [
        "[class*='adblock']", "[id*='adblock']",
    ],
}

# (wait_until, timeout_ms) — dari cepat ke lambat
NAVIGATION_STRATEGIES = [
    ("commit",             15_000),
    ("domcontentloaded",   20_000),
    ("load",               30_000),
]

STREAM_WAIT_TIMEOUT = 15
STREAM_POLL_INTERVAL = 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Data Classes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class SelectorMatch:
    """A matched CSS selector with metadata."""
    selector: str
    value: Optional[str] = None
    tag: Optional[str] = None
    confidence: int = 1
    category: Optional[str] = None
    count: int = 1
    visible: int = 0


@dataclass
class VideoElement:
    """A detected video/iframe element."""
    selector: str
    src: Optional[str] = None
    tag: str = ""
    location: str = "main_page"
    is_video_embed: bool = False
    dimensions: Optional[str] = None
    poster: Optional[str] = None
    src_type: Optional[str] = None


@dataclass
class CapturedStream:
    """A network-captured stream URL."""
    url: str
    content_type: str = ""
    status: int = 0
    stream_type: str = "UNKNOWN"
    is_master: bool = False
    is_media: bool = False


@dataclass
class AnalysisResult:
    """Complete analysis result for a URL."""
    url: str
    domain: str
    page_title: str = ""
    titles: List[SelectorMatch] = field(default_factory=list)
    play_buttons: List[SelectorMatch] = field(default_factory=list)
    videos: List[VideoElement] = field(default_factory=list)
    ads: List[SelectorMatch] = field(default_factory=list)
    streams: List[CapturedStream] = field(default_factory=list)
    total_requests: int = 0
    error: Optional[str] = None

    @property
    def best_title_selector(self) -> Optional[str]:
        return self.titles[0].selector if self.titles else None

    @property
    def best_play_selector(self) -> Optional[str]:
        return self.play_buttons[0].selector if self.play_buttons else None

    @property
    def close_selectors(self) -> List[str]:
        return [
            a.selector for a in self.ads
            if a.category == "close_button" and a.visible > 0
        ]

    @property
    def popup_selectors(self) -> List[str]:
        return [
            a.selector for a in self.ads
            if a.category == "popup" and a.visible > 0
        ]

    @property
    def stream_types(self) -> Set[str]:
        return {s.stream_type for s in self.streams}

    @property
    def master_playlist_url(self) -> Optional[str]:
        for s in self.streams:
            if s.is_master:
                return s.url
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AdapterScout
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AdapterScout:
    """
    Analyze a video website to discover selectors and stream URLs,
    then generate adapter code for the domain.

    Usage:
        async with AdapterScout() as scout:
            result = await scout.analyze("https://example.com/video")
    """

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._streams: List[CapturedStream] = []
        self._seen_urls: Set[str] = set()
        self._request_count: int = 0

    # ── Context Manager ──

    async def __aenter__(self):
        await self._start()
        return self

    async def __aexit__(self, *args):
        await self._close()

    async def _start(self):
        """Launch browser and set up network interception."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=config.BROWSER_ARGS,
        )
        self._context = await self._browser.new_context(
            viewport=config.VIEWPORT,
            user_agent=config.USER_AGENT,
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(60_000)

        # Attach network listeners
        self._page.on("request", self._on_request)
        self._page.on("response", self._on_response)

    async def _close(self):
        """Shut down browser gracefully."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Network Interception
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _on_request(self, request: Request) -> None:
        self._request_count += 1

    async def _on_response(self, response: Response) -> None:
        """Inspect every response for stream URLs."""
        try:
            url = response.url
            if url in self._seen_urls:
                return

            content_type = response.headers.get("content-type", "")
            if not self._is_stream(url, content_type):
                return

            self._seen_urls.add(url)

            stream = CapturedStream(
                url=url,
                content_type=content_type,
                status=response.status,
                stream_type=self._classify_stream(url, content_type),
            )

            if ".m3u8" in url.lower():
                try:
                    body = await response.text()
                    stream.is_master = "#EXT-X-STREAM-INF" in body
                    stream.is_media = "#EXTINF" in body
                except Exception:
                    pass

            self._streams.append(stream)
            logger.info(
                "Stream captured: [%s] %s",
                stream.stream_type, url[:80],
            )

        except Exception as exc:
            logger.debug("Response handler error: %s", exc)

    # ── Stream Helpers ──

    @staticmethod
    def _is_stream(url: str, content_type: str) -> bool:
        """Check whether a URL/content-type looks like a stream."""
        low = url.lower()
        has_ext = any(
            low.endswith(ext) or f"{ext}?" in low
            for ext in STREAM_EXTENSIONS
        )
        has_kw = any(kw in low for kw in STREAM_URL_KEYWORDS)
        has_ct = any(ct in content_type for ct in STREAM_CONTENT_TYPES)
        return has_ext or has_kw or has_ct

    @staticmethod
    def _classify_stream(url: str, content_type: str) -> str:
        """Return HLS / DASH / MP4 / TS_SEGMENT / WEBM / UNKNOWN."""
        low = url.lower()
        if ".m3u8" in low or "mpegurl" in content_type:
            return "HLS"
        if ".mpd" in low or "dash" in content_type:
            return "DASH"
        if ".mp4" in low and "video" in content_type:
            return "MP4"
        if ".ts" in low:
            return "TS_SEGMENT"
        if ".webm" in low:
            return "WEBM"
        return "UNKNOWN"

    @property
    def _has_usable_streams(self) -> bool:
        """True jika sudah punya stream HLS/DASH/MP4."""
        return any(
            s.stream_type in ("HLS", "DASH", "MP4")
            for s in self._streams
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Navigation
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _navigate(self, url: str) -> bool:
        """
        Navigate with escalating strategies.
        If streams are already captured mid-loading, skip waiting.
        """
        for strategy, timeout in NAVIGATION_STRATEGIES:
            try:
                logger.info(
                    "Navigating (%s, %dms)...", strategy, timeout,
                )
                await self._page.goto(
                    url, wait_until=strategy, timeout=timeout,
                )
                logger.info("Loaded with strategy=%s", strategy)
                return True

            except Exception as exc:
                logger.warning(
                    "Navigation (%s) failed: %s", strategy, exc,
                )
                # Streams sudah tertangkap saat loading → lanjut
                if self._has_usable_streams:
                    logger.info(
                        "Navigation timed out BUT %d streams already "
                        "captured — continuing",
                        len(self._streams),
                    )
                    return True

        # Semua strategy gagal — cek apakah page punya content
        try:
            title = await self._page.title()
            if title:
                logger.info(
                    "All strategies failed but page has title: %s",
                    title[:50],
                )
                return True
        except Exception:
            pass

        return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Stream Waiting
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _wait_for_streams(
        self,
        timeout: int = STREAM_WAIT_TIMEOUT,
        min_streams: int = 1,
    ) -> bool:
        """
        Poll sampai punya minimal `min_streams` usable streams,
        atau sampai timeout.
        """
        logger.info(
            "Waiting up to %ds for streams (need %d)...",
            timeout, min_streams,
        )

        usable_count = 0
        for elapsed in range(timeout):
            usable = [
                s for s in self._streams
                if s.stream_type in ("HLS", "DASH", "MP4")
            ]
            usable_count = len(usable)

            if usable_count >= min_streams:
                logger.info(
                    "Got %d usable stream(s) after %ds",
                    usable_count, elapsed,
                )
                return True

            await asyncio.sleep(STREAM_POLL_INTERVAL)

        logger.info(
            "Stream wait finished: %d usable stream(s)", usable_count,
        )
        return usable_count > 0

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Main Analysis Pipeline
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def analyze(self, url: str) -> AnalysisResult:
        """
        Full analysis pipeline:
        1. Navigate (early exit jika streams sudah tertangkap)
        2. Discover selectors (title, play, ads)
        3. Dismiss ads/popups
        4. Click play → trigger stream loading
        5. Wait for streams (smart polling)
        6. Collect video elements & captured streams
        """
        self._reset()

        result = AnalysisResult(
            url=url,
            domain=urlparse(url).netloc,
        )

        # Step 1 — Navigate
        logger.info("Analyzing: %s", url)
        if not await self._navigate(url):
            result.error = "Failed to load page"
            result.streams = list(self._streams)
            result.total_requests = self._request_count
            return result

        await asyncio.sleep(2)
        result.page_title = await self._safe_title()

        # Step 2 — Discover selectors
        result.titles = await self._find_titles()
        result.play_buttons = await self._find_play_buttons()
        result.ads = await self._find_ads()

        # Step 3 — Dismiss ads/popups
        await self._dismiss_ads(result.ads)
        await asyncio.sleep(1)

        # Step 4 — Click play (skip jika stream sudah ada)
        if not self._has_usable_streams:
            clicked = await self._try_play(result.play_buttons)
            if clicked:
                await self._wait_for_streams(timeout=10)
            else:
                await self._wait_for_streams(timeout=5)
        else:
            logger.info(
                "Skipping play — %d stream(s) already captured",
                len(self._streams),
            )

        # Step 5 — Collect results
        result.videos = await self._find_videos()
        result.streams = list(self._streams)
        result.total_requests = self._request_count

        return result

    def _reset(self) -> None:
        """Clear state between runs."""
        self._streams.clear()
        self._seen_urls.clear()
        self._request_count = 0

    async def _safe_title(self) -> str:
        """Get page title without throwing."""
        try:
            return await self._page.title() or ""
        except Exception:
            return ""

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Selector Finders
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _find_titles(self) -> List[SelectorMatch]:
        """Find candidate title selectors, sorted by confidence."""
        results: List[SelectorMatch] = []

        for selector, sel_type, confidence in TITLE_CANDIDATES:
            try:
                el = await self._page.query_selector(selector)
                if not el:
                    continue

                value = (
                    await el.get_attribute("content")
                    if sel_type == "meta"
                    else await el.inner_text()
                )

                if value and value.strip():
                    results.append(SelectorMatch(
                        selector=selector,
                        value=value.strip()[:80],
                        confidence=confidence,
                    ))
            except Exception:
                continue

        results.sort(key=lambda m: m.confidence, reverse=True)
        return results

    async def _find_play_buttons(self) -> List[SelectorMatch]:
        """Find candidate play-button selectors, sorted by confidence."""
        results: List[SelectorMatch] = []

        for selector, confidence in PLAY_CANDIDATES:
            try:
                el = await self._page.query_selector(selector)
                if not el:
                    continue

                tag = await el.evaluate("e => e.tagName")
                is_visible = await el.is_visible()

                results.append(SelectorMatch(
                    selector=selector,
                    tag=tag,
                    confidence=confidence if is_visible else confidence // 2,
                    visible=1 if is_visible else 0,
                ))
            except Exception:
                continue

        results.sort(key=lambda m: m.confidence, reverse=True)
        return results

    async def _find_ads(self) -> List[SelectorMatch]:
        """Find ad / popup / close-button selectors."""
        results: List[SelectorMatch] = []

        for category, selectors in AD_CANDIDATES.items():
            for selector in selectors:
                try:
                    elements = await self._page.query_selector_all(selector)
                    if not elements:
                        continue

                    results.append(SelectorMatch(
                        selector=selector,
                        category=category,
                        count=len(elements),
                        visible=await self._count_visible(selector),
                    ))
                except Exception:
                    continue

        return results

    async def _find_videos(self) -> List[VideoElement]:
        """Find <video>, <source>, and <iframe> elements."""
        results: List[VideoElement] = []

        # Direct <video>
        for el in await self._page.query_selector_all("video"):
            try:
                results.append(VideoElement(
                    selector="video",
                    src=await self._attr(el, "src"),
                    poster=await self._attr(el, "poster"),
                    tag="video",
                ))
            except Exception:
                continue

        # <video> > <source>
        for el in await self._page.query_selector_all("video source"):
            try:
                results.append(VideoElement(
                    selector="video > source",
                    src=await self._attr(el, "src"),
                    src_type=await el.get_attribute("type"),
                    tag="source",
                ))
            except Exception:
                continue

        # <iframe>
        iframes = await self._page.query_selector_all("iframe")
        for idx, iframe in enumerate(iframes):
            try:
                src = await self._attr(iframe, "src", max_len=150)
                width = await iframe.get_attribute("width")
                height = await iframe.get_attribute("height")

                is_embed = bool(
                    src
                    and any(
                        kw in src.lower()
                        for kw in VIDEO_EMBED_KEYWORDS
                    )
                )

                results.append(VideoElement(
                    selector=f"iframe:nth-of-type({idx + 1})",
                    src=src,
                    tag="iframe",
                    is_video_embed=is_embed,
                    dimensions=f"{width}x{height}" if width else None,
                ))

                # Dive inside iframe
                if is_embed:
                    results.extend(
                        await self._probe_iframe(iframe, src or "")
                    )
            except Exception:
                continue

        return results

    async def _probe_iframe(
        self, iframe, iframe_src: str,
    ) -> List[VideoElement]:
        """Try to find <video> elements inside an iframe."""
        found: List[VideoElement] = []
        try:
            frame = await iframe.content_frame()
            if not frame:
                return found

            for vid in await frame.query_selector_all("video"):
                found.append(VideoElement(
                    selector="iframe >> video",
                    src=await self._attr(vid, "src"),
                    tag="video",
                    location=f"iframe[{iframe_src[:50]}]",
                ))
        except Exception as exc:
            logger.debug("Cannot access iframe content: %s", exc)
        return found

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Page Interactions
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _dismiss_ads(self, ads: List[SelectorMatch]) -> None:
        """Click close buttons and remove popup overlays."""
        for ad in ads:
            try:
                if ad.category == "close_button" and ad.visible > 0:
                    await self._page.click(
                        ad.selector, timeout=2_000,
                    )
                    await self._page.wait_for_timeout(500)
                elif ad.category == "popup" and ad.visible > 0:
                    await self._page.evaluate(
                        "(sel) => document.querySelectorAll(sel)"
                        ".forEach(e => e.remove())",
                        ad.selector,
                    )
            except Exception:
                continue

    async def _try_play(
        self, buttons: List[SelectorMatch],
    ) -> bool:
        """Click the best visible play button."""
        for btn in buttons[:3]:
            if not btn.visible:
                continue
            try:
                await self._page.click(
                    btn.selector, timeout=3_000,
                )
                logger.info("Clicked play: %s", btn.selector)
                return True
            except Exception:
                continue
        return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Utilities
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _count_visible(self, selector: str) -> int:
        """Count elements matching selector that are visible."""
        try:
            return await self._page.evaluate(
                """(sel) => Array.from(document.querySelectorAll(sel))
                            .filter(e => e.offsetParent !== null)
                            .length""",
                selector,
            )
        except Exception:
            return 0

    @staticmethod
    async def _attr(
        el, name: str, max_len: int = 100,
    ) -> Optional[str]:
        """Get an attribute value, truncated."""
        val = await el.get_attribute(name)
        return val[:max_len] if val else None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Code Generator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_adapter_code(result: AnalysisResult) -> str:
    """Produce a ready-to-save Python adapter file."""
    domain = result.domain.replace("www.", "")
    domain_snake = re.sub(r"[^a-zA-Z0-9]", "_", domain)
    class_name = (
        "".join(w.capitalize() for w in domain_snake.split("_") if w)
        + "Adapter"
    )

    best_title = result.best_title_selector or "h1"
    best_play = result.best_play_selector
    close_sels = result.close_selectors[:3]
    popup_sels = result.popup_selectors[:3]
    is_meta = best_title.startswith("meta")

    L: List[str] = []
    a = L.append

    # ── Header ──
    a('"""')
    a(f"Adapter for {domain}")
    a("Auto-generated by AdapterScout")
    a('"""')
    a("")
    a("from typing import Optional")
    a("from .. import BaseAdapter, AdapterRegistry")
    a("")
    a("")
    a("@AdapterRegistry.register")
    a(f"class {class_name}(BaseAdapter):")
    a(f'    """Adapter for {domain}."""')
    a("")
    a(f'    DOMAINS = ["{domain}", "www.{domain}"]')
    if result.stream_types:
        a(f"    STREAM_TYPES = {sorted(result.stream_types)}")
    a("")

    # ── before_scrape ──
    a("    async def before_scrape(self) -> None:")
    a('        """Prepare page — dismiss ads, click play."""')
    a("        await self.page.wait_for_timeout(2000)")

    if close_sels or popup_sels:
        a("")
        a("        # Dismiss ads / popups")
        for sel in close_sels:
            a(f'        await self._safe_click("{sel}")')
        for sel in popup_sels:
            a(f'        await self._safe_remove("{sel}")')

    if best_play:
        a("")
        a("        # Start playback")
        a(f'        await self._safe_click("{best_play}")')
        a("        await self.page.wait_for_timeout(3000)")
    a("")

    # ── extract_title ──
    a("    async def extract_title(self) -> Optional[str]:")
    if is_meta:
        a(f'        el = await self.page.query_selector("{best_title}")')
        a("        if el:")
        a('            return await el.get_attribute("content")')
        a("        return await self.page.title()")
    else:
        a("        return await self.page.evaluate(\"\"\"")
        a("            () => {")
        a(f"                const el = document.querySelector('{best_title}');")
        a("                return el")
        a("                    ? el.innerText.trim().split('\\n')[0]")
        a("                    : document.title;")
        a("            }")
        a('        """)')
    a("")

    # ── helpers ──
    a("    # ── helpers ──")
    a("")
    a("    async def _safe_click(self, selector: str) -> bool:")
    a('        """Click element if visible."""')
    a("        try:")
    a("            el = await self.page.query_selector(selector)")
    a("            if el and await el.is_visible():")
    a("                await el.click()")
    a("                return True")
    a("        except Exception:")
    a("            pass")
    a("        return False")
    a("")
    a("    async def _safe_remove(self, selector: str) -> None:")
    a('        """Remove matching elements from DOM."""')
    a("        try:")
    a("            await self.page.evaluate(")
    a('                "(sel) => document.querySelectorAll(sel)"')
    a('                ".forEach(e => e.remove())",')
    a("                selector,")
    a("            )")
    a("        except Exception:")
    a("            pass")

    return "\n".join(L)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Console Report
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_CATEGORY_ICONS = {
    "ad":            "📢",
    "popup":         "💬",
    "close_button":  "❎",
    "anti_adblock":  "🛡️",
}


def print_report(result: AnalysisResult) -> None:
    """Pretty-print the analysis to stdout."""
    bar = "=" * 55

    print(f"\n{bar}")
    print(f"📊  Analysis: {result.domain}")
    print(bar)
    print(f"   URL:      {result.url}")
    print(f"   Title:    {result.page_title[:60]}")
    print(f"   Requests: {result.total_requests}")

    if result.error:
        print(f"\n   ❌ Error: {result.error}")
        # Tetap tampilkan streams yang tertangkap
        if result.streams:
            print(f"\n   ⚠️  But {len(result.streams)} streams were "
                  "captured before error:")
            for s in result.streams:
                print(f"      [{s.stream_type}] {s.url[:80]}")
        return

    # Titles
    print(f"\n📝 Title selectors ({len(result.titles)}):")
    for t in result.titles[:3]:
        print(f'   [{t.confidence:2d}] {t.selector}  →  "{t.value}"')

    # Play buttons
    print(f"\n▶️  Play buttons ({len(result.play_buttons)}):")
    for p in result.play_buttons[:3]:
        icon = "✅" if p.visible else "👻"
        print(f"   [{p.confidence:2d}] {icon} {p.selector}  <{p.tag}>")

    # Video elements
    print(f"\n🎬 Video elements ({len(result.videos)}):")
    for v in result.videos[:5]:
        embed = " 🔗" if v.is_video_embed else ""
        print(f"   <{v.tag}>{embed}  src={v.src or 'N/A'}")
        if v.location != "main_page":
            print(f"       └─ inside {v.location}")

    # Ads
    print(f"\n🚫 Ad / popup elements ({len(result.ads)}):")
    for ad in result.ads[:6]:
        icon = _CATEGORY_ICONS.get(ad.category, "❓")
        print(f"   {icon} {ad.selector}: "
              f"{ad.count} total, {ad.visible} visible")

    # Streams
    print(f"\n🎯 Captured streams ({len(result.streams)}):")
    if result.streams:
        for s in result.streams:
            flag = " [MASTER]" if s.is_master else ""
            print(f"   [{s.stream_type}]{flag} {s.url[:80]}")
    else:
        print("   ⚠️  None captured — page may need more interaction")

    print(f"\n{bar}\n")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CLI Entry Point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_scout(url: str, save: bool = True) -> AnalysisResult:
    """Analyze a URL, print report, and generate adapter code."""
    import os
    
    print(f"\n{'=' * 55}")
    print("🎯  ADAPTER SCOUT — Auto-Generate Domain Adapter")
    print(f"{'=' * 55}")

    async with AdapterScout() as scout:
        result = await scout.analyze(url)

    print_report(result)

    if result.error and not result.streams:
        return result

    code = generate_adapter_code(result)
    domain_file = re.sub(
        r"[^a-zA-Z0-9]", "_",
        result.domain.replace("www.", ""),
    )

    print(f"{'=' * 55}")
    print("📄  Generated Adapter Code:")
    print(f"{'=' * 55}\n")
    print(code)
    
    # Auto-save to file
    if save:
        output_path = f"stream_getter/adapters/domains/{domain_file}.py"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(code)
        print(f"\n✅ Saved to: {output_path}")
    else:
        print(f"\n{'=' * 55}")
        print(f"💾  Save as: stream_getter/adapters/domains/{domain_file}.py")
        print(f"{'=' * 55}\n")

    return result
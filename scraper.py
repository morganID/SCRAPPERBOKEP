"""Video Scraper - Intercept M3U8/MP4 dari halaman video"""

import asyncio
import logging
from datetime import datetime
from playwright.async_api import async_playwright
import config

# ── Logger ──
logger = logging.getLogger(__name__)


class VideoScraper:
    def __init__(self):
        self.captured_urls = {
            'm3u8': [],
            'ts': [],
            'mp4': [],
            'videoplayback': [],
            'other_media': [],
        }
        self.browser = None
        self.page = None
        self.context = None
        self.pw = None
        self.m3u8_found = False

    # ========================
    #  BROWSER
    # ========================

    async def start_browser(self):
        """Launch browser dengan stealth mode"""
        self.pw = await async_playwright().start()

        self.browser = await self.pw.chromium.launch(
            headless=True,
            args=config.BROWSER_ARGS,
        )

        self.context = await self.browser.new_context(
            viewport=config.VIEWPORT,
            user_agent=config.USER_AGENT,
            bypass_csp=True,
            ignore_https_errors=True,
        )

        await self.context.add_init_script(config.STEALTH_SCRIPT)

        self.page = await self.context.new_page()
        self.page.on("request", self._on_request)
        self.page.on("response", self._on_response)

        logger.info("Browser started")

    async def close(self):
        """Tutup browser"""
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()
        logger.info("Browser closed")

    # ========================
    #  NETWORK INTERCEPTOR
    # ========================

    def _on_request(self, request):
        """Intercept setiap request keluar"""
        url = request.url

        if '.m3u8' in url:
            self.captured_urls['m3u8'].append({
                'url': url,
                'headers': dict(request.headers),
                'time': datetime.now().isoformat(),
            })
            self.m3u8_found = True
            logger.info(f"[M3U8] {url}")

        elif '.ts' in url:
            if url not in self.captured_urls['ts']:
                self.captured_urls['ts'].append(url)
                logger.debug(f"[TS] {url}")

        elif '.mp4' in url and 'ad' not in url.lower():
            self.captured_urls['mp4'].append(url)
            logger.info(f"[MP4] {url}")

        elif 'videoplayback' in url:
            self.captured_urls['videoplayback'].append(url)
            logger.info(f"[PLAYBACK] {url}")

    async def _on_response(self, response):
        """Intercept setiap response masuk"""
        content_type = response.headers.get('content-type', '')
        if 'mpegurl' in content_type or 'video' in content_type:
            self.captured_urls['other_media'].append({
                'url': response.url,
                'content_type': content_type,
            })
            logger.debug(f"[MEDIA] {response.url} ({content_type})")

    # ========================
    #  AD HANDLING
    # ========================

    async def close_popups(self):
        """Tutup semua tab/popup iklan"""
        closed = 0
        for page in self.context.pages:
            if page != self.page:
                try:
                    await page.close()
                    closed += 1
                except Exception:
                    pass
        if closed > 0:
            logger.debug(f"Closed {closed} popup(s)")

    async def remove_ad_overlays(self):
        """Hapus overlay iklan dari halaman"""
        try:
            await self.page.evaluate("""
            () => {
                document.querySelectorAll('*').forEach(el => {
                    const z = parseInt(getComputedStyle(el).zIndex);
                    if (z > 999 && el.tagName !== 'VIDEO' && !el.closest('.plyr')) {
                        el.remove();
                    }
                });

                const sels = %s;
                sels.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        if (!el.closest('.plyr') && !el.closest('.videocontent')) {
                            el.remove();
                        }
                    });
                });

                document.querySelectorAll('div').forEach(el => {
                    const style = getComputedStyle(el);
                    if (parseFloat(style.opacity) === 0 && style.position === 'fixed') {
                        el.remove();
                    }
                });
            }
            """ % str(config.AD_SELECTORS))
            logger.debug("Ad overlays removed")
        except Exception:
            logger.debug("Failed to remove overlays (non-critical)")

    # ========================
    #  PLAY VIDEO
    # ========================

    async def click_play(self):
        """Klik play button sambil handle ads"""
        for attempt in range(config.PLAY_ATTEMPTS):
            logger.debug(f"Play attempt {attempt + 1}/{config.PLAY_ATTEMPTS}")

            await self.remove_ad_overlays()
            await asyncio.sleep(1)

            clicked = False
            for selector in config.PLAY_SELECTORS:
                try:
                    btn = self.page.locator(selector).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click(timeout=3000)
                        logger.debug(f"Clicked '{selector}'")
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                await self._force_play()

            await asyncio.sleep(config.WAIT_AFTER_CLICK)
            await self.close_popups()

            if self.captured_urls['m3u8']:
                logger.info("M3U8 captured after play")
                return True

            is_playing = await self.page.evaluate("""
            () => {
                const v = document.querySelector('video');
                return v && !v.paused && v.currentTime > 0;
            }
            """)
            if is_playing:
                logger.debug("Video is playing")
                return True

        # Last resort
        await self._force_play()
        await asyncio.sleep(config.BUFFER_WAIT)
        return bool(self.captured_urls['m3u8'])

    async def _force_play(self):
        """Force play via JavaScript"""
        try:
            await self.page.evaluate("""
            () => {
                const v = document.querySelector('video');
                if (v) { v.muted = true; v.play(); }
            }
            """)
            logger.debug("Force play via JS")
        except Exception:
            logger.debug("Force play failed (non-critical)")

    # ========================
    #  EXTRACT M3U8
    # ========================

    async def extract_m3u8_from_page(self):
        """Extract m3u8 URL dari page source / JS variables"""
        try:
            return await self.page.evaluate("""
            () => {
                const urls = [];

                document.querySelectorAll('script').forEach(s => {
                    const m = s.textContent.match(/https?:\\/\\/[^\\s'"]+\\.m3u8[^\\s'"]*/g);
                    if (m) urls.push(...m);
                });

                const v = document.querySelector('video');
                if (v) {
                    if (v.src && !v.src.startsWith('blob:')) urls.push(v.src);
                    v.querySelectorAll('source').forEach(s => {
                        if (s.src) urls.push(s.src);
                    });
                }

                return urls;
            }
            """)
        except Exception:
            return []

    async def inject_interceptor(self):
        """Inject fetch/XHR interceptor"""
        try:
            await self.page.evaluate("""
            () => {
                window.__intercepted = [];

                const _fetch = window.fetch;
                window.fetch = function(...args) {
                    const url = args[0]?.url || args[0];
                    if (url) window.__intercepted.push(url);
                    return _fetch.apply(this, args);
                };

                const _open = XMLHttpRequest.prototype.open;
                XMLHttpRequest.prototype.open = function(m, url) {
                    window.__intercepted.push(url);
                    return _open.apply(this, arguments);
                };
            }
            """)
            logger.debug("JS interceptor injected")
        except Exception:
            logger.debug("Failed to inject interceptor")

    async def collect_js_intercepted(self):
        """Ambil URL dari JS interceptor"""
        try:
            js_urls = await self.page.evaluate("() => window.__intercepted || []")
            count = 0
            for u in js_urls:
                if isinstance(u, str) and '.m3u8' in u:
                    self.captured_urls['m3u8'].append({
                        'url': u,
                        'headers': {},
                        'time': datetime.now().isoformat(),
                    })
                    count += 1
            if count:
                logger.debug(f"Collected {count} M3U8 from JS interceptor")
        except Exception:
            pass

    # ========================
    #  SERVER INFO
    # ========================

    async def get_server_urls(self):
        """Ambil list server dari halaman"""
        try:
            return await self.page.evaluate("""
            () => {
                const items = [];
                document.querySelectorAll('.list-server-items li').forEach(li => {
                    items.push({
                        name: li.textContent.trim(),
                        url: li.getAttribute('data-video'),
                        active: li.classList.contains('active')
                    });
                });
                return items;
            }
            """)
        except Exception:
            return []

    # ========================
    #  MAIN SCRAPE
    # ========================

    async def scrape(self, url):
        """Main scraping function - return list of m3u8 URLs"""
        print(f"\n🎬 Scraping: {url}")

        # [1] Buka halaman
        logger.debug("Opening page...")
        try:
            await self.page.goto(
                url,
                wait_until='commit',
                timeout=config.PAGE_TIMEOUT,
            )
        except Exception as e:
            logger.warning(f"Page load timeout (continuing): {e}")

        await asyncio.sleep(config.BUFFER_WAIT)

        # [2] Cek m3u8 dari loading awal
        if self.captured_urls['m3u8']:
            logger.info("M3U8 found during page load")
            return self._get_unique_m3u8()

        # [3] Inject interceptor + info server
        await self.inject_interceptor()

        servers = await self.get_server_urls()
        if servers:
            logger.debug(f"{len(servers)} server(s) found")
            for s in servers:
                logger.debug(f"  {'[active]' if s.get('active') else '       '} "
                             f"{s['name']}: {(s.get('url') or '')[:80]}")

        # [4] Klik play
        await self.click_play()

        # [5] Kumpulkan semua URL
        await asyncio.sleep(config.BUFFER_WAIT)
        await self.collect_js_intercepted()

        page_m3u8 = await self.extract_m3u8_from_page()
        for u in page_m3u8:
            if '.m3u8' in u:
                self.captured_urls['m3u8'].append({
                    'url': u,
                    'headers': {},
                    'time': datetime.now().isoformat(),
                })

        result = self._get_unique_m3u8()

        if result:
            print(f"✅ Found {len(result)} M3U8 URL(s)")
        else:
            print(f"❌ No M3U8 found")

        return result

    def _get_unique_m3u8(self):
        """Deduplicate dan return m3u8 URLs"""
        unique = list({item['url'] for item in self.captured_urls['m3u8']})

        logger.info(f"Results: {len(unique)} M3U8, "
                    f"{len(self.captured_urls['ts'])} TS, "
                    f"{len(self.captured_urls['mp4'])} MP4, "
                    f"{len(self.captured_urls['videoplayback'])} Playback, "
                    f"{len(self.captured_urls['other_media'])} Media")

        for i, url in enumerate(unique):
            logger.info(f"  M3U8 [{i+1}] {url}")

        return unique

    def reset(self):
        """Reset captured URLs untuk scrape berikutnya"""
        self.captured_urls = {
            'm3u8': [], 'ts': [], 'mp4': [],
            'videoplayback': [], 'other_media': [],
        }
        self.m3u8_found = False

    # ========================
    #  DEBUG
    # ========================

    async def debug(self, url, screenshot_path='debug_screenshot.png'):
        """Debug halaman - screenshot + info"""
        print(f"\n🔍 DEBUG: {url}\n")

        try:
            await self.page.goto(
                url, wait_until='commit', timeout=config.PAGE_TIMEOUT
            )
        except Exception:
            pass

        await asyncio.sleep(5)

        await self.page.screenshot(path=screenshot_path)
        print(f"📸 Screenshot: {screenshot_path}")

        iframes = await self.page.evaluate("""
        () => Array.from(document.querySelectorAll('iframe'))
              .map(f => ({src: f.src, id: f.id, class: f.className}))
        """)
        print(f"\n📦 Iframes ({len(iframes)}):")
        for f in iframes:
            print(f"  {f}")

        videos = await self.page.evaluate("""
        () => Array.from(document.querySelectorAll('video'))
              .map(v => ({src: v.src, poster: v.poster, currentSrc: v.currentSrc}))
        """)
        print(f"\n🎬 Videos ({len(videos)}):")
        for v in videos:
            print(f"  {v}")

        servers = await self.get_server_urls()
        print(f"\n🖥️ Servers ({len(servers)}):")
        for s in servers:
            arrow = "→" if s.get('active') else " "
            print(f"  {arrow} {s['name']}: {(s.get('url') or '')[:80]}")

        return {
            'iframes': iframes,
            'videos': videos,
            'servers': servers,
        }
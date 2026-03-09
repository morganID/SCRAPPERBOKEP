"""Video Scraper - Intercept M3U8/MP4 dari halaman video"""

import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
import config


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

        print("✅ Browser started")

    async def close(self):
        """Tutup browser"""
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()
        print("🔒 Browser closed")

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
            print(f"  🎯 [M3U8] {url}")

        elif '.ts' in url:
            if url not in self.captured_urls['ts']:
                self.captured_urls['ts'].append(url)

        elif '.mp4' in url and 'ad' not in url.lower():
            self.captured_urls['mp4'].append(url)
            print(f"  🎯 [MP4] {url}")

        elif 'videoplayback' in url:
            self.captured_urls['videoplayback'].append(url)
            print(f"  🎯 [PLAYBACK] {url}")

    async def _on_response(self, response):
        """Intercept setiap response masuk"""
        content_type = response.headers.get('content-type', '')
        if 'mpegurl' in content_type or 'video' in content_type:
            self.captured_urls['other_media'].append({
                'url': response.url,
                'content_type': content_type,
            })

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
                except:
                    pass
        if closed > 0:
            print(f"    🗑️ Tutup {closed} popup")

    async def remove_ad_overlays(self):
        """Hapus overlay iklan dari halaman"""
        try:
            await self.page.evaluate("""
            () => {
                // Hapus overlay z-index tinggi
                document.querySelectorAll('*').forEach(el => {
                    const z = parseInt(getComputedStyle(el).zIndex);
                    if (z > 999 && el.tagName !== 'VIDEO' && !el.closest('.plyr')) {
                        el.remove();
                    }
                });

                // Hapus ad elements
                const sels = %s;
                sels.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        if (!el.closest('.plyr') && !el.closest('.videocontent')) {
                            el.remove();
                        }
                    });
                });

                // Hapus overlay transparan
                document.querySelectorAll('div').forEach(el => {
                    const style = getComputedStyle(el);
                    if (parseFloat(style.opacity) === 0 && style.position === 'fixed') {
                        el.remove();
                    }
                });
            }
            """ % str(config.AD_SELECTORS))
            print("    🧹 Overlay dihapus")
        except:
            pass

    # ========================
    #  PLAY VIDEO
    # ========================

    async def click_play(self):
        """Klik play button sambil handle ads"""
        for attempt in range(config.PLAY_ATTEMPTS):
            print(f"\n  ▶️ Play attempt {attempt + 1}/{config.PLAY_ATTEMPTS}")

            await self.remove_ad_overlays()
            await asyncio.sleep(1)

            # Coba klik setiap selector
            clicked = False
            for selector in config.PLAY_SELECTORS:
                try:
                    btn = self.page.locator(selector).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click(timeout=3000)
                        print(f"    ✅ Klik '{selector}'")
                        clicked = True
                        break
                except:
                    continue

            if not clicked:
                await self._force_play()

            await asyncio.sleep(config.WAIT_AFTER_CLICK)
            await self.close_popups()

            # Cek apakah m3u8 sudah ketangkap
            if self.captured_urls['m3u8']:
                print("    ✅ M3U8 ketangkap!")
                return True

            # Cek apakah video playing
            is_playing = await self.page.evaluate("""
            () => {
                const v = document.querySelector('video');
                return v && !v.paused && v.currentTime > 0;
            }
            """)
            if is_playing:
                print("    ✅ Video playing!")
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
            print("    ⚡ Force play via JS")
        except:
            pass

    # ========================
    #  EXTRACT M3U8
    # ========================

    async def extract_m3u8_from_page(self):
        """Extract m3u8 URL dari page source / JS variables"""
        try:
            return await self.page.evaluate("""
            () => {
                const urls = [];

                // Dari script tags
                document.querySelectorAll('script').forEach(s => {
                    const m = s.textContent.match(/https?:\\/\\/[^\\s'"]+\\.m3u8[^\\s'"]*/g);
                    if (m) urls.push(...m);
                });

                // Dari video element
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
        except:
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
        except:
            pass

    async def collect_js_intercepted(self):
        """Ambil URL dari JS interceptor"""
        try:
            js_urls = await self.page.evaluate("() => window.__intercepted || []")
            for u in js_urls:
                if isinstance(u, str) and '.m3u8' in u:
                    self.captured_urls['m3u8'].append({
                        'url': u,
                        'headers': {},
                        'time': datetime.now().isoformat(),
                    })
        except:
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
        except:
            return []

    # ========================
    #  MAIN SCRAPE
    # ========================

    async def scrape(self, url):
        """Main scraping function - return list of m3u8 URLs"""
        print(f"\n{'='*60}")
        print(f"🎬 SCRAPING: {url}")
        print(f"{'='*60}\n")

        # [1] Buka halaman (jangan tunggu networkidle)
        print("[1/5] Membuka halaman...")
        try:
            await self.page.goto(
                url,
                wait_until='commit',
                timeout=config.PAGE_TIMEOUT,
            )
        except Exception as e:
            print(f"  ⚠️ Timeout tapi lanjut: {e}")

        await asyncio.sleep(config.BUFFER_WAIT)

        # [2] Cek m3u8 dari loading awal
        print("\n[2/5] Cek M3U8 dari loading awal...")
        if self.captured_urls['m3u8']:
            print("  ✅ M3U8 sudah ketangkap!")
            return self._get_unique_m3u8()

        # [3] Inject interceptor + info server
        print("\n[3/5] Inject interceptor...")
        await self.inject_interceptor()

        servers = await self.get_server_urls()
        if servers:
            print(f"  📡 {len(servers)} server ditemukan:")
            for s in servers:
                icon = "🟢" if s.get('active') else "⚪"
                url_preview = (s.get('url') or '')[:80]
                print(f"    {icon} {s['name']}: {url_preview}")

        # [4] Klik play (handle ads)
        print("\n[4/5] Play video...")
        await self.click_play()

        # [5] Kumpulkan semua URL
        print("\n[5/5] Mengumpulkan URL...")
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

        return self._get_unique_m3u8()

    def _get_unique_m3u8(self):
        """Deduplicate dan return m3u8 URLs"""
        unique = list({item['url'] for item in self.captured_urls['m3u8']})

        print(f"\n{'='*60}")
        print(f"📊 HASIL:")
        print(f"  M3U8      : {len(unique)}")
        print(f"  TS        : {len(self.captured_urls['ts'])} segments")
        print(f"  MP4       : {len(self.captured_urls['mp4'])}")
        print(f"  Playback  : {len(self.captured_urls['videoplayback'])}")
        print(f"  Media     : {len(self.captured_urls['other_media'])}")

        if unique:
            print(f"\n📹 M3U8 URLs:")
            for i, url in enumerate(unique):
                print(f"  [{i+1}] {url}")

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
            await self.page.goto(url, wait_until='commit', timeout=config.PAGE_TIMEOUT)
        except:
            pass

        await asyncio.sleep(5)

        # Screenshot
        await self.page.screenshot(path=screenshot_path)
        print(f"📸 Screenshot: {screenshot_path}")

        # Iframes
        iframes = await self.page.evaluate("""
        () => Array.from(document.querySelectorAll('iframe'))
              .map(f => ({src: f.src, id: f.id, class: f.className}))
        """)
        print(f"\n📦 Iframes ({len(iframes)}):")
        for f in iframes:
            print(f"  {f}")

        # Videos
        videos = await self.page.evaluate("""
        () => Array.from(document.querySelectorAll('video'))
              .map(v => ({src: v.src, poster: v.poster, currentSrc: v.currentSrc}))
        """)
        print(f"\n🎬 Videos ({len(videos)}):")
        for v in videos:
            print(f"  {v}")

        # Servers
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
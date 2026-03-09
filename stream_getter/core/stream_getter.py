"""
Main VideoScraper class - orchestrates browser and network interception.
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any

from playwright.async_api import Page

import config
from .browser import BrowserManager
from .interceptor import NetworkInterceptor, JavaScriptInterceptor
from ..adapters import AdapterRegistry

logger = logging.getLogger(__name__)


class VideoScraper:
    """
    Main video scraper class that coordinates browser and network interception.
    
    Usage:
        scraper = VideoScraper()
        await scraper.start_browser()
        m3u8_urls = await scraper.scrape("https://example.com/video")
        await scraper.close()
    """
    
    def __init__(self) -> None:
        """Initialize the video scraper."""
        self.browser = BrowserManager()
        self.interceptor = NetworkInterceptor()
    
    @property
    def page(self) -> Optional[Page]:
        """Get the current page."""
        return self.browser.page
    
    @property
    def captured_urls(self) -> Dict[str, List[Any]]:
        """Get all captured URLs."""
        return self.interceptor.get_all_captured()
    
    async def start_browser(self) -> None:
        """
        Start the browser with stealth mode.
        
        Raises:
            Exception: If browser fails to start.
        """
        await self.browser.start()
        
        # Attach network interceptors
        self.page.on("request", self.interceptor.on_request)
        self.page.on("response", self.interceptor.on_response)
    
    async def close(self) -> None:
        """Close all browser resources."""
        await self.browser.close()
    
    def reset(self) -> None:
        """Reset captured URLs for next scrape."""
        self.interceptor.reset()
    
    async def scrape(self, url: str) -> List[str]:
        """
        Scrape a video page for M3U8 URLs.
        
        Args:
            url: The video page URL to scrape.
            
        Returns:
            List of M3U8 URLs found on the page.
        """
        # Get domain-specific adapter
        adapter = AdapterRegistry.get_adapter(url, self.page, self.interceptor)
        domain = AdapterRegistry.get_domain(url)
        logger.debug(f"Using adapter for: {domain}")
        
        # Call before_scrape hook
        await adapter.before_scrape()
        
        # Step 1: Navigate to the page
        logger.debug("Opening page...")
        
        # Get custom referer if needed
        referer = adapter.get_referer()
        await self.browser.navigate(url, referer=referer)
        await asyncio.sleep(config.BUFFER_WAIT)
        
        # Handle ads/popups after page load
        await adapter.handle_ads()
        
        # Step 2: Check for M3U8 during initial load
        if self.interceptor.has_m3u8():
            logger.debug("M3U8 found during page load")
            result = self.interceptor.get_m3u8_urls()
            return await adapter.after_scrape(result)
        
        # Step 3: Inject JavaScript interceptors
        await JavaScriptInterceptor.inject(self.page)
        
        # Step 4: Click play button using adapter's method
        await adapter.click_play()
        
        # Handle ads after clicking play
        await adapter.handle_ads()
        
        # Step 5: Collect all captured URLs
        await asyncio.sleep(config.BUFFER_WAIT)
        await JavaScriptInterceptor.collect_m3u8(self.page, self.interceptor.captured_urls)
        
        # Extract from page source
        page_m3u8 = await JavaScriptInterceptor.extract_from_page(self.page)
        for url in page_m3u8:
            if '.m3u8' in url:
                self.interceptor.captured_urls['m3u8'].append({
                    'url': url,
                    'headers': {},
                })
        
        result = self.interceptor.get_m3u8_urls()
        
        # Call after_scrape hook
        result = await adapter.after_scrape(result)
        
        if result:
            print(f"✅ Found {len(result)} M3U8 URL(s)")
        else:
            print(f"❌ No M3U8 found")
        
        return result
    
    async def _click_play_button(self) -> bool:
        """
        Click the play button to start video playback.
        
        Returns:
            True if video is playing or M3U8 was captured.
        """
        for attempt in range(config.PLAY_ATTEMPTS):
            logger.debug(f"Play attempt {attempt + 1}/{config.PLAY_ATTEMPTS}")
            
            await self._remove_ad_overlays()
            await asyncio.sleep(1)
            
            # Try clicking play buttons
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
            await self.browser.close_popups()
            
            if self.interceptor.has_m3u8():
                logger.debug("M3U8 captured after play")
                return True
            
            # Check if video is playing
            is_playing = await self.page.evaluate("""
                () => {
                    const v = document.querySelector('video');
                    return v && !v.paused && v.currentTime > 0;
                }
            """)
            if is_playing:
                logger.debug("Video is playing")
                return True
        
        # Last resort: force play
        await self._force_play()
        await asyncio.sleep(config.BUFFER_WAIT)
        return bool(self.interceptor.has_m3u8())
    
    async def _force_play(self) -> None:
        """Force video playback via JavaScript."""
        try:
            await self.page.evaluate("""
                () => {
                    const v = document.querySelector('video');
                    if (v) { v.muted = true; v.play(); }
                }
            """)
            logger.debug("Force play via JS")
        except Exception as e:
            logger.debug(f"Force play failed: {e}")
    
    async def _remove_ad_overlays(self) -> None:
        """Remove advertisement overlays from the page."""
        try:
            await self.page.evaluate(f"""
                () => {{
                    // Remove high z-index elements (except video player)
                    document.querySelectorAll('*').forEach(el => {{
                        const z = parseInt(getComputedStyle(el).zIndex);
                        if (z > 999 && el.tagName !== 'VIDEO' && !el.closest('.plyr')) {{
                            el.remove();
                        }}
                    }});

                    // Remove ad selectors
                    const sels = {str(config.AD_SELECTORS)};
                    sels.forEach(sel => {{
                        document.querySelectorAll(sel).forEach(el => {{
                            if (!el.closest('.plyr') && !el.closest('.videocontent')) {{
                                el.remove();
                            }}
                        }});
                    }});

                    // Remove invisible fixed elements
                    document.querySelectorAll('div').forEach(el => {{
                        const style = getComputedStyle(el);
                        if (parseFloat(style.opacity) === 0 && style.position === 'fixed') {{
                            el.remove();
                        }}
                    }});
                }}
            """)
            logger.debug("Ad overlays removed")
        except Exception as e:
            logger.debug(f"Failed to remove overlays: {e}")
    
    async def get_page_title(self) -> Optional[str]:
        """
        Extract the page title using multiple strategies.
        
        Returns:
            The page title or None if not found.
        """
        try:
            title = await self.page.evaluate("""
                () => {
                    // Try h1 - get only first line
                    const h1 = document.querySelector('h1');
                    if (h1 && h1.innerText.trim()) {
                        const lines = h1.innerText.trim().split(/\n/);
                        return lines[0].trim();
                    }

                    // Try video title class
                    const vt = document.querySelector('.video-title, .entry-title, .title');
                    if (vt && vt.innerText.trim()) {
                        const lines = vt.innerText.trim().split(/\n/);
                        return lines[0].trim();
                    }

                    // Try Open Graph title
                    const og = document.querySelector('meta[property="og:title"]');
                    if (og && og.content) return og.content.trim();

                    // Fallback to document title
                    const title = document.title;
                    if (title) return title.split(/[-|–—]/)[0].trim();

                    return null;
                }
            """)
            logger.debug(f"Page title: {title}")
            return title
        except Exception as e:
            logger.debug(f"Failed to get title: {e}")
            return None
    
    async def get_server_urls(self) -> List[Dict[str, Any]]:
        """
        Get list of server URLs from the page.
        
        Returns:
            List of server dictionaries with name, url, and active status.
        """
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
    
    async def debug(self, url: str, screenshot_path: str = 'debug_screenshot.png') -> Dict[str, Any]:
        """
        Debug a page - capture screenshot and extract page info.
        
        Args:
            url: The URL to debug.
            screenshot_path: Path to save the screenshot.
            
        Returns:
            Dictionary containing iframes, videos, and servers.
        """
        print(f"\n🔍 DEBUG: {url}\n")
        
        await self.browser.navigate(url)
        await asyncio.sleep(5)
        
        await self.browser.screenshot(screenshot_path)
        print(f"📸 Screenshot: {screenshot_path}")
        
        # Get iframes
        iframes = await self.page.evaluate("""
            () => Array.from(document.querySelectorAll('iframe'))
                  .map(f => ({src: f.src, id: f.id, class: f.className}))
        """)
        print(f"\n📦 Iframes ({len(iframes)}):")
        for f in iframes:
            print(f"  {f}")
        
        # Get videos
        videos = await self.page.evaluate("""
            () => Array.from(document.querySelectorAll('video'))
                  .map(v => ({src: v.src, poster: v.poster, currentSrc: v.currentSrc}))
        """)
        print(f"\n🎬 Videos ({len(videos)}):")
        for v in videos:
            print(f"  {v}")
        
        # Get servers
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

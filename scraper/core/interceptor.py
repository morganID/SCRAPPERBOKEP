"""
Network interception for capturing video stream URLs.
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

import config

logger = logging.getLogger(__name__)


class NetworkInterceptor:
    """
    Intercepts network requests and responses to capture video stream URLs.
    
    Captures M3U8, TS, MP4, and other media URLs from network traffic.
    """
    
    def __init__(self) -> None:
        """Initialize the network interceptor."""
        self.captured_urls: Dict[str, List[Any]] = {
            'm3u8': [],
            'ts': [],
            'mp4': [],
            'videoplayback': [],
            'other_media': [],
        }
        self.m3u8_found = False
    
    def reset(self) -> None:
        """Reset captured URLs for a new scrape."""
        self.captured_urls = {
            'm3u8': [],
            'ts': [],
            'mp4': [],
            'videoplayback': [],
            'other_media': [],
        }
        self.m3u8_found = False
    
    def on_request(self, request) -> None:
        """
        Handle intercepted network request.
        
        Args:
            request: The intercepted request object.
        """
        url = request.url
        
        # Check for M3U8 (HLS manifest)
        if '.m3u8' in url:
            self.captured_urls['m3u8'].append({
                'url': url,
                'headers': dict(request.headers),
                'time': datetime.now().isoformat(),
            })
            self.m3u8_found = True
            logger.debug(f"[M3U8] {url}")
        
        # Check for TS segments
        elif '.ts' in url:
            if url not in self.captured_urls['ts']:
                self.captured_urls['ts'].append(url)
                logger.debug(f"[TS] {url}")
        
        # Check for MP4 (excluding ads)
        elif '.mp4' in url and 'ad' not in url.lower():
            self.captured_urls['mp4'].append(url)
            logger.debug(f"[MP4] {url}")
        
        # Check for videoplayback URLs
        elif 'videoplayback' in url:
            self.captured_urls['videoplayback'].append(url)
            logger.debug(f"[PLAYBACK] {url}")
    
    def on_response(self, response) -> None:
        """
        Handle intercepted network response.
        
        Args:
            response: The intercepted response object.
        """
        content_type = response.headers.get('content-type', '')
        
        if 'mpegurl' in content_type or 'video' in content_type:
            self.captured_urls['other_media'].append({
                'url': response.url,
                'content_type': content_type,
            })
            logger.debug(f"[MEDIA] {response.url} ({content_type})")
    
    def get_m3u8_urls(self) -> List[str]:
        """
        Get unique M3U8 URLs from captured data.
        
        Returns:
            List of unique M3U8 URLs.
        """
        unique = list({item['url'] for item in self.captured_urls['m3u8']})
        
        logger.debug(
            f"Results: {len(unique)} M3U8, "
            f"{len(self.captured_urls['ts'])} TS, "
            f"{len(self.captured_urls['mp4'])} MP4, "
            f"{len(self.captured_urls['videoplayback'])} Playback, "
            f"{len(self.captured_urls['other_media'])} Media"
        )
        
        for i, url in enumerate(unique):
            logger.debug(f"  M3U8 [{i+1}] {url}")
        
        return unique
    
    def has_m3u8(self) -> bool:
        """Check if any M3U8 URLs were captured."""
        return bool(self.captured_urls['m3u8'])
    
    def get_all_captured(self) -> Dict[str, List[Any]]:
        """Get all captured URLs."""
        return self.captured_urls.copy()
    
    @staticmethod
    def pick_best_url(m3u8_urls: List[str]) -> Optional[str]:
        """
        Pick the best M3U8 URL from a list.
        
        Prioritizes index.m3u8 and master.m3u8 URLs.
        
        Args:
            m3u8_urls: List of M3U8 URLs.
            
        Returns:
            The best URL or None if list is empty.
        """
        if not m3u8_urls:
            return None
        
        # Priority keywords
        for keyword in ['index.m3u8', 'master.m3u8']:
            for url in m3u8_urls:
                if keyword in url.lower():
                    return url
        
        # Default: return first URL
        return m3u8_urls[0]


class JavaScriptInterceptor:
    """
    Injects JavaScript to intercept fetch/XHR requests.
    """
    
    @staticmethod
    async def inject(page) -> None:
        """
        Inject fetch and XHR interceptors into the page.
        
        Args:
            page: Playwright page object.
        """
        try:
            await page.evaluate("""
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
        except Exception as e:
            logger.debug(f"Failed to inject interceptor: {e}")
    
    @staticmethod
    async def collect_m3u8(page, captured_urls: Dict[str, List]) -> int:
        """
        Collect M3U8 URLs from JavaScript interceptor.
        
        Args:
            page: Playwright page object.
            captured_urls: Dictionary to collect URLs into.
            
        Returns:
            Number of M3U8 URLs found.
        """
        try:
            js_urls = await page.evaluate("() => window.__intercepted || []")
            count = 0
            for u in js_urls:
                if isinstance(u, str) and '.m3u8' in u:
                    captured_urls['m3u8'].append({
                        'url': u,
                        'headers': {},
                        'time': datetime.now().isoformat(),
                    })
                    count += 1
            if count:
                logger.debug(f"Collected {count} M3U8 from JS interceptor")
            return count
        except Exception:
            return 0
    
    @staticmethod
    async def extract_from_page(page) -> List[str]:
        """
        Extract M3U8 URLs from page source and JavaScript variables.
        
        Args:
            page: Playwright page object.
            
        Returns:
            List of M3U8 URLs found in the page.
        """
        try:
            return await page.evaluate("""
                () => {
                    const urls = [];

                    // Check scripts
                    document.querySelectorAll('script').forEach(s => {
                        const m = s.textContent.match(/https?:\\/\\/[^\\s'"]+\\.m3u8[^\\s'"]*/g);
                        if (m) urls.push(...m);
                    });

                    // Check video elements
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

"""
Domain Adapters - Different behavior for different video sites.

Usage:
    from stream_getter.adapters import AdapterRegistry, BaseAdapter
    
    # Adapters are auto-registered when imported
    # Create custom adapter in adapters/domains/your_site.py
"""

from urllib.parse import urlparse
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod

# Auto-load domain adapters
try:
    from . import domains
except ImportError:
    pass


class BaseAdapter(ABC):
    """
    Base class for domain-specific adapters.
    
    Each adapter handles a specific video site with custom logic for:
    - Finding the video player
    - Extracting title
    - Handling auth/referer
    - Post-processing
    """
    
    # Domain patterns this adapter handles
    DOMAINS: List[str] = []
    
    def __init__(self, page, interceptor):
        self.page = page
        self.interceptor = interceptor
    
    @classmethod
    def matches(cls, url: str) -> bool:
        """Check if this adapter handles the given URL."""
        parsed = urlparse(url)
        return any(domain in parsed.netloc for domain in cls.DOMAINS)
    
    @abstractmethod
    async def extract_title(self) -> Optional[str]:
        """Extract video title from the page."""
        pass
    
    @abstractmethod
    async def click_play(self) -> bool:
        """Click the play button to trigger video loading."""
        pass
    
    async def before_scrape(self) -> None:
        """Hook called before scraping. Override for custom behavior."""
        pass
    
    async def after_scrape(self, m3u8_urls: List[str]) -> List[str]:
        """Hook called after scraping. Override for post-processing."""
        return m3u8_urls
    
    def get_referer(self) -> Optional[str]:
        """Get custom referer if needed. Override per domain."""
        return None


class DefaultAdapter(BaseAdapter):
    """Default adapter for unknown domains."""
    
    DOMAINS = ["*"]  # Wildcard - always matches as fallback
    
    async def extract_title(self) -> Optional[str]:
        # Import here to avoid circular imports
        from ..core.stream_getter import VideoScraper
        scraper = VideoScraper()
        scraper.browser = type(self.page).__name__
        # Use the existing get_page_title logic
        return await self.page.evaluate("""
            () => {
                const h1 = document.querySelector('h1');
                if (h1 && h1.innerText.trim()) {
                    return h1.innerText.trim().split(/\\n/)[0].trim();
                }
                const vt = document.querySelector('.video-title, .entry-title, .title');
                if (vt && vt.innerText.trim()) {
                    return vt.innerText.trim().split(/\\n/)[0].trim();
                }
                const og = document.querySelector('meta[property="og:title"]');
                if (og && og.content) return og.content.trim();
                const title = document.title;
                if (title) return title.split(/[-|–—]/)[0].trim();
                return null;
            }
        """)
    
    async def click_play(self) -> bool:
        """Try common play button selectors."""
        selectors = [
            'button.play', '.video-player button',
            '[class*="play"]', 'video + div',
            '.jw-play-button', '.vjs-play-button'
        ]
        
        for selector in selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    await element.click()
                    return True
            except:
                continue
        return False


class AdapterRegistry:
    """Registry for domain adapters with auto-detection."""
    
    _adapters: List[type] = []
    
    @classmethod
    def register(cls, adapter: type) -> type:
        """Register an adapter class."""
        cls._adapters.append(adapter)
        return adapter
    
    @classmethod
    def get_adapter(cls, url: str, page, interceptor) -> BaseAdapter:
        """Get the appropriate adapter for a URL."""
        # Sort adapters so more specific ones come first
        # (non-wildcard domains first)
        sorted_adapters = sorted(
            cls._adapters,
            key=lambda a: 0 if a.DOMAINS == ["*"] else 1
        )
        
        for adapter in sorted_adapters:
            if adapter.matches(url):
                return adapter(page, interceptor)
        
        return DefaultAdapter(page, interceptor)
    
    @classmethod
    def get_domain(cls, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc.replace("www.", "")


# Register default adapter last
AdapterRegistry.register(DefaultAdapter)

"""
Domain Adapters for CSV Getter - Different selectors for different video sites.
"""

from urllib.parse import urlparse
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    """
    Base class for domain-specific adapters.
    Each adapter defines selectors for a specific video listing site.
    """
    
    # Domain patterns this adapter handles
    DOMAINS: List[str] = []
    
    # CSS selectors for video listing elements
    CONTAINER_SELECTOR: str = ".videos-list article, .video-list .video-item, .posts .post"
    TITLE_SELECTOR: str = "h1, h2, h3, h4, .title, .video-title, a"
    LINK_SELECTOR: str = "a"
    THUMBNAIL_SELECTOR: str = "img"
    DURATION_SELECTOR: str = ".duration, [class*='duration'], [class*='time']"
    VIEWS_SELECTOR: str = ".views, [class*='views'], [class*='count']"
    
    # Pagination selectors
    PAGINATION_SELECTOR: str = ".pagination a, .page-numbers a"
    NEXT_SELECTOR: str = ".pagination .next, .page-numbers .next"
    
    @classmethod
    def matches(cls, url: str) -> bool:
        """Check if this adapter handles the given URL."""
        parsed = urlparse(url)
        return any(domain in parsed.netloc for domain in cls.DOMAINS)
    
    @abstractmethod
    async def extract_page_count(self, page) -> int:
        """Extract total page count from pagination."""
        pass
    
    @abstractmethod
    async def extract_videos(self, page) -> List[Dict]:
        """Extract video items from page."""
        pass


class DefaultAdapter(BaseAdapter):
    """Default adapter for unknown domains."""
    
    DOMAINS = ["*"]
    
    async def extract_page_count(self, page) -> int:
        return await page.evaluate("""
            () => {
                const links = document.querySelectorAll('.pagination a, .page-numbers a');
                let max = 1;
                links.forEach(a => {
                    const match = a.href.match(/\\/page\\/(\\d+)/);
                    if (match) max = Math.max(max, parseInt(match[1]));
                });
                return max;
            }
        """)
    
    async def extract_videos(self, page) -> List[Dict]:
        return await page.evaluate("""
            (selectors) => {
                const results = [];
                const articles = document.querySelectorAll(selectors.container);
                
                articles.forEach((article) => {
                    const titleEl = article.querySelector(selectors.title);
                    const title = titleEl ? titleEl.textContent.trim() : '';
                    
                    const linkEl = article.querySelector(selectors.link);
                    const link = linkEl ? linkEl.href : '';
                    
                    const img = article.querySelector(selectors.thumbnail);
                    const thumbnail = img ? (img.src || img.getAttribute('data-src') || '') : '';
                    
                    const dur = article.querySelector(selectors.duration);
                    const duration = dur ? dur.textContent.trim() : '';
                    
                    const views = article.querySelector(selectors.views);
                    const viewsText = views ? views.textContent.trim() : '';
                    
                    if (title || link) {
                        results.push({ title, link, thumbnail, duration, views: viewsText });
                    }
                });
                
                return results;
            }
        """, {
            "container": self.CONTAINER_SELECTOR,
            "title": self.TITLE_SELECTOR,
            "link": self.LINK_SELECTOR,
            "thumbnail": self.THUMBNAIL_SELECTOR,
            "duration": self.DURATION_SELECTOR,
            "views": self.VIEWS_SELECTOR,
        })


class AdapterRegistry:
    """Registry for domain adapters with auto-detection."""
    
    _adapters: List[type] = []
    
    @classmethod
    def register(cls, adapter: type) -> type:
        """Register an adapter class."""
        cls._adapters.append(adapter)
        return adapter
    
    @classmethod
    def get_adapter(cls, url: str) -> BaseAdapter:
        """Get the appropriate adapter for a URL."""
        sorted_adapters = sorted(
            cls._adapters,
            key=lambda a: 0 if a.DOMAINS == ["*"] else 1
        )
        
        for adapter in sorted_adapters:
            if adapter.matches(url):
                return adapter()
        
        return DefaultAdapter()
    
    @classmethod
    def get_domain(cls, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc.replace("www.", "")


# Auto-load domain adapters
try:
    from . import domains
except ImportError:
    pass


# Register default adapter
AdapterRegistry.register(DefaultAdapter)

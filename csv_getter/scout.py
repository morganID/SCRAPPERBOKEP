"""
CSV Getter Scout - Analyze website and generate adapter code automatically.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from urllib.parse import urlparse

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Data Classes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class SelectorMatch:
    selector: str
    count: int = 0
    visible: int = 0


@dataclass
class AnalysisResult:
    url: str
    domain: str
    containers: List[SelectorMatch] = field(default_factory=list)
    titles: List[SelectorMatch] = field(default_factory=list)
    links: List[SelectorMatch] = field(default_factory=list)
    thumbnails: List[SelectorMatch] = field(default_factory=list)
    durations: List[SelectorMatch] = field(default_factory=list)
    views: List[SelectorMatch] = field(default_factory=list)
    pagination: List[SelectorMatch] = field(default_factory=list)
    error: Optional[str] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Scout
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Scout:
    """Analyze video listing page and generate adapter code."""
    
    # Candidate selectors
    CONTAINER_CANDIDATES = [
        ".videos-list article",
        ".video-list .video-item", 
        ".posts .post",
        ".video-grid .video",
        "[class*='video-list']",
        "[class*='videos'] article",
        ".content .video",
    ]
    
    TITLE_CANDIDATES = [
        "h1", "h2", "h3", "h4",
        ".title", ".video-title", ".entry-title",
        "[class*='title']",
    ]
    
    LINK_CANDIDATES = ["a", "a[href]", ".thumb a", ".video-thumb a"]
    
    THUMBNAIL_CANDIDATES = [
        "img", "img.thumb", ".thumbnail img",
        "[class*='thumb'] img",
    ]
    
    DURATION_CANDIDATES = [
        ".duration", ".time", "[class*='duration']",
        "[class*='time']", ".video-duration",
    ]
    
    VIEWS_CANDIDATES = [
        ".views", "[class*='views']", ".view-count",
        "[class*='view']", ".views-count",
    ]
    
    PAGINATION_CANDIDATES = [
        ".pagination a", ".page-numbers a",
        "[class*='pagination'] a",
        ".paging a",
    ]
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
    
    async def __aenter__(self):
        await self._start()
        return self
    
    async def __aexit__(self, *args):
        await self._close()
    
    async def _start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        self.page = await self.context.new_page()
    
    async def _close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def analyze(self, url: str) -> AnalysisResult:
        """Analyze a video listing page."""
        result = AnalysisResult(url=url, domain=urlparse(url).netloc)
        
        try:
            await self.page.goto(url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            
            # Scroll
            for _ in range(2):
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1)
            
            # Find selectors
            result.containers = await self._find_selectors(self.CONTAINER_CANDIDATES)
            result.titles = await self._find_selectors(self.TITLE_CANDIDATES)
            result.links = await self._find_selectors(self.LINK_CANDIDATES)
            result.thumbnails = await self._find_selectors(self.THUMBNAIL_CANDIDATES)
            result.durations = await self._find_selectors(self.DURATION_CANDIDATES)
            result.views = await self._find_selectors(self.VIEWS_CANDIDATES)
            result.pagination = await self._find_selectors(self.PAGINATION_CANDIDATES)
            
        except Exception as e:
            result.error = str(e)
        
        return result
    
    async def _find_selectors(self, candidates: List[str]) -> List[SelectorMatch]:
        results = []
        for sel in candidates:
            try:
                count = await self.page.evaluate(f"""
                    () => document.querySelectorAll('{sel}').length
                """)
                if count > 0:
                    results.append(SelectorMatch(selector=sel, count=count))
            except:
                continue
        return sorted(results, key=lambda x: x.count, reverse=True)


def generate_adapter_code(result: AnalysisResult) -> str:
    """Generate adapter code from analysis result."""
    domain = result.domain.replace("www.", "")
    domain_snake = re.sub(r"[^a-zA-Z0-9]", "_", domain)
    class_name = "".join(w.capitalize() for w in domain_snake.split("_") if w) + "Adapter"
    
    best_container = result.containers[0].selector if result.containers else ".videos article"
    best_title = result.titles[0].selector if result.titles else ".title"
    best_link = result.links[0].selector if result.links else "a"
    best_thumb = result.thumbnails[0].selector if result.thumbnails else "img"
    best_duration = result.durations[0].selector if result.durations else ".duration"
    best_views = result.views[0].selector if result.views else ".views"
    best_pagination = result.pagination[0].selector if result.pagination else ".pagination a"
    
    return f'''"""Adapter for {domain}.\"\"\"

from .. import BaseAdapter, AdapterRegistry
from typing import List, Dict


@RepositoryRegistry.register
class {class_name}(BaseAdapter):
    """Adapter for {domain}\"\"\"
    
    DOMAINS = ["{domain}", "www.{domain}"]
    
    CONTAINER_SELECTOR = "{best_container}"
    TITLE_SELECTOR = "{best_title}"
    LINK_SELECTOR = "{best_link}"
    THUMBNAIL_SELECTOR = "{best_thumb}"
    DURATION_SELECTOR = "{best_duration}"
    VIEWS_SELECTOR = "{best_views}"
    PAGINATION_SELECTOR = "{best_pagination}"
    
    async def extract_page_count(self, page) -> int:
        return await page.evaluate(\"\"\"
            () => {{
                const links = document.querySelectorAll('{best_pagination}');
                let max = 1;
                links.forEach(a => {{
                    const match = a.href.match(/\\\\/page\\\\/(\\\\d+)/);
                    if (match) max = Math.max(max, parseInt(match[1]));
                }});
                return max;
            }}
        \"\"\")
    
    async def extract_videos(self, page) -> List[Dict]:
        return await page.evaluate(\"\"\"
            (selectors) => {{
                const results = [];
                const articles = document.querySelectorAll(selectors.container);
                
                articles.forEach((article) => {{
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
                    
                    if (title || link) {{
                        results.push({{ title, link, thumbnail, duration, views: viewsText }});
                    }}
                }});
                
                return results;
            }}
        \"\"", {{
            "container": self.CONTAINER_SELECTOR,
            "title": self.TITLE_SELECTOR,
            "link": self.LINK_SELECTOR,
            "thumbnail": self.THUMBNAIL_SELECTOR,
            "duration": self.DURATION_SELECTOR,
            "views": self.VIEWS_SELECTOR,
        }})
'''


def print_report(result: AnalysisResult):
    """Print analysis report."""
    bar = "=" * 50
    
    print(f"\n{bar}")
    print(f"📊 Analysis: {result.domain}")
    print(bar)
    
    if result.error:
        print(f"❌ Error: {result.error}")
        return
    
    print(f"\n📦 Containers ({len(result.containers)}):")
    for s in result.containers[:3]:
        print(f"   {s.selector}: {s.count} items")
    
    print(f"\n📝 Titles ({len(result.titles)}):")
    for s in result.titles[:3]:
        print(f"   {s.selector}: {s.count}")
    
    print(f"\n🖼️ Thumbnails ({len(result.thumbnails)}):")
    for s in result.thumbnails[:3]:
        print(f"   {s.selector}: {s.count}")
    
    print(f"\n⏱️ Durations ({len(result.durations)}):")
    for s in result.durations[:3]:
        print(f"   {s.selector}: {s.count}")
    
    print(f"\n👁️ Views ({len(result.views)}):")
    for s in result.views[:3]:
        print(f"   {s.selector}: {s.count}")
    
    print(f"\n📑 Pagination ({len(result.pagination)}):")
    for s in result.pagination[:3]:
        print(f"   {s.selector}: {s.count}")
    
    print(f"\n{bar}\n")


async def run_scout(url: str, save: bool = True):
    """Run scout and generate adapter."""
    import os
    
    print(f"\n{'=' * 50}")
    print("🎯 CSV GETTER SCOUT")
    print(f"{'=' * 50}")
    
    async with Scout() as scout:
        result = await scout.analyze(url)
    
    print_report(result)
    
    if result.error:
        return result
    
    code = generate_adapter_code(result)
    domain_file = re.sub(r"[^a-zA-Z0-9]", "_", result.domain.replace("www.", ""))
    
    print(f"{'=' * 50}")
    print("📄 Generated Adapter Code:")
    print(f"{'=' * 50}\n")
    print(code)
    
    if save:
        output_path = f"csv_getter/adapters/domains/{domain_file}.py"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(code)
        print(f"\n✅ Saved to: {output_path}")
    
    return result

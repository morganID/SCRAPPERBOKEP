"""
Adapter Scout - Analyze website and generate adapter code automatically.
"""

import asyncio
import logging
from urllib.parse import urlparse
from typing import Optional, Dict, List

from playwright.async_api import async_playwright

import config

logger = logging.getLogger(__name__)


class AdapterScout:
    """
    Analyze a video website and suggest selectors for adapter.
    
    Usage:
        scout = AdapterScout()
        analysis = await scout.analyze("https://example.com/video")
        print(analysis)
    """
    
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, *args):
        await self.close()
    
    async def start(self):
        """Start browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=config.BROWSER_ARGS,
        )
        self.context = await self.browser.new_context(
            viewport=config.VIEWPORT,
            user_agent=config.USER_AGENT,
        )
        self.page = await self.context.new_page()
        # Set longer timeout
        self.page.set_default_timeout(60000)
    
    async def close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def analyze(self, url: str) -> Dict:
        """
        Analyze a URL and return suggested selectors.
        
        Returns:
            Dict with analysis results
        """
        print(f"\n🔍 Analyzing: {url}")
        
        # Navigate
        print("   Loading page...")
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"   ⚠️ Page load issue: {e}")
            print("   Trying with networkidle...")
            try:
                await self.page.goto(url, wait_until="load", timeout=60000)
            except Exception as e2:
                print(f"   ❌ Failed to load: {e2}")
                return {"error": str(e2)}
        
        await asyncio.sleep(2)
        
        analysis = {
            "url": url,
            "domain": urlparse(url).netloc,
            "title_selectors": await self._find_title_selectors(),
            "play_selectors": await self._find_play_selectors(),
            "video_selectors": await self._find_video_selectors(),
            "ad_selectors": await self._find_ad_selectors(),
            "page_title": await self.page.title(),
        }
        
        return analysis
    
    async def _find_title_selectors(self) -> List[Dict]:
        """Find potential title elements."""
        selectors = [
            "h1", "h2", 
            ".title", ".video-title", ".entry-title",
            "[class*='title']",
            "meta[property='og:title']",
            "meta[name='title']"
        ]
        
        results = []
        for sel in selectors:
            try:
                el = await self.page.query_selector(sel)
                if el:
                    text = await el.inner_text() if sel != "meta[property='og:title']" else (await el.get_attribute("content"))
                    if text:
                        results.append({
                            "selector": sel,
                            "value": text[:50] if text else None,
                            "confidence": self._get_confidence(sel, "title")
                        })
            except:
                continue
        
        return sorted(results, key=lambda x: x["confidence"], reverse=True)
    
    async def _find_play_selectors(self) -> List[Dict]:
        """Find potential play button elements."""
        selectors = [
            "button.play",
            ".play-button",
            "#playbutton",
            ".btn-play",
            "[class*='play']",
            "video + *",
            ".video-player button",
            ".jw-play-button",
            ".vjs-play-button"
        ]
        
        results = []
        for sel in selectors:
            try:
                el = await self.page.query_selector(sel)
                if el:
                    tag = await el.evaluate("e => e.tagName")
                    results.append({
                        "selector": sel,
                        "tag": tag,
                        "confidence": self._get_confidence(sel, "play")
                    })
            except:
                continue
        
        return sorted(results, key=lambda x: x["confidence"], reverse=True)
    
    async def _find_video_selectors(self) -> List[Dict]:
        """Find video elements."""
        selectors = ["video", "iframe"]
        
        results = []
        for sel in selectors:
            try:
                elements = await self.page.query_selector_all(sel)
                for el in elements:
                    src = await el.get_attribute("src")
                    results.append({
                        "selector": sel,
                        "src": src[:50] if src else None,
                        "tag": sel
                    })
            except:
                continue
        
        return results
    
    async def _find_ad_selectors(self) -> List[Dict]:
        """Find potential ad/popup elements."""
        selectors = [
            ".ads", ".ad", ".advertisement",
            ".popup", ".modal", ".overlay",
            "[class*='ads']", "[class*='popup']",
            ".close", "[class*='close']"
        ]
        
        results = []
        for sel in selectors:
            try:
                elements = await self.page.query_selector_all(sel)
                if elements:
                    count = len(elements)
                    results.append({
                        "selector": sel,
                        "count": count,
                        "visible": await self._count_visible(sel)
                    })
            except:
                continue
        
        return results
    
    async def _count_visible(self, selector: str) -> int:
        """Count visible elements."""
        try:
            return await self.page.evaluate(f"""
                () => {{
                    return document.querySelectorAll('{selector}').filter(e => {{
                        return e.offsetParent !== null;
                    }}).length;
                }}
            """)
        except:
            return 0
    
    def _get_confidence(self, selector: str, type: str) -> int:
        """Get confidence score for selector."""
        scores = {
            "title": {
                "h1": 10,
                "meta[property='og:title']": 8,
                ".video-title": 7,
                ".title": 5,
            },
            "play": {
                ".jw-play-button": 10,
                ".vjs-play-button": 10,
                "button.play": 8,
                "#playbutton": 8,
                ".play-button": 6,
            }
        }
        return scores.get(type, {}).get(selector, 1)


async def run_scout(url: str):
    """Run the adapter scout interactively."""
    print(f"\n{'='*50}")
    print("🎯 ADAPTER SCOUT - Auto Generate Domain Adapter")
    print(f"{'='*50}")
    
    async with AdapterScout() as scout:
        analysis = await scout.analyze(url)
        
        # Display results
        print(f"\n📊 Analysis Results for {analysis['domain']}")
        print(f"   Page Title: {analysis['page_title'][:50]}...")
        
        print(f"\n📝 Title Selectors:")
        for item in analysis["title_selectors"][:3]:
            print(f"   - {item['selector']}: {item['value']}")
        
        print(f"\n▶️ Play Button Selectors:")
        for item in analysis["play_selectors"][:3]:
            print(f"   - {item['selector']} ({item.get('tag', 'N/A')})")
        
        print(f"\n🎬 Video Elements:")
        for item in analysis["video_selectors"][:3]:
            print(f"   - {item['selector']}: {item['src']}")
        
        print(f"\n🚫 Ad/Popup Elements:")
        for item in analysis["ad_selectors"][:5]:
            print(f"   - {item['selector']}: {item.get('count', 0)} found, {item.get('visible', 0)} visible")
        
        # Generate adapter code
        print(f"\n{'='*50}")
        print("📄 Generated Adapter Code:")
        print(f"{'='*50}\n")
        
        domain_name = analysis["domain"].replace("www.", "").replace(".", "_")
        
        best_title = analysis["title_selectors"][0]["selector"] if analysis["title_selectors"] else "h1"
        best_play = analysis["play_selectors"][0]["selector"] if analysis["play_selectors"] else ".play-button"
        
        ad_selectors = [item["selector"] for item in analysis["ad_selectors"][:3]]
        
        code = f'''"""
Adapter for {analysis['domain']}
Auto-generated by AdapterScout
"""

from .. import BaseAdapter, AdapterRegistry
from typing import Optional


@RepositoryRegistry.register
class {domain_name.title().replace("_", "")}Adapter(BaseAdapter):
    """Adapter for {analysis['domain']}"""
    
    DOMAINS = ["{analysis['domain']}", "www.{analysis['domain']}"]
    
    async def extract_title(self) -> Optional[str]:
        return await self.page.evaluate("""
            () => {{
                const el = document.querySelector('{best_title}');
                return el ? el.innerText.trim().split(/\\\\n/)[0] : null;
            }}
        """)
    
    async def click_play(self) -> bool:
        try:
            await self.page.click('{best_play}')
            return True
        except:
            return False
    
    async def before_scrape(self) -> None:
        # Wait for page to stabilize
        await self.page.wait_for_timeout(1000)
'''
        
        print(code)
        
        print(f"{'='*50}")
        print(f"💾 Save as: stream_getter/adapters/domains/{domain_name}.py")
        print(f"{'='*50}")
        
        return analysis

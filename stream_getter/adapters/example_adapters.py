"""
Example domain adapters - customize per site.

Copy and modify these for your target sites.
"""

from . import BaseAdapter, AdapterRegistry
from typing import Optional


@AdapterRegistry.register
class Site1Adapter(BaseAdapter):
    """Adapter for site1.com"""
    
    DOMAINS = ["site1.com", "www.site1.com"]
    
    async def extract_title(self) -> Optional[str]:
        # Custom title extraction for this site
        return await self.page.evaluate("""
            () => {
                // Site1 uses a specific class for title
                const titleEl = document.querySelector('.video-title h1');
                return titleEl ? titleEl.innerText.trim() : null;
            }
        """)
    
    async def click_play(self) -> bool:
        # Custom play button for this site
        try:
            await self.page.click('#play-button')
            return True
        except:
            return False
    
    async def before_scrape(self) -> None:
        # Site1 needs extra wait time
        await self.page.wait_for_timeout(2000)
    
    def get_referer(self) -> str:
        return "https://site1.com/"


@AdapterRegistry.register
class Site2Adapter(BaseAdapter):
    """Adapter for site2.net"""
    
    DOMAINS = ["site2.net"]
    
    async def extract_title(self) -> Optional[str]:
        # Site2 puts title in og:title
        return await self.page.evaluate("""
            () => {
                const og = document.querySelector('meta[property="og:title"]');
                return og ? og.content : document.title;
            }
        """)
    
    async def click_play(self) -> bool:
        # Site2 uses a different player
        try:
            await self.page.click('.player-container .play')
            return True
        except:
            return False
    
    async def after_scrape(self, m3u8_urls):
        # Filter out low quality streams for this site
        return [url for url in m3u8_urls if "360" not in url]


@AdapterRegistry.register  
class IndoVideoAdapter(BaseAdapter):
    """Adapter for Indonesian video sites"""
    
    DOMAINS = [
        "indovidz.com",
        "bokepindo.net", 
        "sjavhd.com",
        "lendir.xyz"
    ]
    
    async def extract_title(self) -> Optional[str]:
        return await self.page.evaluate("""
            () => {
                // Try h1 first
                const h1 = document.querySelector('h1');
                if (h1) {
                    const text = h1.innerText.trim().split(/\\n/)[0];
                    // Clean up Indonesian video site patterns
                    return text.replace(/\\d{1,2}:\\d{2}\\s*/, '').trim();
                }
                return document.title.split('|')[0].trim();
            }
        """)
    
    async def click_play(self) -> bool:
        # Common Indonesian sites often use these selectors
        selectors = [
            '#playbutton',
            '.btn-play',
            'button[onclick*="play"]',
            '.video-wrapper button'
        ]
        
        for sel in selectors:
            try:
                el = await self.page.query_selector(sel)
                if el:
                    await el.click()
                    return True
            except:
                continue
        return False

"""
Adapter for indovidz.com and similar Indonesian video sites.
"""

from .. import BaseAdapter, AdapterRegistry
from typing import Optional


@AdapterRegistry.register
class IndovidzAdapter(BaseAdapter):
    """Adapter for indovidz.com"""
    
    DOMAINS = ["indovidz.com", "www.indovidz.com"]
    
    async def extract_title(self) -> Optional[str]:
        return await self.page.evaluate("""
            () => {
                const h1 = document.querySelector('h1');
                if (h1) {
                    const text = h1.innerText.trim().split(/\\n/)[0];
                    return text.replace(/\\d{1,2}:\\d{2}\\s*/, '').trim();
                }
                return document.title.split('|')[0].trim();
            }
        """)
    
    async def click_play(self) -> bool:
        selectors = [
            '#playbutton',
            '.btn-play', 
            'button[onclick*="play"]',
            '.video-wrapper button',
            '#player button'
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

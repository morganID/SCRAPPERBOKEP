"""
CSV Getter - Scrape video listings from pagination pages to CSV.
"""

import csv
import asyncio
import logging
from typing import List, Dict, Optional
from pathlib import Path

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


# Default browser args
BROWSER_ARGS = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-blink-features=AutomationControlled',
    '--disable-web-security',
]

DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

DEFAULT_CONCURRENT = 5


class CSVGetter:
    """
    Scrape video listings from paginated websites to CSV.
    
    Usage:
        getter = CSVGetter()
        await getter.scrape("https://example.com/videos", output="hasil.csv")
    """
    
    def __init__(
        self,
        concurrent: int = DEFAULT_CONCURRENT,
        user_agent: str = DEFAULT_USER_AGENT,
        output: str = "hasil.csv",
    ):
        self.concurrent = concurrent
        self.user_agent = user_agent
        self.output = output
        self.browser = None
        self.context = None
    
    async def __aenter__(self):
        await self._start()
        return self
    
    async def __aexit__(self, *args):
        await self._close()
    
    async def _start(self):
        """Start browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=BROWSER_ARGS,
        )
        self.context = await self.browser.new_context(
            user_agent=self.user_agent,
            viewport={'width': 1920, 'height': 1080},
        )
    
    async def _close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def scrape_page(self, base_url: str, page_num: int) -> List[Dict]:
        """Scrape single page."""
        try:
            page = await self.context.new_page()
            
            # Set stealth
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
            
            # Build URL
            if page_num == 1:
                url = f"{base_url.rstrip('/')}/"
            else:
                url = f"{base_url.rstrip('/')}/page/{page_num}/"
            
            response = await page.goto(url, wait_until="networkidle", timeout=60000)
            
            if response and response.status >= 400:
                await page.close()
                return []
            
            # Scroll to load more content
            prev_height = 0
            for _ in range(3):
                curr_height = await page.evaluate("document.body.scrollHeight")
                if curr_height == prev_height:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(800)
                prev_height = curr_height
            
            # Extract data
            data = await page.evaluate("""
                () => {
                    const results = [];
                    const articles = document.querySelectorAll('.videos-list article, .video-list .video-item, .posts .post, [class*="video"]');
                    
                    articles.forEach((article) => {
                        // Title
                        const titleEl = article.querySelector('h1, h2, h3, h4, .title, .video-title, a');
                        const title = titleEl ? titleEl.textContent.trim() : '';
                        
                        // Link
                        const linkEl = article.querySelector('a');
                        const link = linkEl ? linkEl.href : '';
                        
                        // Thumbnail
                        const img = article.querySelector('img');
                        const thumbnail = img ? (img.src || img.getAttribute('data-src') || '') : '';
                        
                        // Duration
                        const dur = article.querySelector('.duration, [class*="duration"], [class*="time"]');
                        const duration = dur ? dur.textContent.trim() : '';
                        
                        // Views
                        const views = article.querySelector('.views, [class*="views"], [class*="count"]');
                        const viewsText = views ? views.textContent.trim() : '';
                        
                        if (title || link) {
                            results.push({ title, link, thumbnail, duration, views: viewsText });
                        }
                    });
                    
                    return results;
                }
            """)
            
            await page.close()
            
            for item in data:
                item['page'] = page_num
            
            logger.info(f"✅ Page {page_num}: {len(data)} videos")
            return data
            
        except Exception as e:
            logger.warning(f"❌ Page {page_num}: {str(e)[:80]}")
            return []
    
    async def get_total_pages(self, base_url: str) -> int:
        """Detect total pages from pagination."""
        page = await self.context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        
        await page.goto(base_url, wait_until="networkidle", timeout=60000)
        
        total_pages = await page.evaluate("""
            () => {
                const links = document.querySelectorAll('.pagination a, .page-numbers a, [class*="pagination"] a');
                let max = 1;
                links.forEach(a => {
                    const match = a.href.match(/\\/page\\/(\\d+)/);
                    if (match) max = Math.max(max, parseInt(match[1]));
                });
                
                // Also check last page link
                const lastLink = document.querySelector('.pagination .last, .page-numbers .last, [class*="pagination"] .last');
                if (lastLink) {
                    const match = lastLink.href.match(/\\/page\\/(\\d+)/);
                    if (match) max = Math.max(max, parseInt(match[1]));
                }
                
                return max;
            }
        """)
        
        await page.close()
        return total_pages
    
    async def scrape(self, base_url: str) -> List[Dict]:
        """
        Scrape all pages from base_url.
        
        Args:
            base_url: The main page URL (without /page/x)
            
        Returns:
            List of video data dicts
        """
        base_url = base_url.rstrip('/')
        all_data = []
        
        # Get total pages
        total_pages = await self.get_total_pages(base_url)
        logger.info(f"📊 Total: {total_pages} pages")
        logger.info(f"🚀 Concurrent: {self.concurrent} connections\n")
        
        # Process in batches
        for batch_start in range(1, total_pages + 1, self.concurrent):
            batch_end = min(batch_start + self.concurrent, total_pages + 1)
            batch_pages = list(range(batch_start, batch_end))
            
            logger.info(f"📦 Batch: Page {batch_start}-{batch_end - 1}")
            
            # Run concurrent
            tasks = [self.scrape_page(base_url, pg) for pg in batch_pages]
            results = await asyncio.gather(*tasks)
            
            for data in results:
                all_data.extend(data)
            
            # Save progress
            if all_data:
                await self._save_progress(all_data)
            
            # Delay between batches
            await asyncio.sleep(2)
        
        # Final save
        all_data.sort(key=lambda x: x.get('page', 1))
        await self._save_final(all_data)
        
        logger.info(f"\n{'='*50}")
        logger.info(f"🎉 TOTAL: {len(all_data)} videos from {total_pages} pages")
        logger.info(f"💾 Saved to: {self.output}")
        logger.info(f"{'='*50}")
        
        return all_data
    
    async def _save_progress(self, data: List[Dict]):
        """Save progress to temp file."""
        temp_data = data.copy()
        for i, item in enumerate(temp_data, 1):
            item['no'] = i
        
        fieldnames = ['no', 'page', 'title', 'link', 'thumbnail', 'duration', 'views']
        
        # Use temp file for progress
        temp_output = Path(self.output).stem + "_temp.csv"
        
        with open(temp_output, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            w.writeheader()
            w.writerows(temp_data)
    
    async def _save_final(self, data: List[Dict]):
        """Save final CSV."""
        for i, item in enumerate(data, 1):
            item['no'] = i
        
        fieldnames = ['no', 'page', 'title', 'link', 'thumbnail', 'duration', 'views']
        
        with open(self.output, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            w.writeheader()
            w.writerows(data)
        
        # Remove temp file
        temp_output = Path(self.output).stem + "_temp.csv"
        try:
            Path(temp_output).unlink()
        except:
            pass


async def run(base_url: str, output: str = "hasil.csv", concurrent: int = 5):
    """CLI entry point."""
    async with CSVGetter(concurrent=concurrent, output=output) as getter:
        await getter.scrape(base_url)

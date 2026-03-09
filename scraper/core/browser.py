"""
Browser management for the video scraper.
"""

import asyncio
import logging
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

import config
from ..utils.exceptions import BrowserError

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Manages browser lifecycle and configuration for video scraping.
    
    Provides a clean interface for browser initialization, context creation,
    and cleanup with stealth mode enabled.
    """
    
    def __init__(self) -> None:
        """Initialize the browser manager."""
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
    
    @property
    def page(self) -> Optional[Page]:
        """Get the current page instance."""
        return self._page
    
    @property
    def context(self) -> Optional[BrowserContext]:
        """Get the current browser context."""
        return self._context
    
    @property
    def browser(self) -> Optional[Browser]:
        """Get the browser instance."""
        return self._browser
    
    async def start(self) -> None:
        """
        Start the browser with stealth mode enabled.
        
        Raises:
            BrowserError: If browser fails to start.
        """
        try:
            self._playwright = await async_playwright().start()
            
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=config.BROWSER_ARGS,
            )
            
            self._context = await self._browser.new_context(
                viewport=config.VIEWPORT,
                user_agent=config.USER_AGENT,
                bypass_csp=True,
                ignore_https_errors=True,
            )
            
            # Add stealth scripts
            await self._context.add_init_script(config.STEALTH_SCRIPT)
            
            self._page = await self._context.new_page()
            
            logger.info("Browser started successfully")
            
        except Exception as e:
            await self.close()
            raise BrowserError(f"Failed to start browser: {e}") from e
    
    async def close(self) -> None:
        """
        Close all browser resources properly.
        """
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.debug(f"Browser close error: {e}")
        
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug(f"Playwright stop error: {e}")
        
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        
        logger.info("Browser closed")
    
    async def navigate(self, url: str, wait_until: str = "commit") -> None:
        """
        Navigate to a URL.
        
        Args:
            url: The URL to navigate to.
            wait_until: Wait strategy (commit, domcontentloaded, networkidle, load).
            
        Raises:
            BrowserError: If navigation fails.
        """
        if not self._page:
            raise BrowserError("Browser not started. Call start() first.")
        
        try:
            await self._page.goto(
                url,
                wait_until=wait_until,
                timeout=config.PAGE_TIMEOUT,
            )
            logger.debug(f"Navigated to: {url}")
        except Exception as e:
            logger.warning(f"Page load issue (continuing): {e}")
    
    async def wait(self, seconds: float) -> None:
        """
        Wait for a specified number of seconds.
        
        Args:
            seconds: Number of seconds to wait.
        """
        await asyncio.sleep(seconds)
    
    async def close_popups(self) -> int:
        """
        Close all popup pages except the main page.
        
        Returns:
            Number of popups closed.
        """
        if not self._context:
            return 0
        
        closed = 0
        for page in self._context.pages:
            if page != self._page:
                try:
                    await page.close()
                    closed += 1
                except Exception:
                    pass
        
        if closed > 0:
            logger.debug(f"Closed {closed} popup(s)")
        
        return closed
    
    async def evaluate(self, script: str):
        """
        Evaluate JavaScript in the page context.
        
        Args:
            script: JavaScript code to execute.
            
        Returns:
            Result of the script evaluation.
        """
        if not self._page:
            raise BrowserError("Browser not started")
        
        return await self._page.evaluate(script)
    
    async def screenshot(self, path: str) -> None:
        """
        Take a screenshot of the current page.
        
        Args:
            path: Path to save the screenshot.
        """
        if not self._page:
            raise BrowserError("Browser not started")
        
        await self._page.screenshot(path=path)
        logger.debug(f"Screenshot saved: {path}")

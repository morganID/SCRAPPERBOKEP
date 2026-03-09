# csv_getter/debug.py
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from playwright.async_api import async_playwright


async def main():
    # URL tanpa www
    url = "https://jable.tv/"
    
    print(f"\n🔍 Testing: {url}")
    print("=" * 50)
    
    playwright = None
    browser = None
    
    try:
        playwright = await async_playwright().start()
        
        print("🚀 Starting browser...")
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox"],
        )
        
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )
        
        page = await context.new_page()
        
        print(f"📡 Loading {url}...")
        
        response = await page.goto(url, timeout=60000)
        
        if response:
            print(f"✅ Status: {response.status}")
        
        title = await page.title()
        print(f"✅ Title: {title}")
        
        # Tunggu user explore
        print("\n" + "=" * 50)
        print("✅ Browser terbuka!")
        print("   - Inspect elements")  
        print("   - Scroll halaman")
        print("   - Lihat struktur HTML")
        print("=" * 50)
        
        input("\n⏸️  Tekan ENTER untuk close browser...")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        input("\nTekan ENTER untuk close...")
        
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
        print("✅ Done")


if __name__ == "__main__":
    asyncio.run(main())
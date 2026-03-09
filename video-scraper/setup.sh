#!/bin/bash
echo "================================"
echo "  VIDEO SCRAPER - SETUP"
echo "================================"

# Install Python dependencies
echo "[1/4] Installing Python packages..."
pip install -r requirements.txt -q

# Install Playwright browsers
echo "[2/4] Installing Chromium..."
playwright install chromium
playwright install-deps

# Install ffmpeg
echo "[3/4] Installing ffmpeg..."
apt-get update -qq && apt-get install -y -qq ffmpeg

# Verify
echo "[4/4] Verifying..."
python -c "from playwright.async_api import async_playwright; print('  ✅ Playwright OK')"
ffmpeg -version 2>/dev/null | head -1 && echo "  ✅ ffmpeg OK"

echo ""
echo "================================"
echo "  SETUP COMPLETE!"
echo "================================"
echo ""
echo "Usage:"
echo "  python main.py --url \"https://target-site.com/video\""
echo "  python main.py --url \"URL\" --output video.mp4"
echo "  python main.py --direct \"https://xxx/index.m3u8\""
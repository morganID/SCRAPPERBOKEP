"""
utils.py - Helper functions
"""

import re


def sanitize_filename(name):
    """Bersihkan nama file dari karakter ilegal"""
    if not name:
        return "video"
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = name.strip('.')
    name = name[:100]
    return name if name else "video"


async def get_page_title(page):
    """Ambil judul dari halaman browser"""
    try:
        return await page.evaluate("""
            () => {
                const h1 = document.querySelector('h1');
                if (h1 && h1.innerText.trim()) return h1.innerText.trim();

                const vt = document.querySelector('.video-title, .entry-title, .title');
                if (vt && vt.innerText.trim()) return vt.innerText.trim();

                const og = document.querySelector('meta[property="og:title"]');
                if (og && og.content) return og.content.trim();

                const t = document.title;
                if (t) return t.split(/[-|–—]/)[0].trim();

                return null;
            }
        """)
    except Exception:
        return None
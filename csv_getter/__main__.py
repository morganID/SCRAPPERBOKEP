"""
CSV Getter CLI — python -m csv_getter

Usage:
    python -m csv_getter --scout "https://example.com/"
    python -m csv_getter "https://example.com/"
    python -m csv_getter "https://example.com/" -c 10 --max-pages 20
    python -m csv_getter --list
"""

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog="python -m csv_getter",
        description="CSV Getter — Scrape video listings to CSV/{domain}.csv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python -m csv_getter --scout "https://dicrotin.com/"
  python -m csv_getter "https://dicrotin.com/"
  python -m csv_getter "https://dicrotin.com/" -c 10 --max-pages 20
  python -m csv_getter --list
        """,
    )

    parser.add_argument("url", nargs="?", help="Target URL")
    parser.add_argument("--scout", action="store_true", help="Analyze only, save adapter")
    parser.add_argument("--force-scout", action="store_true", help="Re-analyze then scrape")
    parser.add_argument("--list", action="store_true", help="List saved adapters")
    parser.add_argument("-c", "--concurrent", type=int, default=10, help="Concurrent (default: 5)")
    parser.add_argument("--max-pages", type=int, default=0, help="Max pages, 0=all")
    parser.add_argument("--no-headless", action="store_true", help="Show browser")
    parser.add_argument("--proxy", type=str, default=None, help="Proxy server")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    if args.list:
        list_adapters()
        return

    if not args.url:
        parser.print_help()
        print('\n❌ URL required')
        print('   python -m csv_getter --scout "https://example.com/"')
        sys.exit(1)

    headless = not args.no_headless

    if args.scout:
        asyncio.run(scout_only(args.url, headless, args.proxy))
    else:
        asyncio.run(full_run(
            args.url, args.concurrent, args.max_pages,
            headless, args.proxy, args.force_scout,
        ))


async def scout_only(url, headless=True, proxy=None):
    from .scout import run_scout                       # ← scout.py

    result = await run_scout(url=url, save=True, headless=headless, proxy=proxy)

    if result.error:
        print(f"\n❌ Failed: {result.error}")
        sys.exit(1)
    if not result.is_valid:
        print("\n⚠️  No valid selectors found")
        sys.exit(1)

    print("\n✅ Adapter saved! Now scrape:")
    print(f'   python -m csv_getter "{url}"')


async def full_run(url, concurrent=7, max_pages=0,
                   headless=True, proxy=None, force_scout=False):
    from .scraper import run                           # ← scraper.py

    data = await run(
        url=url,
        concurrent=concurrent,
        max_pages=max_pages,
        headless=headless,
        proxy=proxy,
        force_scout=force_scout,
    )

    if not data:
        print("\n⚠️  No data scraped")
        sys.exit(1)


def list_adapters():
    adapters_dir = Path("csv_getter/adapters/domains")
    csv_dir = Path("CSV")

    print(f"\n{'=' * 55}")
    print("📂  Saved Adapters")
    print(f"{'=' * 55}")

    if not adapters_dir.exists():
        print("   (none)")
        print(f"{'=' * 55}\n")
        return

    files = sorted(f for f in adapters_dir.glob("*.py") if f.name != "__init__.py")
    if not files:
        print("   (none)")
        print(f"{'=' * 55}\n")
        return

    for i, f in enumerate(files, 1):
        domain = f.stem.replace("_", ".")
        csv_file = csv_dir / f"{f.stem}.csv"
        pag = "?"
        try:
            m = re.search(r'PAGINATION_TYPE\s*=\s*["\'](.+?)["\']', f.read_text())
            if m: pag = m.group(1)
        except: pass
        csv_info = f"📄 {csv_file}" if csv_file.exists() else "(no CSV)"
        print(f"   {i}. {domain:<28s} [{pag}]  {csv_info}")

    print(f"\n   Total: {len(files)} adapters")
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    main()
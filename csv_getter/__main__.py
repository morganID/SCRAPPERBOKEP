"""
Entry point for csv_getter CLI.
"""

import argparse
import asyncio
from .scraper import run as run_scraper
from .scout import run_scout


def main():
    parser = argparse.ArgumentParser(description="CSV Getter - Scrape video listings to CSV")
    parser.add_argument("url", nargs="?", help="Base URL of video site")
    parser.add_argument("-o", "--output", default="hasil.csv", help="Output CSV file")
    parser.add_argument("-c", "--concurrent", type=int, default=5, help="Concurrent connections")
    parser.add_argument("--scout", action="store_true", help="Analyze page and generate adapter")
    
    args = parser.parse_args()
    
    if args.scout:
        if not args.url:
            print("Error: --scout requires a URL")
            return
        asyncio.run(run_scout(args.url))
    else:
        if not args.url:
            parser.print_help()
            return
        asyncio.run(run_scraper(args.url, args.output, args.concurrent))


if __name__ == "__main__":
    main()

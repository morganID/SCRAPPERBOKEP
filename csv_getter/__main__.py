"""
Entry point for csv_getter CLI.
"""

import argparse
import asyncio
from .scraper import run


def main():
    parser = argparse.ArgumentParser(description="CSV Getter - Scrape video listings to CSV")
    parser.add_argument("url", help="Base URL of video site")
    parser.add_argument("-o", "--output", default="hasil.csv", help="Output CSV file")
    parser.add_argument("-c", "--concurrent", type=int, default=5, help="Concurrent connections")
    
    args = parser.parse_args()
    asyncio.run(run(args.url, args.output, args.concurrent))


if __name__ == "__main__":
    main()

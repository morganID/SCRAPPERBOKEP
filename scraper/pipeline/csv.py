"""
CSV processing pipeline for batch video scraping from CSV files.
"""

import asyncio
import logging
import os
from typing import List, Dict, Any, Optional

import config
from .downloader import download_video, pick_best_url
from .uploader import upload_to_streamtape
from .csv_helper import (
    read_csv, save_csv, detect_url_column,
    ensure_columns, get_pending_rows, print_summary,
)
from ..core.scraper import VideoScraper
from ..utils.helpers import sanitize_filename, unique_output

logger = logging.getLogger(__name__)


class CSVPipeline:
    """
    Pipeline for processing videos from CSV files.
    
    Reads URLs from CSV, scrapes each one, and updates the CSV with results.
    """
    
    def __init__(
        self,
        csv_file: str,
        url_column: str = 'url',
        output_dir: str = ".",
        referer: Optional[str] = None,
        upload: bool = False,
    ) -> None:
        """
        Initialize the CSV pipeline.
        
        Args:
            csv_file: Path to the CSV file.
            url_column: Name of the URL column.
            output_dir: Directory to save downloaded videos.
            referer: HTTP referer to use.
            upload: Whether to upload videos after download.
        """
        self.csv_file = csv_file
        self.url_column = url_column
        self.output_dir = output_dir
        self.referer = referer or config.DEFAULT_REFERER
        self.upload = upload
        
        # Get concurrency limits from config
        self.max_dl = getattr(config, 'MAX_CONCURRENT_DOWNLOADS', 3)
        self.max_up = getattr(config, 'MAX_CONCURRENT_UPLOADS', 2)
        
        self.sem_dl = asyncio.Semaphore(self.max_dl)
        self.sem_up = asyncio.Semaphore(self.max_up)
        self.csv_lock = asyncio.Lock()
        
        # Track active tasks for concurrent display
        self._active_dl = 0
        self._active_up = 0
        self._dl_lock = asyncio.Lock()
        self._up_lock = asyncio.Lock()
    
    def _truncate(self, text: str, length: int = 30) -> str:
        """Truncate text to specified length."""
        return text[:length] + '...' if len(text) > length else text
    
    def _get_status(self) -> str:
        """Get concurrent status string."""
        return f"⚡DL{self._active_dl}/{self.max_dl}|UP{self._active_up}/{self.max_up}"
    
    async def run(self) -> List[Dict[str, Any]]:
        """
        Run the CSV pipeline.
        
        Returns:
            Updated list of CSV rows.
        """
        if not os.path.exists(self.csv_file):
            logger.error(f"File not found: {self.csv_file}")
            print(f"❌ File not found: {self.csv_file}")
            return []
        
        fieldnames, rows = read_csv(self.csv_file)
        if not fieldnames:
            logger.error("CSV is empty or invalid!")
            print("❌ CSV is empty or invalid!")
            return []
        
        print(f"📄 CSV: {self.csv_file}")
        print(f"   Columns: {fieldnames}")
        print(f"   Rows: {len(rows)}")
        
        # Detect URL column
        detected = detect_url_column(fieldnames, preferred=self.url_column)
        if not detected:
            logger.error(f"URL column '{self.url_column}' not found! Available: {fieldnames}")
            print(f"\n❌ URL column not found!")
            print(f"   Looking for: '{self.url_column}'")
            print(f"   Available: {fieldnames}")
            print(f"   Use --csv-column COLUMN_NAME")
            return []
        self.url_column = detected
        print(f"   URL Column: '{self.url_column}'")
        
        # Ensure required columns exist
        added = ensure_columns(fieldnames)
        if added:
            logger.debug(f"New columns: {added}")
            print(f"   ➕ New columns: {added}")
        
        # Get pending rows
        to_process = get_pending_rows(rows, url_column=self.url_column)
        skipped = len(rows) - len(to_process)
        
        if skipped > 0:
            print(f"   ⏭️  Skip {skipped} rows (already have streamtape)")
        
        if not to_process:
            print("\n✅ All rows already have streamtape links!")
            return rows
        
        print(f"   🎯 Will process: {len(to_process)} videos")
        
        os.makedirs(self.output_dir, exist_ok=True)
        
        print(f"   ⚡ Concurrent: download(×{self.max_dl}), upload(×{self.max_up})")
        logger.info(f"CSV: {len(to_process)} videos, dl×{self.max_dl}, up×{self.max_up}")
        
        scraper = VideoScraper()
        tasks: List[asyncio.Task] = []
        
        try:
            await scraper.start_browser()
            
            for seq, idx in enumerate(to_process, 1):
                row = rows[idx]
                url = row[self.url_column].strip()
                
                self._print_header(seq, len(to_process), idx, url)
                
                logger.info(f"[{seq}/{len(to_process)}] Scraping row #{idx + 2}")
                scraper.reset()
                
                try:
                    m3u8_urls = await scraper.scrape(url)
                    
                    if not m3u8_urls:
                        logger.warning(f"[{seq}] M3U8 not found")
                        print("❌ M3U8 not found")
                        row['status'] = 'NO_M3U8'
                        save_csv(self.csv_file, fieldnames, rows)
                        await asyncio.sleep(2)
                        continue
                    
                    best = pick_best_url(m3u8_urls)
                    title = await scraper.get_page_title()
                    title = sanitize_filename(title) or f"video_{idx + 1}"
                    row['title'] = row.get('title', '').strip() or title
                    output = unique_output(
                        os.path.join(self.output_dir, f"{sanitize_filename(row['title'])}.mp4")
                    )
                    
                    print(f"📝 Title: {row['title']}")
                    print(f"🏆 Best: {best}")
                    logger.debug(f"[{seq}] M3U8: {best}")
                    logger.debug(f"[{seq}] Output: {output}")
                    
                    job = {
                        'url': url,
                        'title': row['title'],
                        'm3u8': best,
                        'output': output,
                        'status': 'QUEUED',
                        'streamtape': '',
                    }
                    
                    task = asyncio.create_task(
                        self._process_and_save(job, idx, fieldnames, rows)
                    )
                    tasks.append(task)
                    
                except Exception as e:
                    logger.error(f"[{seq}] Error: {e}", exc_info=True)
                    print(f"❌ Error: {e}")
                    row['status'] = f'ERROR: {str(e)[:80]}'
                    save_csv(self.csv_file, fieldnames, rows)
                
                await asyncio.sleep(3)
                
        finally:
            await scraper.close()
        
        if tasks:
            print(f"\n⏳ Waiting for {len(tasks)} download/upload to complete...")
            await asyncio.gather(*tasks)
        
        save_csv(self.csv_file, fieldnames, rows)
        
        print(f"\n\n{'=' * 60}")
        print(f"📊 CSV SUMMARY — {self.csv_file}")
        print(f"{'=' * 60}")
        print_summary(rows, skipped=skipped)
        print(f"\n💾 CSV saved: {self.csv_file}")
        logger.info(f"CSV done: {self.csv_file}")
        
        return rows
    
    async def _process_and_save(
        self,
        job: Dict[str, Any],
        row_idx: int,
        fieldnames: List[str],
        rows: List[Dict[str, Any]],
    ) -> None:
        """
        Process a job and save results to CSV.
        
        Args:
            job: Job dictionary.
            row_idx: Index of the row in CSV.
            fieldnames: CSV fieldnames.
            rows: CSV rows.
        """
        await self._process_job(job, self.sem_dl, self.sem_up)
        
        async with self.csv_lock:
            row = rows[row_idx]
            row['status'] = job['status']
            if job.get('title'):
                row['title'] = row.get('title', '').strip() or job['title']
            if job.get('streamtape'):
                row['streamtape'] = job['streamtape']
            save_csv(self.csv_file, fieldnames, rows)
            logger.debug(f"CSV saved (row #{row_idx + 2}, status={job['status']})")
            print(f"💾 CSV updated (row #{row_idx + 2})")
    
    async def _process_job(
        self,
        job: Dict[str, Any],
        sem_dl: asyncio.Semaphore,
        sem_up: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        """
        Process a single job: download and optionally upload.
        
        Args:
            job: Job dictionary with m3u8, output, etc.
            sem_dl: Download semaphore.
            sem_up: Upload semaphore.
            
        Returns:
            Updated job dictionary.
        """
        # Download phase
        async with sem_dl:
            async with self._dl_lock:
                self._active_dl += 1
            status = self._get_status()
            print(f"{status} ↓ {self._truncate(job['title'])}")
            
            success = await asyncio.to_thread(
                download_video,
                m3u8_url=job['m3u8'],
                output_file=job['output'],
                referer=self.referer,
            )
            
            async with self._dl_lock:
                self._active_dl -= 1
        
        if not success:
            job['status'] = 'DOWNLOAD_FAILED'
            return job
        
        size = os.path.getsize(job['output']) / (1024 * 1024)
        job['status'] = 'DOWNLOADED'
        
        if self.upload:
            async with sem_up:
                async with self._up_lock:
                    self._active_up += 1
                status = self._get_status()
                print(f"{status} ↑ {self._truncate(job['title'])}")
                
                st_url = await upload_to_streamtape(job['output'])
                
                async with self._up_lock:
                    self._active_up -= 1
            
            if st_url:
                job['streamtape'] = st_url
                job['status'] = 'OK'
                print(f"✅ {self._truncate(job['title'], 25)} → {st_url}")
            else:
                job['status'] = 'UPLOAD_FAILED'
        
        return job
    
    def _print_header(self, seq: int, total: int, row_idx: int, url: str) -> None:
        """Print section header."""
        print(f"[{seq}/{total}] {self._truncate(url, 40)}")

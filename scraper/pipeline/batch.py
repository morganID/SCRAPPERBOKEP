"""
Batch processing pipeline for multiple URLs.
"""

import asyncio
import logging
import os
from typing import List, Dict, Any, Optional

import config
from downloader import download_video, pick_best_url
from uploader import upload_to_streamtape
from ..core.scraper import VideoScraper
from ..core.interceptor import NetworkInterceptor
from ..utils.helpers import sanitize_filename, unique_output

import logging

logger = logging.getLogger(__name__)


class BatchPipeline:
    """
    Pipeline for batch processing multiple video URLs.
    
    Handles concurrent downloading and uploading with configurable limits.
    """
    
    def __init__(
        self,
        output_dir: str = ".",
        referer: Optional[str] = None,
        upload: bool = False,
    ) -> None:
        """
        Initialize the batch pipeline.
        
        Args:
            output_dir: Directory to save downloaded videos.
            referer: HTTP referer to use.
            upload: Whether to upload videos after download.
        """
        self.output_dir = output_dir
        self.referer = referer or config.DEFAULT_REFERER
        self.upload = upload
        
        # Get concurrency limits from config
        self.max_dl = getattr(config, 'MAX_CONCURRENT_DOWNLOADS', 3)
        self.max_up = getattr(config, 'MAX_CONCURRENT_UPLOADS', 2)
        
        self.sem_dl = asyncio.Semaphore(self.max_dl)
        self.sem_up = asyncio.Semaphore(self.max_up)
    
    async def run(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Run the batch pipeline on a list of URLs.
        
        Args:
            urls: List of URLs to process.
            
        Returns:
            List of job results.
        """
        valid_urls = [u.strip() for u in urls if u.strip() and not u.startswith('#')]
        total = len(valid_urls)
        
        print(f"⚡ Concurrent: download(×{self.max_dl}), upload(×{self.max_up})")
        logger.info(f"Batch: {total} URLs")
        
        os.makedirs(self.output_dir, exist_ok=True)
        
        scraper = VideoScraper()
        jobs: List[Dict[str, Any]] = []
        tasks: List[asyncio.Task] = []
        
        try:
            await scraper.start_browser()
            
            for i, url in enumerate(valid_urls, 1):
                self._print_header(i, total, url)
                
                logger.info(f"[{i}/{total}] Scraping: {url}")
                scraper.reset()
                
                try:
                    m3u8_urls = await scraper.scrape(url)
                    
                    if not m3u8_urls:
                        logger.warning(f"[{i}/{total}] M3U8 not found")
                        print("❌ M3U8 not found")
                        jobs.append({'url': url, 'title': '', 'status': 'NO_M3U8'})
                        continue
                    
                    best = pick_best_url(m3u8_urls)
                    title = await scraper.get_page_title()
                    title = sanitize_filename(title) or f"video_{i}"
                    output = unique_output(os.path.join(self.output_dir, f"{title}.mp4"))
                    
                    print(f"📝 Title: {title}")
                    print(f"🏆 Best: {best}")
                    logger.debug(f"[{i}/{total}] Output: {output}")
                    
                    job = {
                        'url': url,
                        'title': title,
                        'm3u8': best,
                        'output': output,
                        'status': 'QUEUED',
                        'streamtape': '',
                    }
                    jobs.append(job)
                    
                    task = asyncio.create_task(
                        self._process_job(job, self.sem_dl, self.sem_up)
                    )
                    tasks.append(task)
                    
                except Exception as e:
                    logger.error(f"[{i}/{total}] Scrape error: {e}", exc_info=True)
                    print(f"❌ Error: {e}")
                    jobs.append({'url': url, 'title': '', 'status': f'ERROR: {e}'})
                
                await asyncio.sleep(3)
                
        finally:
            await scraper.close()
        
        if tasks:
            print(f"\n⏳ Waiting for {len(tasks)} download/upload to complete...")
            await asyncio.gather(*tasks)
        
        self._print_summary(jobs)
        
        return jobs
    
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
        async with sem_dl:
            logger.info(f"Downloading: {job['title'][:40]}")
            log.debug(f"M3U8: {job['m3u8']}")
            
            success = await asyncio.to_thread(
                download_video,
                m3u8_url=job['m3u8'],
                output_file=job['output'],
                referer=self.referer,
            )
        
        if not success:
            job['status'] = 'DOWNLOAD_FAILED'
            logger.warning(f"Download failed: {job['title'][:40]}")
            return job
        
        size = os.path.getsize(job['output']) / (1024 * 1024)
        print(f"✅ Downloaded: {job['title'][:40]} ({size:.1f} MB)")
        logger.info(f"Downloaded: {job['title'][:40]} ({size:.1f} MB)")
        job['status'] = 'DOWNLOADED'
        
        if self.upload:
            async with sem_up:
                logger.info(f"Uploading: {job['title'][:40]}")
                st_url = await upload_to_streamtape(job['output'])
            
            if st_url:
                job['streamtape'] = st_url
                job['status'] = 'OK'
                print(f"📺 {st_url}")
                logger.info(f"Uploaded: {st_url}")
            else:
                job['status'] = 'UPLOAD_FAILED'
                logger.warning(f"Upload failed: {job['title'][:40]}")
        
        return job
    
    def _print_header(self, index: int, total: int, url: str) -> None:
        """Print section header."""
        print(f"\n{'#' * 60}")
        print(f"# VIDEO {index}/{total}")
        print(f"# {url}")
        print(f"{'#' * 60}")
    
    def _print_summary(self, jobs: List[Dict[str, Any]]) -> None:
        """Print batch summary."""
        print(f"\n\n{'=' * 60}")
        print(f"📊 BATCH SUMMARY")
        print(f"{'=' * 60}")
        
        for job in jobs:
            status = job.get('status', '')
            icon = "✅" if status == 'OK' else ("⬇️" if status == 'DOWNLOADED' else "❌")
            title = job.get('title', '')[:40] or job['url'][:40]
            print(f"  {icon} {title}")
            print(f"     Status: {status}")
            if job.get('streamtape'):
                print(f"     📺 {job['streamtape']}")
        
        ok = sum(1 for j in jobs if j['status'] == 'OK')
        dl = sum(1 for j in jobs if j['status'] == 'DOWNLOADED')
        fail = sum(1 for j in jobs if j['status'] not in ('OK', 'DOWNLOADED'))
        
        print(f"\n  ✅ OK: {ok}  ⬇️ Downloaded: {dl}  ❌ Failed: {fail}")
        logger.info(f"Batch done: OK={ok}, Downloaded={dl}, Failed={fail}")


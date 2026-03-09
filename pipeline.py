"""
pipeline.py - Concurrent scrape → download → upload pipeline

Usage:
    jobs = [Job(url="..."), Job(url="...")]
    pipe = Pipeline(upload=True, max_dl=3, max_up=2)
    await pipe.run(jobs)                       # batch
    await pipe.run(jobs, on_update=callback)   # CSV-style
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from scraper import VideoScraper
from downloader import download_video, pick_best_url
from uploader import upload_to_streamtape
from utils import sanitize_filename, get_page_title
import config


# ═══════════════════════════════════════
#  Job dataclass
# ═══════════════════════════════════════

@dataclass
class Job:
    url: str
    id: Any = None                        # batch: seq, csv: row index
    title: str = ''
    m3u8: str = ''
    output: str = ''
    status: str = 'PENDING'
    streamtape: str = ''
    error: str = ''
    meta: dict = field(default_factory=dict)

    @property
    def ok(self):
        return self.status == 'OK'

    @property
    def done(self):
        return self.status not in ('PENDING', 'SCRAPED', 'DOWNLOADED')


# ═══════════════════════════════════════
#  Filename allocator (concurrent-safe)
# ═══════════════════════════════════════

class _FileAllocator:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._reserved: set[str] = set()

    async def allocate(self, title, output_dir):
        async with self._lock:
            fname = sanitize_filename(title)
            path = os.path.join(output_dir, f"{fname}.mp4")
            counter = 1
            while os.path.exists(path) or path in self._reserved:
                path = os.path.join(output_dir, f"{fname}_{counter}.mp4")
                counter += 1
            self._reserved.add(path)
            return path


# ═══════════════════════════════════════
#  Pipeline
# ═══════════════════════════════════════

class Pipeline:
    """
    Scraper(1) ──→ Download Workers(×N) ──→ Upload Workers(×M)
         sequential        concurrent             concurrent
    """

    def __init__(self, *,
                 max_dl: int = 3,
                 max_up: int = 2,
                 referer: str = None,
                 upload: bool = False,
                 output_dir: str = '.'):
        self.max_dl = max_dl
        self.max_up = max_up
        self.referer = referer or config.DEFAULT_REFERER
        self.upload = upload
        self.output_dir = output_dir
        self._alloc = _FileAllocator()
        self._dl_q: asyncio.Queue = None
        self._up_q: asyncio.Queue = None
        self._on_update: Optional[Callable] = None

    # ── public ──

    async def run(self, jobs: list[Job],
                  on_update: Callable[[Job], Any] = None) -> list[Job]:
        """
        Run the pipeline. Returns the same jobs list with updated statuses.

        on_update(job) dipanggil setiap kali status job berubah.
        Bisa sync atau async.
        """
        self._on_update = on_update
        self._dl_q = asyncio.Queue()
        self._up_q = asyncio.Queue()
        total = len(jobs)

        print(f"⚡ Pipeline: scrape(1) → download(×{self.max_dl})"
              f"{f' → upload(×{self.max_up})' if self.upload else ''}")
        print(f"📋 Total: {total} jobs\n")

        os.makedirs(self.output_dir, exist_ok=True)

        # Start workers
        dl_tasks = [asyncio.create_task(self._dl_worker(i + 1))
                    for i in range(self.max_dl)]
        up_tasks = ([asyncio.create_task(self._up_worker(i + 1))
                     for i in range(self.max_up)] if self.upload else [])

        # Scraper feeds dl_queue (sequential)
        await self._scrape_worker(jobs)

        # Wait downloads
        await asyncio.gather(*dl_tasks)

        # Signal & wait uploads
        if self.upload and up_tasks:
            for _ in range(self.max_up):
                await self._up_q.put(None)
            await asyncio.gather(*up_tasks)

        return jobs

    # ── internal: notify ──

    async def _notify(self, job: Job):
        if not self._on_update:
            return
        ret = self._on_update(job)
        if asyncio.iscoroutine(ret):
            await ret

    # ── internal: scraper (sequential, 1 browser) ──

    async def _scrape_worker(self, jobs: list[Job]):
        scraper = VideoScraper()
        total = len(jobs)

        try:
            await scraper.start_browser()

            for seq, job in enumerate(jobs, 1):
                print(f"\n{'─'*55}")
                print(f"🔍 [{seq}/{total}] {job.url[:80]}")
                scraper.reset()

                try:
                    m3u8_urls = await scraper.scrape(job.url)

                    if m3u8_urls:
                        job.m3u8 = pick_best_url(m3u8_urls)
                        title = await get_page_title(scraper.page)
                        job.title = job.title or sanitize_filename(title) or f"video_{seq}"
                        job.output = await self._alloc.allocate(
                            job.title, self.output_dir
                        )
                        job.status = 'SCRAPED'
                        await self._notify(job)

                        print(f"   📝 {job.title}")
                        print(f"   🏆 {job.m3u8[:80]}")

                        await self._dl_q.put(job)
                    else:
                        print(f"   ❌ M3U8 tidak ditemukan")
                        job.status = 'NO_M3U8'
                        await self._notify(job)

                except Exception as e:
                    print(f"   ❌ Scrape error: {e}")
                    job.status = 'SCRAPE_ERROR'
                    job.error = str(e)[:80]
                    await self._notify(job)

                await asyncio.sleep(2)
        finally:
            await scraper.close()
            for _ in range(self.max_dl):
                await self._dl_q.put(None)

    # ── internal: download workers ──

    async def _dl_worker(self, wid):
        while True:
            job = await self._dl_q.get()
            if job is None:
                break

            short = job.title[:40]
            print(f"\n⬇️  [DL-{wid}] {short}")

            try:
                success = await asyncio.to_thread(
                    download_video,
                    m3u8_url=job.m3u8,
                    output_file=job.output,
                    referer=self.referer,
                )

                if success:
                    sz = os.path.getsize(job.output) / (1024 * 1024)
                    print(f"✅ [DL-{wid}] Done: {short} ({sz:.1f} MB)")
                    job.status = 'DOWNLOADED'
                    await self._notify(job)

                    if self.upload:
                        await self._up_q.put(job)
                else:
                    print(f"❌ [DL-{wid}] Failed: {short}")
                    job.status = 'DOWNLOAD_FAILED'
                    await self._notify(job)

            except Exception as e:
                print(f"❌ [DL-{wid}] Error: {e}")
                job.status = 'DL_ERROR'
                job.error = str(e)[:80]
                await self._notify(job)

    # ── internal: upload workers ──

    async def _up_worker(self, wid):
        while True:
            job = await self._up_q.get()
            if job is None:
                break

            short = job.title[:40]
            print(f"\n⬆️  [UP-{wid}] {short}")

            try:
                st_url = await upload_to_streamtape(job.output)

                if st_url:
                    print(f"📺 [UP-{wid}] {st_url}")
                    job.streamtape = st_url
                    job.status = 'OK'
                else:
                    print(f"❌ [UP-{wid}] Upload gagal")
                    job.status = 'UPLOAD_FAILED'

                await self._notify(job)

            except Exception as e:
                print(f"❌ [UP-{wid}] Error: {e}")
                job.status = 'UP_ERROR'
                job.error = str(e)[:80]
                await self._notify(job)
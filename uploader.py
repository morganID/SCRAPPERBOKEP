"""Upload video ke Streamtape dengan folder support"""

import os
import re
import json
import asyncio
import logging
import aiohttp
import config

# ── Logger ──
logger = logging.getLogger(__name__)


async def upload_to_streamtape(file_path, folder_id=None):
    """
    Upload 1 file ke Streamtape.
    Return URL string jika sukses, None jika gagal.
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return None

    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path) / (1024 * 1024)
    folder_id = folder_id or getattr(config, 'STREAMTAPE_FOLDER', None)

    print(f"\n⬆️  Upload: {filename} ({file_size:.1f} MB)")
    logger.debug(f"Folder: {folder_id or 'root'}")

    timeout = aiohttp.ClientTimeout(total=3600)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            # ── Step 1: Get upload URL ──
            api_url = (
                f"https://api.streamtape.com/file/ul"
                f"?login={config.STREAMTAPE_LOGIN}"
                f"&key={config.STREAMTAPE_KEY}"
            )
            if folder_id:
                api_url += f"&folder={folder_id}"

            logger.debug("Requesting upload URL...")

            async with session.get(api_url) as resp:
                data = await resp.json()
                if data.get('status') != 200:
                    logger.error(f"API error: {data.get('msg')}")
                    return None
                upload_url = data['result']['url']
                logger.debug(f"Upload URL: {upload_url[:80]}...")

            # ── Step 2: Upload file ──
            logger.debug("Uploading file...")

            with open(file_path, 'rb') as f:
                form = aiohttp.FormData()
                form.add_field(
                    'file1', f,
                    filename=filename,
                    content_type='video/mp4'
                )

                async with session.post(upload_url, data=form) as resp:
                    content_type = resp.headers.get('Content-Type', '')
                    response_text = await resp.text()

                    logger.debug(f"Response: HTTP {resp.status}, "
                                 f"Content-Type: {content_type}")

                    # ── Try 1: Parse JSON response ──
                    if 'application/json' in content_type:
                        try:
                            result = json.loads(response_text)
                            if result.get('status') == 200:
                                url = result['result']['url']
                                print(f"   ✅ {url}")
                                return url
                            else:
                                logger.error(f"Upload failed: {result.get('msg')}")
                                return None
                        except (json.JSONDecodeError, KeyError, TypeError):
                            logger.debug("JSON parse failed, trying regex...")

                    # ── Try 2: Regex cari URL streamtape ──
                    match = re.search(
                        r'https?://streamtape\.com/v/([a-zA-Z0-9]+)',
                        response_text
                    )
                    if match:
                        url = match.group(0)
                        print(f"   ✅ {url}")
                        return url

                    # ── Try 3: Regex cari video ID ──
                    match = re.search(
                        r'"id"\s*:\s*"([a-zA-Z0-9]+)"',
                        response_text
                    )
                    if match:
                        video_id = match.group(1)
                        url = f"https://streamtape.com/v/{video_id}"
                        print(f"   ✅ {url}")
                        return url

                    # ── Try 4: HTTP 200 → cek file list ──
                    if resp.status == 200:
                        logger.info("Upload done, searching file list...")

                        for attempt in range(5):
                            await asyncio.sleep(3)
                            logger.debug(f"Checking file list... ({attempt + 1}/5)")

                            found_url = await _find_uploaded_file(
                                session, filename, folder_id
                            )
                            if found_url:
                                return found_url

                        logger.warning("File uploaded but URL not found")
                        logger.warning("Check manually: https://streamtape.com/videos")
                        return None

                    logger.error(f"HTTP {resp.status}")
                    logger.debug(f"Response body: {response_text[:300]}")
                    return None

        except asyncio.TimeoutError:
            logger.error(f"Upload timeout: {filename}")
            return None
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return None


async def _find_uploaded_file(session, filename, folder_id=None):
    """
    Cari file yang baru diupload dari file list API.
    Return URL jika ketemu, None jika belum.
    """
    try:
        api_url = (
            f"https://api.streamtape.com/file/listfolder"
            f"?login={config.STREAMTAPE_LOGIN}"
            f"&key={config.STREAMTAPE_KEY}"
        )
        if folder_id:
            api_url += f"&folder={folder_id}"

        async with session.get(api_url) as resp:
            data = await resp.json()

            if data.get('status') != 200:
                return None

            files = data.get('result', {}).get('files', [])
            if not files:
                return None

            clean_target = re.sub(
                r'[^a-z0-9]', '',
                os.path.splitext(filename)[0].lower()
            )

            for f in reversed(files):
                file_name = f.get('name', '')
                clean_name = re.sub(
                    r'[^a-z0-9]', '',
                    os.path.splitext(file_name)[0].lower()
                )

                if clean_target == clean_name or \
                   clean_target in clean_name or \
                   clean_name in clean_target:
                    file_id = f.get('linkid')
                    if file_id:
                        url = f"https://streamtape.com/v/{file_id}"
                        print(f"   ✅ {url}")
                        return url

            return None

    except Exception as e:
        logger.warning(f"File list check error: {e}")
        return None


async def upload_multiple(file_paths, folder_id=None, concurrent=3):
    """Upload banyak file ke folder tertentu"""
    folder_id = folder_id or getattr(config, 'STREAMTAPE_FOLDER', None)
    semaphore = asyncio.Semaphore(concurrent)

    async def _upload_one(fp):
        async with semaphore:
            url = await upload_to_streamtape(fp, folder_id)
            return {
                'file': os.path.basename(fp),
                'status': 'success' if url else 'failed',
                'url': url or ''
            }

    total = len(file_paths)
    print(f"\n🚀 Uploading {total} file(s) to Streamtape"
          f" (folder: {folder_id or 'root'}, concurrent: {concurrent})")

    tasks = [_upload_one(fp) for fp in file_paths]
    results = await asyncio.gather(*tasks)

    success = sum(1 for r in results if r['status'] == 'success')
    failed = total - success

    print(f"\n📊 Upload done: {success} success, {failed} failed")

    if failed > 0:
        for r in results:
            if r['status'] == 'failed':
                logger.warning(f"Failed: {r['file']}")

    return results


# ============ FOLDER HELPERS ============

async def list_folders():
    """List semua folder di Streamtape"""
    async with aiohttp.ClientSession() as session:
        api_url = (
            f"https://api.streamtape.com/file/listfolder"
            f"?login={config.STREAMTAPE_LOGIN}"
            f"&key={config.STREAMTAPE_KEY}"
        )
        async with session.get(api_url) as resp:
            data = await resp.json()

            if data.get('status') == 200:
                folders = data.get('result', {}).get('folders', [])
                print(f"\n📁 Folders ({len(folders)}):")
                for f in folders:
                    print(f"   {f['id']} → {f['name']}")
                return folders
            else:
                logger.error(f"List folders failed: {data.get('msg')}")
                return []


async def create_folder(name, parent_id=None):
    """Buat folder baru di Streamtape"""
    async with aiohttp.ClientSession() as session:
        api_url = (
            f"https://api.streamtape.com/file/createfolder"
            f"?login={config.STREAMTAPE_LOGIN}"
            f"&key={config.STREAMTAPE_KEY}"
            f"&name={name}"
        )
        if parent_id:
            api_url += f"&folder={parent_id}"

        async with session.get(api_url) as resp:
            data = await resp.json()

            if data.get('status') == 200:
                folder_id = data['result']['folderid']
                print(f"✅ Folder created: {name} (ID: {folder_id})")
                return folder_id
            else:
                logger.error(f"Create folder failed: {data.get('msg')}")
                return None
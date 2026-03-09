"""Upload video ke Streamtape"""

import os
import asyncio
import aiohttp
import config


async def upload_to_streamtape(file_path):
    """
    Upload 1 file ke Streamtape
    
    Args:
        file_path: Path ke file video
    
    Returns:
        str: URL streamtape jika sukses, None jika gagal
    """
    if not os.path.exists(file_path):
        print(f"   ❌ File tidak ditemukan: {file_path}")
        return None

    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path) / (1024 * 1024)

    print(f"\n⬆️  Uploading ke Streamtape...")
    print(f"   File : {filename}")
    print(f"   Size : {file_size:.1f} MB")

    timeout = aiohttp.ClientTimeout(total=3600)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            # Step 1: Get upload URL
            api_url = (
                f"https://api.streamtape.com/file/ul"
                f"?login={config.STREAMTAPE_LOGIN}"
                f"&key={config.STREAMTAPE_KEY}"
            )

            async with session.get(api_url) as resp:
                data = await resp.json()
                if data.get('status') != 200:
                    print(f"   ❌ API Error: {data.get('msg')}")
                    return None
                upload_url = data['result']['url']

            # Step 2: Upload file
            with open(file_path, 'rb') as f:
                form = aiohttp.FormData()
                form.add_field('file1', f, filename=filename, content_type='video/mp4')

                async with session.post(upload_url, data=form) as resp:
                    result = await resp.json()

                    if result.get('status') == 200:
                        url = result['result']['url']
                        print(f"   ✅ Uploaded: {url}")
                        return url
                    else:
                        print(f"   ❌ Upload failed: {result.get('msg')}")
                        return None

        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None


async def upload_multiple(file_paths, concurrent=3):
    """
    Upload banyak file sekaligus
    
    Args:
        file_paths: List path file
        concurrent: Jumlah upload bersamaan
    
    Returns:
        List of dict hasil upload
    """
    semaphore = asyncio.Semaphore(concurrent)

    async def upload_with_semaphore(fp):
        async with semaphore:
            url = await upload_to_streamtape(fp)
            return {
                'file': os.path.basename(fp),
                'status': 'success' if url else 'failed',
                'url': url or ''
            }

    tasks = [upload_with_semaphore(fp) for fp in file_paths]
    results = await asyncio.gather(*tasks)

    # Summary
    success = sum(1 for r in results if r['status'] == 'success')
    print(f"\n📊 Upload Summary: {success}/{len(results)} berhasil")

    return results
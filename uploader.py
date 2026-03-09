"""Upload video ke Streamtape dengan folder support"""

import os
import re
import asyncio
import aiohttp
import config


async def upload_to_streamtape(file_path, folder_id=None):
    """
    Upload 1 file ke Streamtape
    
    Args:
        file_path: Path ke file video
        folder_id: ID folder tujuan (optional, default dari config)
    
    Returns:
        str: URL streamtape jika sukses, None jika gagal
    """
    if not os.path.exists(file_path):
        print(f"   ❌ File tidak ditemukan: {file_path}")
        return None

    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path) / (1024 * 1024)
    folder_id = folder_id or getattr(config, 'STREAMTAPE_FOLDER', None)

    print(f"\n⬆️  Uploading ke Streamtape...")
    print(f"   File   : {filename}")
    print(f"   Size   : {file_size:.1f} MB")
    if folder_id:
        print(f"   Folder : {folder_id}")

    timeout = aiohttp.ClientTimeout(total=3600)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            # Step 1: Get upload URL (dengan folder)
            api_url = (
                f"https://api.streamtape.com/file/ul"
                f"?login={config.STREAMTAPE_LOGIN}"
                f"&key={config.STREAMTAPE_KEY}"
            )
            if folder_id:
                api_url += f"&folder={folder_id}"

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
                    content_type = resp.headers.get('Content-Type', '')
                    
                    if 'application/json' in content_type:
                        result = await resp.json()
                        if result.get('status') == 200:
                            url = result['result']['url']
                            print(f"   ✅ Uploaded: {url}")
                            return url
                        else:
                            print(f"   ❌ Failed: {result.get('msg')}")
                            return None
                    else:
                        # Response bukan JSON
                        text = await resp.text()
                        
                        # Cari URL di response
                        match = re.search(r'https?://streamtape\.com/v/[a-zA-Z0-9]+', text)
                        if match:
                            url = match.group(0)
                            print(f"   ✅ Uploaded: {url}")
                            return url
                        
                        # Cek file list kalau status 200
                        if resp.status == 200:
                            print(f"   ⏳ Checking file list...")
                            return await check_uploaded_file(session, filename, folder_id)
                        
                        print(f"   ❌ Failed: HTTP {resp.status}")
                        return None

        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None


async def check_uploaded_file(session, filename, folder_id=None):
    """Cek file dari file list API"""
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
            if data.get('status') == 200:
                files = data.get('result', {}).get('files', [])
                
                for f in reversed(files):
                    if filename.lower() in f.get('name', '').lower():
                        file_id = f.get('linkid')
                        url = f"https://streamtape.com/v/{file_id}"
                        print(f"   ✅ Found: {url}")
                        return url
                        
        print(f"   ⚠️ URL tidak ditemukan")
        return None
        
    except Exception as e:
        print(f"   ⚠️ Error: {e}")
        return None


async def upload_multiple(file_paths, folder_id=None, concurrent=3):
    """Upload banyak file sekaligus ke folder tertentu"""
    folder_id = folder_id or getattr(config, 'STREAMTAPE_FOLDER', None)
    semaphore = asyncio.Semaphore(concurrent)

    async def upload_with_semaphore(fp):
        async with semaphore:
            url = await upload_to_streamtape(fp, folder_id)
            return {
                'file': os.path.basename(fp),
                'status': 'success' if url else 'failed',
                'url': url or ''
            }

    print(f"\n{'='*50}")
    print(f"🚀 STREAMTAPE UPLOADER")
    print(f"{'='*50}")
    print(f"📁 Files    : {len(file_paths)}")
    print(f"📂 Folder   : {folder_id or 'root'}")
    print(f"⚡ Concurrent: {concurrent}")
    print(f"{'='*50}")

    tasks = [upload_with_semaphore(fp) for fp in file_paths]
    results = await asyncio.gather(*tasks)

    success = sum(1 for r in results if r['status'] == 'success')
    
    print(f"\n{'='*50}")
    print(f"📊 SUMMARY: {success}/{len(results)} berhasil")
    print(f"{'='*50}")

    return results


# ============ HELPER FUNCTIONS ============

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
                print("\n📁 Folders:")
                for f in folders:
                    print(f"   {f['id']} → {f['name']}")
                return folders
            else:
                print(f"❌ Error: {data.get('msg')}")
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
                print(f"❌ Error: {data.get('msg')}")
                return None
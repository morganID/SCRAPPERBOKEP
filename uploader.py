"""Upload video ke Streamtape dengan folder support"""

import os
import re
import asyncio
import aiohttp
import config


async def upload_to_streamtape(file_path, folder_id=None):
    """
    Upload 1 file ke Streamtape
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
            # Step 1: Get upload URL
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
                    response_text = await resp.text()
                    
                    # Debug: tampilkan response
                    print(f"   📡 Response status: {resp.status}")
                    print(f"   📡 Content-Type: {content_type}")
                    
                    # Coba parse sebagai JSON
                    if 'application/json' in content_type:
                        try:
                            result = json.loads(response_text)
                            if result.get('status') == 200:
                                url = result['result']['url']
                                print(f"   ✅ Uploaded: {url}")
                                return url
                            else:
                                print(f"   ❌ Failed: {result.get('msg')}")
                        except:
                            pass
                    
                    # Response mungkin berisi URL langsung atau info lain
                    # Cari URL pattern di response
                    match = re.search(r'https?://streamtape\.com/v/([a-zA-Z0-9]+)', response_text)
                    if match:
                        url = match.group(0)
                        print(f"   ✅ Uploaded: {url}")
                        return url
                    
                    # Cari video ID pattern
                    match = re.search(r'"id"\s*:\s*"([a-zA-Z0-9]+)"', response_text)
                    if match:
                        video_id = match.group(1)
                        url = f"https://streamtape.com/v/{video_id}"
                        print(f"   ✅ Uploaded: {url}")
                        return url
                    
                    # Kalau status 200, kemungkinan sukses - tunggu dan cek file list
                    if resp.status == 200:
                        print(f"   ⏳ Upload selesai, menunggu proses...")
                        
                        # Tunggu beberapa detik biar Streamtape proses
                        for attempt in range(5):
                            await asyncio.sleep(3)  # Tunggu 3 detik
                            print(f"   🔍 Checking file list... (attempt {attempt + 1}/5)")
                            
                            found_url = await check_uploaded_file(session, filename, folder_id)
                            if found_url:
                                return found_url
                        
                        print(f"   ⚠️ File mungkin sudah terupload tapi URL belum tersedia")
                        print(f"   💡 Cek manual di: https://streamtape.com/videos")
                        return None
                    
                    print(f"   ❌ Failed: HTTP {resp.status}")
                    print(f"   Response: {response_text[:300]}")
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
                
                # Bersihkan filename untuk comparison
                clean_filename = os.path.splitext(filename)[0].lower()
                clean_filename = re.sub(r'[^a-z0-9]', '', clean_filename)
                
                # Cari file dengan nama yang mirip (terbaru dulu)
                for f in reversed(files):
                    file_name = f.get('name', '')
                    clean_name = os.path.splitext(file_name)[0].lower()
                    clean_name = re.sub(r'[^a-z0-9]', '', clean_name)
                    
                    # Cek kesamaan
                    if clean_filename in clean_name or clean_name in clean_filename:
                        file_id = f.get('linkid')
                        url = f"https://streamtape.com/v/{file_id}"
                        print(f"   ✅ Found: {url}")
                        return url
                
                # Fallback: ambil file terbaru (yang baru diupload)
                if files:
                    latest = files[-1]
                    file_id = latest.get('linkid')
                    latest_name = latest.get('name', '')
                    
                    # Konfirmasi dengan user
                    print(f"   🔍 File terbaru: {latest_name}")
                    url = f"https://streamtape.com/v/{file_id}"
                    print(f"   ✅ Assuming: {url}")
                    return url
                        
        return None
        
    except Exception as e:
        print(f"   ⚠️ Error checking: {e}")
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
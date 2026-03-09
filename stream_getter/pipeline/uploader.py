"""
Video Uploader - Upload videos to Streamtape.

This module provides functionality for uploading video files to Streamtape,
including folder management and batch upload support.
"""

import os
import re
import json
import asyncio
import logging
from typing import Optional, List, Dict, Any

import aiohttp
import config

logger = logging.getLogger(__name__)


class StreamtapeUploader:
    """
    Handles video upload operations to Streamtape.
    
    Attributes:
        login: Streamtape API login.
        key: Streamtape API key.
        default_folder: Default folder ID for uploads.
        timeout: HTTP timeout for uploads.
    """
    
    BASE_URL = "https://api.streamtape.com"
    
    def __init__(
        self,
        login: Optional[str] = None,
        key: Optional[str] = None,
        default_folder: Optional[str] = None,
        timeout: int = 3600,
    ):
        """
        Initialize the Streamtape uploader.
        
        Args:
            login: Streamtape API login.
            key: Streamtape API key.
            default_folder: Default folder ID for uploads.
            timeout: HTTP timeout in seconds.
        """
        self.login = login or getattr(config, 'STREAMTAPE_LOGIN', '')
        self.key = key or getattr(config, 'STREAMTAPE_KEY', '')
        self.default_folder = default_folder or getattr(config, 'STREAMTAPE_FOLDER', None)
        self.timeout = aiohttp.ClientTimeout(total=timeout)
    
    async def upload(
        self,
        file_path: str,
        folder_id: Optional[str] = None,
        delete_after: Optional[bool] = None,
    ) -> Optional[str]:
        """
        Upload a single file to Streamtape.
        
        Args:
            file_path: Path to the video file.
            folder_id: Optional folder ID.
            delete_after: Delete file after successful upload (default from config).
            
        Returns:
            Streamtape URL if successful, None otherwise.
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
        
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        folder_id = folder_id or self.default_folder
        delete_after = delete_after if delete_after is not None else getattr(config, 'DELETE_AFTER_UPLOAD', False)
        
        logger.info(f"Uploading: {filename} ({file_size:.1f} MB)")
        
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                # Step 1: Get upload URL
                upload_url = await self._get_upload_url(session, folder_id)
                if not upload_url:
                    return None
                
                # Step 2: Upload file
                result = await self._upload_file(session, upload_url, file_path, filename)
                
                # Step 3: Delete file after successful upload
                if result and delete_after:
                    try:
                        os.remove(file_path)
                        logger.info(f"Deleted: {file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete {file_path}: {e}")
                
                return result
                
            except asyncio.TimeoutError:
                logger.error(f"Upload timeout: {filename}")
                return None
            except Exception as e:
                logger.error(f"Upload error: {e}")
                return None
    
    async def _get_upload_url(
        self,
        session: aiohttp.ClientSession,
        folder_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get upload URL from Streamtape API.
        
        Args:
            session: aiohttp session.
            folder_id: Optional folder ID.
            
        Returns:
            Upload URL or None on error.
        """
        api_url = (
            f"{self.BASE_URL}/file/ul"
            f"?login={self.login}&key={self.key}"
        )
        if folder_id:
            api_url += f"&folder={folder_id}"
        
        try:
            async with session.get(api_url) as resp:
                data = await resp.json()
                if data.get('status') != 200:
                    logger.error(f"API error: {data.get('msg')}")
                    return None
                return data['result']['url']
        except Exception as e:
            logger.error(f"Get upload URL error: {e}")
            return None
    
    async def _upload_file(
        self,
        session: aiohttp.ClientSession,
        upload_url: str,
        file_path: str,
        filename: str,
    ) -> Optional[str]:
        """
        Upload file to the provided URL.
        
        Args:
            session: aiohttp session.
            upload_url: Upload URL.
            file_path: Path to file.
            filename: Filename for upload.
            
        Returns:
            Streamtape URL if successful, None otherwise.
        """
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
                
                # Try 1: Parse JSON response
                if 'application/json' in content_type:
                    try:
                        result = json.loads(response_text)
                        if result.get('status') == 200:
                            return result['result']['url']
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass
                
                # Try 2: Regex find Streamtape URL
                match = re.search(
                    r'https?://streamtape\.com/v/([a-zA-Z0-9]+)',
                    response_text
                )
                if match:
                    return match.group(0)
                
                # Try 3: Regex find video ID
                match = re.search(r'"id"\s*:\s*"([a-zA-Z0-9]+)"', response_text)
                if match:
                    return f"https://streamtape.com/v/{match.group(1)}"
                
                # Try 4: Check file list if HTTP 200
                if resp.status == 200:
                    return await self._find_uploaded_file(session, filename)
                
                logger.error(f"Upload failed: HTTP {resp.status}")
                return None
    
    async def _find_uploaded_file(
        self,
        session: aiohttp.ClientSession,
        filename: str,
        folder_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Find uploaded file from file list API.
        
        Args:
            session: aiohttp session.
            filename: Filename to find.
            folder_id: Optional folder ID.
            
        Returns:
            Streamtape URL if found, None otherwise.
        """
        folder_id = folder_id or self.default_folder
        
        try:
            api_url = (
                f"{self.BASE_URL}/file/listfolder"
                f"?login={self.login}&key={self.key}"
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
                
                # Compare filenames
                clean_target = re.sub(r'[^a-z0-9]', '', os.path.splitext(filename)[0].lower())
                
                for f in reversed(files):
                    file_name = f.get('name', '')
                    clean_name = re.sub(r'[^a-z0-9]', '', os.path.splitext(file_name)[0].lower())
                    
                    if (clean_target == clean_name or 
                        clean_target in clean_name or 
                        clean_name in clean_target):
                        file_id = f.get('linkid')
                        if file_id:
                            return f"https://streamtape.com/v/{file_id}"
                
                return None
                
        except Exception as e:
            logger.warning(f"File list check error: {e}")
            return None
    
    async def upload_multiple(
        self,
        file_paths: List[str],
        folder_id: Optional[str] = None,
        concurrent: int = 3,
        delete_after: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        Upload multiple files with concurrency control.
        
        Args:
            file_paths: List of file paths.
            folder_id: Optional folder ID.
            concurrent: Number of concurrent uploads.
            delete_after: Delete files after successful upload.
            
        Returns:
            List of result dictionaries.
        """
        folder_id = folder_id or self.default_folder
        delete_after = delete_after if delete_after is not None else getattr(config, 'DELETE_AFTER_UPLOAD', False)
        semaphore = asyncio.Semaphore(concurrent)
        
        async def _upload_one(fp: str) -> Dict[str, Any]:
            async with semaphore:
                url = await self.upload(fp, folder_id, delete_after=delete_after)
                return {
                    'file': os.path.basename(fp),
                    'status': 'success' if url else 'failed',
                    'url': url or ''
                }
        
        logger.info(f"Batch upload: {len(file_paths)} files, concurrency={concurrent}")
        tasks = [_upload_one(fp) for fp in file_paths]
        results = await asyncio.gather(*tasks)
        
        success = sum(1 for r in results if r['status'] == 'success')
        logger.info(f"Batch upload complete: {success}/{len(file_paths)} successful")
        
        return list(results)
    
    async def list_folders(self) -> List[Dict[str, Any]]:
        """
        List all folders in Streamtape.
        
        Returns:
            List of folder dictionaries.
        """
        async with aiohttp.ClientSession() as session:
            api_url = (
                f"{self.BASE_URL}/file/listfolder"
                f"?login={self.login}&key={self.key}"
            )
            try:
                async with session.get(api_url) as resp:
                    data = await resp.json()
                    if data.get('status') == 200:
                        return data.get('result', {}).get('folders', [])
                    logger.error(f"List folders failed: {data.get('msg')}")
                    return []
            except Exception as e:
                logger.error(f"List folders error: {e}")
                return []
    
    async def create_folder(
        self,
        name: str,
        parent_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create a new folder in Streamtape.
        
        Args:
            name: Folder name.
            parent_id: Optional parent folder ID.
            
        Returns:
            Folder ID if successful, None otherwise.
        """
        async with aiohttp.ClientSession() as session:
            api_url = (
                f"{self.BASE_URL}/file/createfolder"
                f"?login={self.login}&key={self.key}"
                f"&name={name}"
            )
            if parent_id:
                api_url += f"&folder={parent_id}"
            
            try:
                async with session.get(api_url) as resp:
                    data = await resp.json()
                    if data.get('status') == 200:
                        return data['result']['folderid']
                    logger.error(f"Create folder failed: {data.get('msg')}")
                    return None
            except Exception as e:
                logger.error(f"Create folder error: {e}")
                return None


# =============================================================================
# Module-level functions for backward compatibility
# =============================================================================

_uploader = None


def get_uploader() -> StreamtapeUploader:
    """Get or create the singleton uploader instance."""
    global _uploader
    if _uploader is None:
        _uploader = StreamtapeUploader()
    return _uploader


async def upload_to_streamtape(
    file_path: str,
    folder_id: Optional[str] = None,
) -> Optional[str]:
    """Upload single file to Streamtape (backward compatibility)."""
    return await get_uploader().upload(file_path, folder_id)


async def upload_multiple(
    file_paths: List[str],
    folder_id: Optional[str] = None,
    concurrent: int = 3,
) -> List[Dict[str, Any]]:
    """Upload multiple files (backward compatibility)."""
    return await get_uploader().upload_multiple(file_paths, folder_id, concurrent)


async def list_folders() -> List[Dict[str, Any]]:
    """List all folders (backward compatibility)."""
    return await get_uploader().list_folders()


async def create_folder(
    name: str,
    parent_id: Optional[str] = None,
) -> Optional[str]:
    """Create folder (backward compatibility)."""
    return await get_uploader().create_folder(name, parent_id)

"""
Video Downloader - Download HLS/m3u8 streams using ffmpeg.

This module provides functionality for downloading video streams from m3u8 URLs
using ffmpeg as the underlying tool.
"""

import subprocess
import os
import logging
from typing import Optional, Dict, Any

import config

logger = logging.getLogger(__name__)


class VideoDownloader:
    """
    Handles video download operations from HLS/m3u8 streams.
    
    Attributes:
        default_output: Default output file path.
        default_referer: Default HTTP referer header.
        timeout: Timeout for ffmpeg operations in seconds.
    """
    
    def __init__(
        self,
        default_output: Optional[str] = None,
        default_referer: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        """
        Initialize the video downloader.
        
        Args:
            default_output: Default output file path.
            default_referer: Default HTTP referer header.
            timeout: Timeout for ffmpeg in seconds.
        """
        self.default_output = default_output or getattr(config, 'DEFAULT_OUTPUT', 'video.mp4')
        self.default_referer = default_referer or getattr(config, 'DEFAULT_REFERER', 'https://google.com')
        self.timeout = timeout or getattr(config, 'FFMPEG_TIMEOUT', 1800)
    
    def pick_best_url(self, m3u8_urls: list) -> Optional[str]:
        """
        Select the best URL from a list of m3u8 URLs.
        
        Prioritizes index.m3u8 and master.m3u8 files.
        
        Args:
            m3u8_urls: List of m3u8 URLs.
            
        Returns:
            Best URL or None if list is empty.
        """
        if not m3u8_urls:
            return None
        
        # Priority: index > master > first available
        for keyword in ['index.m3u8', 'master.m3u8']:
            for url in m3u8_urls:
                if keyword in url.lower():
                    return url
        
        return m3u8_urls[0]
    
    def download(
        self,
        m3u8_url: str,
        output_file: Optional[str] = None,
        referer: Optional[str] = None,
    ) -> bool:
        """
        Download HLS stream using ffmpeg.
        
        Args:
            m3u8_url: The m3u8 URL to download.
            output_file: Output file path (uses default if not provided).
            referer: HTTP referer header.
            
        Returns:
            True if download succeeded, False otherwise.
        """
        output_file = output_file or self.default_output
        referer = referer or self.default_referer
        
        logger.debug(f"Downloading: {m3u8_url[:60]}...")
        logger.debug(f"Output: {output_file}")
        
        cmd = self._build_ffmpeg_command(m3u8_url, output_file, referer)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            
            return self._handle_result(result, output_file)
            
        except subprocess.TimeoutExpired:
            logger.error(f"Download timeout after {self.timeout}s")
            return False
        except Exception as e:
            logger.error(f"Download error: {e}")
            return False
    
    def _build_ffmpeg_command(
        self,
        m3u8_url: str,
        output_file: str,
        referer: str,
    ) -> list:
        """
        Build ffmpeg command with appropriate headers.
        
        Args:
            m3u8_url: Source URL.
            output_file: Output file path.
            referer: HTTP referer.
            
        Returns:
            List of command arguments.
        """
        cmd = ['ffmpeg', '-y']
        
        if referer:
            cmd += ['-headers', f'Referer: {referer}\r\n']
        
        cmd += [
            '-i', m3u8_url,
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-movflags', '+faststart',
            output_file,
        ]
        
        return cmd
    
    def _handle_result(
        self,
        result: subprocess.CompletedProcess,
        output_file: str,
    ) -> bool:
        """
        Handle ffmpeg result and return success status.
        
        Args:
            result: CompletedProcess from ffmpeg.
            output_file: Path to output file.
            
        Returns:
            True if file exists, False otherwise.
        """
        if os.path.exists(output_file):
            size_mb = os.path.getsize(output_file) / (1024 * 1024)
            logger.info(f"Downloaded: {output_file} ({size_mb:.1f} MB)")
            return True
        else:
            logger.error(f"Download failed: {result.stderr[:500] if result.stderr else 'Unknown error'}")
            return False
    
    def download_direct(
        self,
        m3u8_url: str,
        output_file: str = 'video.mp4',
        referer: Optional[str] = None,
    ) -> bool:
        """
        Convenience method for direct download without scrape.
        
        Args:
            m3u8_url: The m3u8 URL to download.
            output_file: Output file path.
            referer: HTTP referer header.
            
        Returns:
            True if download succeeded, False otherwise.
        """
        logger.debug(f"Direct download: {m3u8_url[:60]}")
        return self.download(m3u8_url, output_file, referer)


# =============================================================================
# Module-level functions for backward compatibility
# =============================================================================

# Singleton instance
_downloader = None


def get_downloader() -> VideoDownloader:
    """Get or create the singleton downloader instance."""
    global _downloader
    if _downloader is None:
        _downloader = VideoDownloader()
    return _downloader


def pick_best_url(m3u8_urls: list) -> Optional[str]:
    """Select best URL from m3u8 list (backward compatibility)."""
    return get_downloader().pick_best_url(m3u8_urls)


def download_video(
    m3u8_url: str,
    output_file: Optional[str] = None,
    referer: Optional[str] = None,
) -> bool:
    """
    Download video from m3u8 URL (backward compatibility).
    
    Args:
        m3u8_url: The m3u8 URL to download.
        output_file: Output file path.
        referer: HTTP referer header.
        
    Returns:
        True if download succeeded, False otherwise.
    """
    return get_downloader().download(m3u8_url, output_file, referer)


def download_direct(
    m3u8_url: str,
    output_file: str = 'video.mp4',
    referer: Optional[str] = None,
) -> bool:
    """Direct download shortcut (backward compatibility)."""
    return get_downloader().download_direct(m3u8_url, output_file, referer)

"""
Custom exceptions for the video scraper package.
"""


class ScraperError(Exception):
    """Base exception for all scraper-related errors."""
    pass


class BrowserError(ScraperError):
    """Raised when browser operations fail."""
    pass


class DownloadError(ScraperError):
    """Raised when video download fails."""
    pass


class UploadError(ScraperError):
    """Raised when video upload fails."""
    pass


class ValidationError(ScraperError):
    """Raised when input validation fails."""
    pass


class NetworkError(ScraperError):
    """Raised when network operations fail."""
    pass


class ParseError(ScraperError):
    """Raised when parsing page content fails."""
    pass

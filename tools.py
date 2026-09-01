import ipaddress
import re
from urllib.parse import urlparse
import os
import yt_dlp

from logger import setup_logger

logger = setup_logger(__name__)


class _YTDLPLogger:
    """Routes yt-dlp output through the bot's logging system."""

    def debug(self, msg):
        if msg.startswith('[debug] '):
            logger.debug(msg)
        else:
            logger.info(msg)

    def info(self, msg):
        logger.info(msg)

    def warning(self, msg):
        logger.warning(msg)

    def error(self, msg):
        logger.error(msg)


def is_valid_url(url: str, allow_localhost: bool = False) -> bool:
    """
    Secure URL validator that prevents code injection and malicious URLs.

    Args:
        url: String to validate
        allow_localhost: Whether to allow localhost/127.0.0.1 URLs

    Returns:
        True if valid and safe URL, False otherwise
    """
    if not url or not isinstance(url, str):
        return False

    url = url.strip()

    # Length check - prevent extremely long URLs
    if len(url) > 2048:
        return False

    # Must start with http:// or https:// only
    if not (url.startswith('http://') or url.startswith('https://')):
        return False

    # Block dangerous characters that could be used for injection.
    # Note: '&' is intentionally excluded — it is a standard query-param
    # separator used in YouTube/YouTube Music URLs (e.g. ?v=X&list=Y).
    dangerous_chars = [
        '\n', '\r',   # Newlines
        '\x00',       # Null bytes
        '<', '>',     # HTML tags
        '`',          # Command execution
        '|', ';',     # Command chaining / shell separator
        '$', '(',     # Variable expansion
    ]

    for char in dangerous_chars:
        if char in url:
            return False

    # Block javascript: data: file: and other dangerous protocols in the URL
    dangerous_protocols = ['javascript:', 'data:', 'file:', 'vbscript:', 'about:']
    url_lower = url.lower()
    for protocol in dangerous_protocols:
        if protocol in url_lower:
            return False

    try:
        parsed = urlparse(url)

        # Verify scheme is only http or https
        if parsed.scheme not in ['http', 'https']:
            return False

        # Must have a netloc (domain)
        if not parsed.netloc:
            return False

        # Block localhost, private and reserved IP addresses unless explicitly
        # allowed. Handles IPv4 literals, CIDR-style hostnames and IPv6 literals
        # (bracketed in the netloc, e.g. http://[::1]:8000/).
        hostname = _extract_hostname(parsed.netloc)
        if hostname is None:
            return False
        hostname = hostname.lower()

        if not allow_localhost:
            try:
                if ipaddress.ip_address(hostname).is_private:
                    return False
            except ValueError:
                pass  # Not an IP literal; validated as a domain below
            if hostname == 'localhost':
                return False

        # Domain validation - must contain at least one dot
        if '.' not in hostname and hostname != 'localhost':
            return False

        # Validate domain format with regex
        domain_pattern = re.compile(
            r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*'
            r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$'
        )

        if not domain_pattern.match(hostname):
            return False

        return True

    except Exception:
        return False


def _extract_hostname(netloc: str):
    """Return the bare hostname from a parsed URL's netloc.

    Strips userinfo, port and IPv6 brackets: 'user@host:8080' -> 'host',
    '[::1]:80' -> '::1'. Returns None if the netloc is unusable.
    """
    host = netloc.rsplit('@', 1)[-1]
    if host.startswith('[') and ']' in host:
        host = host[1:host.index(']')]
    else:
        host = host.rsplit(':', 1)[0]
    return host or None


def to_snake_case(text: str) -> str:
    """Convert text to snake_case"""
    text = text.replace(' ', '_').replace('-', '_')
    text = re.sub(r'[^a-zA-Z0-9_]', '', text)
    text = text.lower()
    text = re.sub(r'_+', '_', text)
    text = text.strip('_')
    return text if text else 'common'


def download_data(url: str, download_path: str, music_folder: str, progress_callback=None) -> bool:
    """
    Download audio from a YouTube / YouTube Music URL (single track or playlist)
    using yt-dlp's Python API. Saves as mp3 at 320 kbps.

    progress_callback(status, title, pct, speed, eta, playlist_index, playlist_count)
    is called from the yt-dlp download thread on each progress event. Callers must
    handle thread-safety themselves (e.g. asyncio.run_coroutine_threadsafe).

    Returns True on success, False on any error.
    """
    final_path = os.path.join(download_path, music_folder)
    try:
        os.makedirs(final_path, exist_ok=True)

        files_before = set(os.listdir(final_path))

        def _progress_hook(d):
            if progress_callback is None:
                return
            try:
                info = d.get('info_dict', {})
                title = info.get('title') or d.get('filename', 'Unknown')
                playlist_index = info.get('playlist_index')
                playlist_count = info.get('playlist_count')
                status = d['status']

                if status == 'downloading':
                    downloaded = d.get('downloaded_bytes', 0)
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    pct = (downloaded / total * 100) if total else 0.0
                    speed = d.get('_speed_str', '?')
                    eta = d.get('_eta_str', '?')
                elif status == 'finished':
                    pct = 100.0
                    speed = None
                    eta = None
                else:
                    return

                progress_callback(
                    status=status,
                    title=title,
                    pct=pct,
                    speed=speed,
                    eta=eta,
                    playlist_index=playlist_index,
                    playlist_count=playlist_count,
                )
            except Exception:
                pass  # Never let a progress error abort the download

        ydl_opts = {
            # Best available audio; fall back to best combined stream
            'format': 'bestaudio/best',
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320',
                },
                {
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                },
            ],
            'postprocessor_args': ['-id3v2_version', '3'],
            'outtmpl': os.path.join(final_path, '%(title)s.%(ext)s'),
            # Route yt-dlp log output through the bot logger
            'logger': _YTDLPLogger(),
            # For playlists: skip individual failures rather than aborting
            'ignoreerrors': True,
            # Retries on transient network errors
            'retries': 5,
            'fragment_retries': 5,
            'progress_hooks': [_progress_hook],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ret = ydl.download([url])

        files_after = set(os.listdir(final_path))
        new_files = files_after - files_before
        # With ignoreerrors=True, yt-dlp returns non-zero if any individual
        # track in a playlist fails, even when the rest downloaded successfully.
        # Treat as success if new files were created, or if yt-dlp itself
        # reported clean success (covers single tracks already present).
        return len(new_files) > 0 or ret == 0

    except yt_dlp.utils.DownloadError as e:
        logger.error(f"yt-dlp DownloadError: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during download: {e}")
        return False

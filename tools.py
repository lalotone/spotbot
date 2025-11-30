import re
from urllib.parse import urlparse
import os
import subprocess

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

    # Block dangerous characters that could be used for injection
    dangerous_chars = [
        '\n', '\r',  # Newlines
        '\x00',  # Null bytes
        '<', '>',  # HTML tags
        '`',  # Command execution
        '|', ';', '&',  # Command chaining
        '$', '(',  # Variable expansion
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

        # Block localhost/private IPs unless explicitly allowed
        if not allow_localhost:
            blocked_hosts = [
                'localhost',
                '127.0.0.1',
                '0.0.0.0',
                '::1',
            ]
            if parsed.netloc.lower().split(':')[0] in blocked_hosts:
                return False

            # Block private IP ranges
            if parsed.netloc.startswith('10.') or \
                    parsed.netloc.startswith('192.168.') or \
                    parsed.netloc.startswith('172.'):
                return False

        # Domain validation - must contain at least one dot
        hostname = parsed.netloc.split(':')[0]  # Remove port if present
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


def to_snake_case(text: str) -> str:
    """Convert text to snake_case"""
    # Replace spaces and hyphens with underscores
    text = text.replace(' ', '_').replace('-', '_')
    # Remove special characters
    text = re.sub(r'[^a-zA-Z0-9_]', '', text)
    # Convert to lowercase
    text = text.lower()
    # Replace multiple underscores with single underscore
    text = re.sub(r'_+', '_', text)
    # Remove leading/trailing underscores
    text = text.strip('_')

    return text if text else 'common'

def download_data(url, download_path, music_folder):
    final_path = os.path.join(download_path, music_folder)
    try:
        if not os.path.isdir(final_path):
            os.mkdir(final_path)
        # Use spotdl to download
        command = [
            'spotdl',
            '--output', final_path,
            '--format', 'mp3',  # Output format
            '--bitrate', '320k',
            url
        ]

        print(f"Running command: {command}")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout for playlists
        )

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print(f"Download timeout for URL: {url}")
        return False
    except Exception as e:
        print(f"Download error: {e}")
        return False
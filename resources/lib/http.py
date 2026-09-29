"""Shared HTTP client with bounded timeouts and retries that stop on Kodi shutdown."""

import json
import ssl
import time
import zlib
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPSHandler, Request, build_opener

import xbmc

USER_AGENT = 'weather.nws/1.0 (+https://github.com/MikeSiLVO/weather.nws)'

DEFAULT_TIMEOUT = 8
DEFAULT_RETRIES = 1
RETRY_DELAY = 2

monitor = xbmc.Monitor()
_opener = build_opener(HTTPSHandler(context=ssl.create_default_context()))
_deadline = None


class Aborted(Exception):
    """Kodi shutdown signal, raised so callers stop without logging an error."""


def aborted():
    """Whether Kodi has requested shutdown."""
    return monitor.abortRequested()


def wait(seconds):
    """Wait, raising Aborted as soon as Kodi requests shutdown."""
    if monitor.waitForAbort(seconds):
        raise Aborted()


def set_deadline(seconds):
    """Limit every later request to finish within this many seconds from now."""
    global _deadline
    _deadline = time.monotonic() + seconds


def get_json(url, timeout=DEFAULT_TIMEOUT, retries=DEFAULT_RETRIES, accept=None):
    """Get a URL as parsed JSON, retrying 5xx and network errors, then raising the last one."""
    return json.loads(get_bytes(url, timeout, retries, accept))


def get_bytes(url, timeout=DEFAULT_TIMEOUT, retries=DEFAULT_RETRIES, accept=None,
              retry_on_status=(500, 502, 503, 504), form=None):
    """Get a URL's raw body, posting form fields when given, retrying 5xx and network errors."""
    if aborted():
        raise Aborted()

    headers = {'User-Agent': USER_AGENT, 'Accept-Encoding': 'gzip'}
    if accept:
        headers['Accept'] = accept
    data = urlencode(form).encode() if form else None

    last_exc: Exception = RuntimeError('unreachable')
    for attempt in range(retries + 1):
        remaining = _remaining()
        try:
            with _opener.open(Request(url, headers=headers, data=data),
                              timeout=min(timeout, remaining)) as resp:
                body = resp.read()
                if resp.headers.get('Content-Encoding') == 'gzip':
                    body = zlib.decompress(body, 31)
                return body
        except HTTPError as e:
            last_exc = e
            if e.code not in retry_on_status:
                raise
        except (URLError, OSError) as e:
            last_exc = e

        if attempt < retries and _remaining() > RETRY_DELAY + 1:
            wait(RETRY_DELAY)
        else:
            break

    raise last_exc


def _remaining():
    """Seconds left before the deadline, raising URLError once it has passed."""
    if _deadline is None:
        return float('inf')
    left = _deadline - time.monotonic()
    if left <= 0:
        raise URLError('weather fetch time limit reached')
    return left

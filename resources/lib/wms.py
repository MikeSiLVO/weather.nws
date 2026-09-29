"""WMS image frames by time, spliced into looping GIFs without an image library."""

import re
from datetime import datetime
from urllib.parse import urlencode

from . import http

WIDTH, HEIGHT = 1280, 720


def frame_times(caps_url, layer, count, step):
    """Pick evenly spaced recent frame times for a layer, oldest first, from its capabilities."""
    caps = http.get_bytes(caps_url).decode('utf-8', 'replace')
    block = re.search(rf'<Name>(?:\w+:)?{layer}</Name>(.*?)</Layer>', caps, re.S)
    match = re.search(r'<Dimension name="time"[^>]*>([^<]+)<', block.group(1) if block else caps)
    if not match:
        raise ValueError(f'{layer} capabilities list no times')

    picked, last = [], None
    for value in reversed(match.group(1).strip().split(',')):
        ts = datetime.fromisoformat(value.strip().replace('Z', '+00:00')).timestamp()
        if last is None or last - ts >= step:
            picked.append(value.strip())
            last = ts
        if len(picked) == count:
            break
    return list(reversed(picked))


def get_frame(url, layers, styles, box, when, transparent=True):
    """Get one map frame as a parsed GIF."""
    query = urlencode({
        'service': 'WMS', 'version': '1.3.0', 'request': 'GetMap', 'layers': layers,
        'styles': styles, 'crs': 'EPSG:3857', 'bbox': box, 'width': WIDTH, 'height': HEIGHT,
        'format': 'image/gif', 'transparent': 'true' if transparent else 'false', 'time': when,
    })
    return parse_gif(http.get_bytes(f'{url}?{query}', retries=0))


def parse_gif(data):
    """Parse a single-frame GIF into its color table flags, table, transparency and image block."""
    if data[:6] not in (b'GIF87a', b'GIF89a'):
        raise ValueError('not a GIF')
    packed = data[10]
    i, table = 13, b''
    if packed & 0x80:
        size = 3 * 2 ** ((packed & 7) + 1)
        table, i = data[i:i + size], i + size

    transparent = None
    while i < len(data):
        block = data[i]
        if block == 0x21:
            if data[i + 1] == 0xF9 and data[i + 3] & 1:
                transparent = data[i + 6]
            i += 2
            while data[i]:
                i += data[i] + 1
            i += 1
        elif block == 0x2C:
            start = i
            i += 10
            if data[i - 1] & 0x80:
                i += 3 * 2 ** ((data[i - 1] & 7) + 1)
            i += 1
            while data[i]:
                i += data[i] + 1
            return packed, table, transparent, data[start:i + 1]
        else:
            raise ValueError(f'unexpected GIF block {block:#x}')
    raise ValueError('GIF has no image')


def splice(frames, delay=50, hold=200):
    """Join parsed GIF frames into one looping GIF, holding the newest frame longer."""
    out = bytearray(b'GIF89a' + WIDTH.to_bytes(2, 'little') + HEIGHT.to_bytes(2, 'little'))
    out += bytes([0x70, 0, 0])
    out += b'\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00'
    for n, (packed, table, transparent, image) in enumerate(frames):
        wait = hold if n == len(frames) - 1 else delay
        # disposal 2 clears each frame so transparent areas do not keep the last one
        flags = (2 << 2) | (1 if transparent is not None else 0)
        out += bytes([0x21, 0xF9, 4, flags]) + wait.to_bytes(2, 'little')
        out += bytes([transparent or 0, 0])
        descriptor, body = bytearray(image[:10]), image[10:]
        if not descriptor[9] & 0x80:
            descriptor[9] = (descriptor[9] & 0x78) | 0x80 | (packed & 7)
            body = table + body
        out += descriptor + body
    out += b'\x3b'
    return bytes(out)

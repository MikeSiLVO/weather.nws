"""USGS base maps and overlays, flattened into one PNG without an image library."""

import json
import re
import struct
import threading
import zlib
from urllib.error import URLError
from urllib.parse import urlencode

from . import http
from .wms import HEIGHT, WIDTH

USGS_HOSTS = ('carto.nationalmap.gov', 'cartowfs.nationalmap.gov')
TIMEOUT = 20
FALLBACK_WMS = 'https://opengeo.ncep.noaa.gov/geoserver/ows'
_NONZERO = re.compile(rb'[^\x00]+')

# consolidated city-counties carry legal names like "Augusta-Richmond County consolidated ..."
LABEL_EXPRESSION = (
    "var n = Replace($feature.PLACE_NAME, ' (balance)', ''); "
    "var cuts = [' metropolitan government', ' unified government', "
    "' consolidated government', ' County', ' city']; "
    "for (var k in cuts) { var i = Find(cuts[k], n); if (i > 0) { n = Left(n, i); } } "
    "return n;"
)

# base is drawn under radar; light sits over satellite, dark over the temperature map
STYLES = {
    'base': {'background': True, 'state': [40, 40, 40, 255], 'county': [160, 160, 160, 255],
             'roads': True, 'text': [30, 30, 30, 255], 'halo': [255, 255, 255, 255]},
    'light': {'background': False, 'state': [255, 255, 255, 230], 'county': None,
              'roads': False, 'text': [255, 255, 255, 255], 'halo': [0, 0, 0, 255]},
    'dark': {'background': False, 'state': [40, 40, 40, 255], 'county': None,
             'roads': False, 'text': [30, 30, 30, 255], 'halo': [255, 255, 255, 255]},
}


def export(url, box, layers=None, dynamic=None, transparent=True, timeout=TIMEOUT):
    """Export an ArcGIS map service image for a bbox, posting when styles are overridden."""
    form = {'bbox': box, 'bboxSR': 3857, 'imageSR': 3857, 'size': f'{WIDTH},{HEIGHT}',
            'format': 'png32', 'transparent': 'true' if transparent else 'false', 'f': 'image'}
    if layers:
        form['layers'] = layers
    if dynamic:
        form['dynamicLayers'] = json.dumps(dynamic)
        return http.get_bytes(f'{url}/export', timeout=timeout, form=form)
    return http.get_bytes(f'{url}/export?{urlencode(form)}', timeout=timeout)


def build(path, box, min_population, counties, style='base'):
    """Build a map at path in a style, returning False when a layer is missing and needs rebuild."""
    passes = _passes(min_population, counties, STYLES[style])
    images: list = [None] * len(passes)

    def fetch(index, service, dynamic):
        try:
            images[index] = _usgs(service, box, dynamic)
        except (URLError, OSError, ValueError):
            pass

    threads = [threading.Thread(target=fetch, args=(i, service, dynamic))
               for i, (service, dynamic) in enumerate(passes)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if not any(images):
        if style == 'base':
            _write_fallback(path, box)
        return False
    if len(images) == 1 and not STYLES[style]['background']:
        with open(path, 'wb') as f:
            f.write(images[0])
        return True

    fill = b'\xff\xff\xff\xff' if STYLES[style]['background'] else b'\x00\x00\x00\x00'
    rows = [bytearray(fill * WIDTH) for _ in range(HEIGHT)]
    for data in images:
        if data is not None:
            _composite(rows, _read_rgba(data))
    _write_rgba(path, rows)
    return all(images)


def _usgs(service, box, dynamic):
    """Export one USGS layer image, trying each host in turn."""
    last_exc: Exception = RuntimeError('no hosts')
    for host in USGS_HOSTS:
        url = f'https://{host}/arcgis/rest/services/{service}/MapServer'
        try:
            return export(url, box, dynamic=dynamic)
        except (URLError, OSError) as e:
            last_exc = e
    raise last_exc


def _outline(color, width):
    """Renderer drawing polygon outlines only."""
    return {'type': 'simple', 'symbol': {
        'type': 'esriSFS', 'style': 'esriSFSNull',
        'outline': {'type': 'esriSLS', 'style': 'esriSLSSolid', 'color': color, 'width': width}}}


def _label_layer(layer_id, min_population, style):
    """Dynamic layer labeling places above a population, one bold label per place."""
    return {
        'id': layer_id, 'source': {'type': 'mapLayer', 'mapLayerId': layer_id},
        'definitionExpression': f'POPULATION >= {min_population}',
        'drawingInfo': {
            'renderer': _outline([0, 0, 0, 0], 0),
            'showLabels': True,
            'labelingInfo': [{
                'labelExpressionInfo': {'expression': LABEL_EXPRESSION},
                'labelPlacement': 'esriServerPolygonPlacementAlwaysHorizontal',
                'removeDuplicates': 'all', 'multiPart': 'labelLargest',
                'deconflictionStrategy': 'dynamic', 'minScale': 0, 'maxScale': 0,
                'symbol': {'type': 'esriTS', 'color': style['text'],
                           'haloColor': style['halo'], 'haloSize': 2,
                           'font': {'family': 'Arial', 'size': 13, 'weight': 'bold'}},
            }],
        },
    }


def _passes(min_population, counties, style):
    """Service and dynamic layers for each pass, bottom pass first, top layer first in a pass."""
    lines = [{'id': 21, 'source': {'type': 'mapLayer', 'mapLayerId': 21},
              'drawingInfo': {'renderer': _outline(style['state'], 1.8)}}]
    if counties and style['county']:
        lines.append({'id': 23, 'source': {'type': 'mapLayer', 'mapLayerId': 23},
                      'drawingInfo': {'renderer': _outline(style['county'], 0.6)}})
    labels = [_label_layer(24, min_population, style), _label_layer(25, min_population, style)]
    if not style['roads']:
        return [('govunits', labels + lines)]
    roads = [{
        'id': 9, 'source': {'type': 'mapLayer', 'mapLayerId': 9},
        'definitionExpression': "INTERSTATE <> ' '",
        'drawingInfo': {'renderer': {'type': 'simple', 'symbol': {
            'type': 'esriSLS', 'style': 'esriSLSSolid',
            'color': [200, 70, 50, 255], 'width': 1.6}}},
    }]
    return [('govunits', lines), ('transportation', roads), ('govunits', labels)]


def _write_fallback(path, box):
    """Write NWS state lines on white, for when USGS is unreachable."""
    query = urlencode({
        'service': 'WMS', 'version': '1.3.0', 'request': 'GetMap', 'layers': 'geopolitical',
        'styles': '', 'crs': 'EPSG:3857', 'bbox': box, 'width': WIDTH, 'height': HEIGHT,
        'format': 'image/png', 'transparent': 'false', 'bgcolor': '0xFFFFFF',
    })
    data = http.get_bytes(f'{FALLBACK_WMS}?{query}')
    with open(path, 'wb') as f:
        f.write(data)


def _read_rgba(data):
    """Decode an 8-bit RGBA PNG of the map size into rows of bytes."""
    pos, idat = 8, []
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if kind == b'IHDR':
            w, h, depth, color_type = struct.unpack('>IIBB', body[:10])
            if (w, h, depth, color_type) != (WIDTH, HEIGHT, 8, 6):
                raise ValueError(f'unexpected PNG {w}x{h} depth {depth} type {color_type}')
        elif kind == b'IDAT':
            idat.append(body)
        pos += 12 + length

    raw = zlib.decompress(b''.join(idat))
    stride = WIDTH * 4
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(HEIGHT):
        kind = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        _unfilter(kind, line, prev)
        rows.append(line)
        prev = line
    return rows


def _unfilter(kind, line, prev):
    """Undo one PNG scanline filter in place."""
    if kind == 1:
        for x in range(4, len(line)):
            line[x] = (line[x] + line[x - 4]) & 255
    elif kind == 2:
        for x in range(len(line)):
            line[x] = (line[x] + prev[x]) & 255
    elif kind == 3:
        for x in range(len(line)):
            left = line[x - 4] if x >= 4 else 0
            line[x] = (line[x] + ((left + prev[x]) >> 1)) & 255
    elif kind == 4:
        line[:] = _paeth(line, prev)


def _paeth(filtered, prev):
    """Undo the Paeth filter on one row, skipping runs where every input byte is zero."""
    n = len(filtered)
    above = int.from_bytes(prev, 'big')
    # a pixel whose own, upper and upper-left bytes are zero decodes to its left neighbor
    mask = (int.from_bytes(filtered, 'big') | above | above >> 32).to_bytes(n, 'big')
    line = bytearray(n)
    x = 0
    for run in _NONZERO.finditer(mask):
        x = max(x, run.start())
        end = run.end()
        while x < n and (x < end or any(line[max(x - 4, 0):x])):
            a = line[x - 4] if x >= 4 else 0
            b = prev[x]
            c = prev[x - 4] if x >= 4 else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            line[x] = (filtered[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
            x += 1
    return line


def _composite(rows, layer):
    """Blend RGBA layer rows over RGBA rows, skipping fully transparent pixels."""
    for y, line in enumerate(layer):
        out = rows[y]
        alphas = line[3::4]
        if not any(alphas):
            continue
        for x, a in enumerate(alphas):
            if not a:
                continue
            s = x * 4
            if a == 255:
                out[s:s + 4] = line[s:s + 4]
                continue
            below = out[s + 3] * (255 - a) // 255
            total = a + below
            for c in range(3):
                out[s + c] = (line[s + c] * a + out[s + c] * below) // total
            out[s + 3] = total


def _write_rgba(path, rows):
    """Encode RGBA rows as a PNG file."""
    def chunk(kind, body):
        return (struct.pack('>I', len(body)) + kind + body
                + struct.pack('>I', zlib.crc32(kind + body)))

    raw = b''.join(b'\x00' + bytes(row) for row in rows)
    header = struct.pack('>IIBBBBB', WIDTH, HEIGHT, 8, 6, 0, 0, 0)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
                + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))

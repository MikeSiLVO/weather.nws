"""Hazard map layers: an NHC tropical cyclone forecast, else the SPC severe weather outlook."""

import json
import threading
from urllib.error import URLError
from urllib.parse import urlencode

from . import basemap, http

NHC = ('https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/'
       'NHC_tropical_weather/MapServer')
SPC = ('https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/'
       'SPC_wx_outlks/MapServer')

# storm slots AT1 to CP5; each has points, track, cone and watches at +2 to +5
NHC_SLOTS = range(4, 369, 26)
SPC_DAY1 = 1
SPC_CATEGORIES = (2, 3, 4, 5, 6, 8)


def get_hazard(box, outlook_labels):
    """Get the tropical storm reaching the map, else a severe weather risk in it, or None."""
    checks = {}

    def check(name, func):
        try:
            checks[name] = func(box)
        except (URLError, OSError, ValueError, KeyError):
            checks[name] = None

    threads = [threading.Thread(target=check, args=item)
               for item in (('storm', _find_storm), ('risk', _severe_risk))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if checks.get('storm'):
        slot, name, kind = checks['storm']
        layers = 'show:' + ','.join(str(slot + n) for n in range(2, 6))
        return {'kind': 'storm', 'name': name, 'type': kind,
                'image': basemap.export(NHC, box, layers=layers)}
    if checks.get('risk'):
        return {'kind': 'outlook', 'image': _outlook_image(box, outlook_labels)}
    return None


def _envelope(box):
    """ArcGIS envelope geometry for a Web Mercator bbox string."""
    x0, y0, x1, y1 = (float(v) for v in box.split(','))
    return json.dumps({'xmin': x0, 'ymin': y0, 'xmax': x1, 'ymax': y1,
                       'spatialReference': {'wkid': 3857}})


def _find_storm(box):
    """Storm slot, name and type of the first forecast cone reaching the map, or None."""
    query = urlencode({
        'geometry': _envelope(box), 'geometryType': 'esriGeometryEnvelope', 'sr': 3857,
        'layers': 'all:' + ','.join(str(slot + 4) for slot in NHC_SLOTS),
        'tolerance': 0, 'mapExtent': box, 'imageDisplay': '1280,720,96',
        'returnGeometry': 'false', 'f': 'json',
    })
    for result in http.get_json(f'{NHC}/identify?{query}').get('results', []):
        attrs = result.get('attributes', {})
        return result['layerId'] - 4, attrs.get('Storm Name', ''), attrs.get('Storm Type', '')
    return None


def _severe_risk(box):
    """Whether today's SPC outlook has a marginal or higher risk anywhere on the map."""
    query = urlencode({
        'geometry': _envelope(box), 'geometryType': 'esriGeometryEnvelope', 'inSR': 3857,
        'spatialRel': 'esriSpatialRelIntersects', 'where': 'dn >= 3',
        'returnCountOnly': 'true', 'f': 'json',
    })
    return http.get_json(f'{SPC}/{SPC_DAY1}/query?{query}').get('count', 0) > 0


def _outlook_image(box, labels):
    """Render today's SPC categorical outlook with each area labeled by its risk name."""
    renderer = http.get_json(f'{SPC}/{SPC_DAY1}?f=json')['drawingInfo']['renderer']
    names = [text.replace("'", "\\'") for text in labels]
    pairs = ', '.join(f"{dn}, '{names[i]}'" for i, dn in enumerate(SPC_CATEGORIES))
    label = {
        'labelExpressionInfo': {'expression': f"Decode($feature.dn, {pairs}, '')"},
        'labelPlacement': 'esriServerPolygonPlacementAlwaysHorizontal',
        'deconflictionStrategy': 'dynamic', 'minScale': 0, 'maxScale': 0,
        'symbol': {'type': 'esriTS', 'color': [20, 20, 20, 255],
                   'haloColor': [255, 255, 255, 255], 'haloSize': 2,
                   'font': {'family': 'Arial', 'size': 13, 'weight': 'bold'}},
    }
    dynamic = [{'id': SPC_DAY1, 'source': {'type': 'mapLayer', 'mapLayerId': SPC_DAY1},
                'drawingInfo': {'renderer': renderer, 'showLabels': True,
                                'labelingInfo': [label]}}]
    return basemap.export(SPC, box, dynamic=dynamic)

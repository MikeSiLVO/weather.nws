"""Weather maps for a location: radar loops, satellite, forecast highs and hazards."""

import math
import os
import threading
import time
from urllib.error import URLError

import xbmcvfs

from . import basemap, hazards, http, radar, wms

CACHE_DIR = xbmcvfs.translatePath('special://profile/addon_data/weather.nws/maps/')
CACHE_MAX_AGE = 30 * 24 * 3600
PARTIAL_RETRY = 6 * 3600
LOOP_FRAMES = 10
LOOP_STEP = 6 * 60

NOWCOAST = 'https://nowcoast.noaa.gov/geoserver'
NDFD_TEMP = 'https://mapservices.weather.noaa.gov/raster/rest/services/NDFD/NDFD_temp/MapServer'
NDFD_MAX_TEMP_DAY1 = 124

# degrees of latitude shown, smallest labeled population, county lines
EXTENTS = {'local': (1.45, 20000, True), 'regional': (5.8, 100000, False),
           'wide': (10.0, 250000, False)}
NATIONAL_POPULATION = 750000

# layer, seconds between frames, frame count; GOES imagery stops near 50N and short of Guam
GOES = ('goes_longwave_imagery', 10 * 60, 6)
GLOBAL_MOSAIC = ('global_longwave_imagery_mosaic', 3600, 6)
GOES_MAX_LAT = 50.0

# GOES infrared brightness to color: ordinary clouds stay gray, only cold storm tops take color
ENHANCED_IR = ((0, (0, 0, 0)), (150, (150, 150, 150)), (185, (225, 225, 225)),
               (195, (80, 170, 255)), (210, (0, 90, 220)), (222, (0, 200, 80)),
               (232, (255, 230, 0)), (242, (255, 90, 0)), (250, (200, 0, 0)), (255, (255, 0, 255)))


def get_maps(lat, lon, outlook_labels):
    """Get the maps for a location in display order, each with its kind, area and layer paths."""
    region = radar.region_for(lat, lon)
    if region is None:
        return []
    os.makedirs(CACHE_DIR, exist_ok=True)

    boxes = {name: _bbox(lat, lon, span) for name, (span, _, _) in EXTENTS.items()}
    in_goes = region != 'guam' and lat + EXTENTS['regional'][0] / 2 <= GOES_MAX_LAT
    sat_layer, sat_step, sat_count = GOES if in_goes else GLOBAL_MOSAIC
    radar_layers, radar_styles = radar.layers(region)
    key = f'{lat:.3f}_{lon:.3f}'
    jobs: dict = {
        'radar': (_frames, (radar.caps_url(region), f'{region}_bref_qcd', LOOP_FRAMES,
                            LOOP_STEP, f'{radar.WMS}/ows', radar_layers, radar_styles,
                            {'local': boxes['local'], 'regional': boxes['regional']})),
        'satellite': (_frames, (f'{NOWCOAST}/satellite/{sat_layer}/ows?service=WMS'
                                '&version=1.3.0&request=GetCapabilities', sat_layer, sat_count,
                                sat_step, f'{NOWCOAST}/ows', f'satellite:{sat_layer}', '',
                                {'sat': boxes['regional']})),
        'hazard': (hazards.get_hazard, (boxes['wide'], outlook_labels)),
        'sat_overlay': (_cached, (f'overlay_{key}_regional', boxes['regional'],
                                  EXTENTS['regional'][1], False, 'light')),
    }
    for name, (_, population, counties) in EXTENTS.items():
        jobs[f'base_{name}'] = (_cached, (f'base_{key}_{name}', boxes[name], population,
                                          counties, 'base'))
    if region == 'conus':
        national = _national_bbox()
        jobs['temperature'] = (basemap.export, (NDFD_TEMP, national),
                               {'layers': f'show:{NDFD_MAX_TEMP_DAY1}', 'transparent': False})
        jobs['national_overlay'] = (_cached, ('overlay_national', national,
                                              NATIONAL_POPULATION, False, 'dark'))
    results = _run_parallel(jobs)

    stamp = int(time.time())
    maps = []
    radar_frames = results.get('radar') or {}
    for extent in ('local', 'regional'):
        loop = _save_loop(radar_frames, extent, f'radar_{extent}_{stamp}.gif')
        if loop and results.get(f'base_{extent}'):
            maps.append({'kind': f'{extent}_radar', 'area': results[f'base_{extent}'],
                         'layer': loop, 'legend': 'radar'})
    sat_frames = results.get('satellite') or {}
    if in_goes:
        sat_frames = {k: _enhance(v) if v else v for k, v in sat_frames.items()}
    satellite = _save_loop(sat_frames, 'sat', f'satellite_{stamp}.gif')
    if satellite:
        maps.append({'kind': 'satellite', 'area': satellite,
                     'layer': results.get('sat_overlay') or '',
                     'legend': 'satellite' if in_goes else ''})
    if results.get('temperature'):
        maps.append({'kind': 'temperature',
                     'area': _save(f'temperature_{stamp}.png', results['temperature']),
                     'layer': results.get('national_overlay') or '', 'legend': 'temperature'})
    hazard = results.get('hazard')
    if hazard and results.get('base_wide'):
        maps.append({'kind': hazard['kind'], 'name': hazard.get('name', ''),
                     'type': hazard.get('type', ''), 'area': results['base_wide'],
                     'layer': _save(f'hazard_{stamp}.png', hazard['image']), 'legend': ''})
    _prune(stamp)
    return maps


def _frames(caps_url, layer, count, step, url, layers, styles, boxes):
    """Get a layer's recent frames for each named box, keyed by box name and frame index."""
    times = wms.frame_times(caps_url, layer, count, step)
    return _run_parallel({f'{name}{i}': (wms.get_frame, (url, layers, styles, box, when))
                          for name, box in boxes.items() for i, when in enumerate(times)})


def _enhance(frame):
    """Recolor a grayscale infrared frame's palette so cold cloud tops stand out."""
    packed, table, transparent, image = frame
    colors = bytearray()
    for i in range(0, len(table), 3):
        gray = table[i]
        for k in range(len(ENHANCED_IR) - 1):
            (g0, c0), (g1, c1) = ENHANCED_IR[k], ENHANCED_IR[k + 1]
            if gray <= g1:
                t = (gray - g0) / (g1 - g0)
                colors += bytes(round(c0[j] + (c1[j] - c0[j]) * t) for j in range(3))
                break
    return packed, bytes(colors), transparent, image


def _bbox(lat, lon, span):
    """Web Mercator bbox centered on a location, span degrees tall and 16:9 wide."""
    half_w = span * wms.WIDTH / wms.HEIGHT / math.cos(math.radians(lat)) / 2
    x0, y0 = _mercator(lon - half_w, lat - span / 2)
    x1, y1 = _mercator(lon + half_w, lat + span / 2)
    return f'{x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}'


def _national_bbox():
    """Web Mercator bbox framing the lower 48 states at 16:9."""
    x0, y0 = _mercator(-127, 22)
    x1, y1 = _mercator(-65, 50.5)
    cx, cy, half_w = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2
    half_h = half_w * wms.HEIGHT / wms.WIDTH
    return f'{cx - half_w:.0f},{cy - half_h:.0f},{cx + half_w:.0f},{cy + half_h:.0f}'


def _mercator(lon, lat):
    """Web Mercator x and y in meters for a longitude and latitude."""
    return lon * 20037508.34 / 180, math.log(math.tan((90 + lat) * math.pi / 360)) * 6378137


def _run_parallel(jobs):
    """Run jobs on threads, returning results by name with None for failures."""
    results = {}
    errors = []

    def run(name, func, args, kwargs):
        try:
            results[name] = func(*args, **kwargs)
        except http.Aborted as e:
            errors.append(e)
        except (URLError, OSError, ValueError, KeyError):
            results[name] = None

    threads = [threading.Thread(target=run, args=(name, job[0], job[1],
                                                  job[2] if len(job) > 2 else {}))
               for name, job in jobs.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise errors[0]
    return results


def _save_loop(results, prefix, name):
    """Splice the frames that downloaded under a prefix into a loop file, or None if none did."""
    frames = [results[k] for k in sorted((k for k in results if k.startswith(prefix)
                                          and k[len(prefix):].isdigit()),
                                         key=lambda k: int(k[len(prefix):]))
              if results[k]]
    return _save(name, wms.splice(frames)) if frames else None


def _cached(key, box, population, counties, style):
    """Get a cached map path, rebuilding it when missing or incomplete and six hours old."""
    path = os.path.join(CACHE_DIR, key + '.png')
    partial = os.path.join(CACHE_DIR, key + '_partial.png')
    if os.path.exists(path):
        os.utime(path)
        return path
    if os.path.exists(partial) and time.time() - os.path.getmtime(partial) < PARTIAL_RETRY:
        return partial

    if basemap.build(path, box, population, counties, style):
        if os.path.exists(partial):
            os.remove(partial)
        return path
    if os.path.exists(path):
        os.replace(path, partial)
        return partial
    return None


def _save(name, data):
    """Save bytes to the map cache, returning the path."""
    path = os.path.join(CACHE_DIR, name)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def _prune(stamp):
    """Delete maps from earlier refreshes and cached maps unused for a month, best effort."""
    now = time.time()
    for name in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, name)
        cached = name.startswith(('base_', 'overlay_'))
        if (cached and now - os.path.getmtime(path) > CACHE_MAX_AGE) or (
                not cached and str(stamp) not in name):
            try:
                os.remove(path)
            except OSError:
                pass

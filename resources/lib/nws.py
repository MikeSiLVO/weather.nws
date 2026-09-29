"""NWS (api.weather.gov) client for forecasts, gridpoint data and alerts."""

import re
from datetime import datetime

from . import http

API_BASE = 'https://api.weather.gov'

# NWS forecast endpoints often answer slowly or with a 5xx
TIMEOUT = 10
RETRIES = 1

GRID_FIELDS = ('skyCover', 'apparentTemperature', 'quantitativePrecipitation',
               'windGust', 'visibility', 'minTemperature')
_DURATION = re.compile(r'P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$')


def _get(url):
    """Get an NWS URL as GeoJSON, with the longer NWS timeout."""
    return http.get_json(
        url,
        timeout=TIMEOUT,
        retries=RETRIES,
        accept='application/geo+json',
    )


def get_point(lat, lon):
    """Get the NWS forecast office, grid cell and nearest named place for a location."""
    data = _get(f'{API_BASE}/points/{lat},{lon}')
    props = data['properties']
    rel = props.get('relativeLocation', {}).get('properties', {})
    return {
        'wfo': props['gridId'],
        'grid_x': props['gridX'],
        'grid_y': props['gridY'],
        'city': rel.get('city', ''),
        'state': rel.get('state', ''),
    }


def get_forecast(wfo, grid_x, grid_y, imperial=False):
    """Get the 7-day forecast as day and night periods, its text in US or metric units."""
    return _get_periods(f'{API_BASE}/gridpoints/{wfo}/{grid_x},{grid_y}/forecast', imperial)


def get_forecast_hourly(wfo, grid_x, grid_y, imperial=False):
    """Get the hourly forecast periods, their text in US or metric units."""
    return _get_periods(f'{API_BASE}/gridpoints/{wfo}/{grid_x},{grid_y}/forecast/hourly', imperial)


def _get_periods(url, imperial):
    """Get forecast periods with Celsius and km/h numbers whichever units the text uses."""
    data = _get(f'{url}?units={"us" if imperial else "si"}')
    periods = data.get('properties', {}).get('periods', [])
    return [_parse_forecast_period(p) for p in periods]


def get_grid_data(wfo, grid_x, grid_y):
    """Get the raw gridpoint series used here as (start, end, value) lists in epoch seconds."""
    props = _get(f'{API_BASE}/gridpoints/{wfo}/{grid_x},{grid_y}').get('properties', {})
    series = {}
    for name in GRID_FIELDS:
        entries = []
        for item in props.get(name, {}).get('values', []):
            span = _parse_valid_time(item.get('validTime', ''))
            if span and item.get('value') is not None:
                entries.append((span[0], span[1], item['value']))
        series[name] = entries
    return series


def _parse_valid_time(value):
    """Parse an ISO interval like 2026-09-23T16:00:00+00:00/PT3H to epoch start and end."""
    start, _, duration = value.partition('/')
    match = _DURATION.match(duration)
    if not match:
        return None
    days, hours, minutes = (int(g or 0) for g in match.groups())
    begin = datetime.fromisoformat(start).timestamp()
    return begin, begin + days * 86400 + hours * 3600 + minutes * 60


def grid_value(series, ts):
    """Value of a gridpoint series at a moment, or None when it has no data then."""
    for start, end, value in series:
        if start <= ts < end:
            return value
    return None


def grid_values(series, start, end):
    """Values of a gridpoint series whose intervals begin within a time range."""
    return [value for begin, _, value in series if start <= begin < end]


def _parse_forecast_period(period):
    """Parse one NWS forecast period into a flat dict with wind speed in km/h."""
    def _val(field):
        v = period.get(field)
        return v.get('value') if isinstance(v, dict) else v

    pop_val = _val('probabilityOfPrecipitation')
    wind_speed = _parse_wind_speed(period.get('windSpeed'))
    if 'mph' in str(period.get('windSpeed', '')):
        wind_speed *= 1.609344
    temperature = _val('temperature')
    if temperature is not None and period.get('temperatureUnit') == 'F':
        temperature = (temperature - 32) / 1.8

    return {
        'name': period.get('name', ''),
        'start_time': period.get('startTime', ''),
        'is_daytime': period.get('isDaytime', True),
        'temperature': temperature,
        'wind_speed': wind_speed,
        'wind_direction': period.get('windDirection', ''),
        'icon_url': period.get('icon', ''),
        'short_forecast': period.get('shortForecast', ''),
        'detailed_forecast': period.get('detailedForecast', ''),
        'pop': pop_val if pop_val is not None else 0,
        'dewpoint': _val('dewpoint'),
        'humidity': _val('relativeHumidity'),
    }


def _parse_wind_speed(value):
    """Parse an NWS windSpeed string or value object to km/h, taking the top of a range."""
    if value is None or value == '':
        return 0
    if isinstance(value, dict):
        v = value.get('maxValue', value.get('value'))
        return float(v) if v is not None else 0
    numbers = re.findall(r'[\d.]+', str(value))
    return float(numbers[-1]) if numbers else 0


def get_alerts(lat, lon):
    """Get active weather alerts for a location, most severe first."""
    url = f'{API_BASE}/alerts/active?point={lat},{lon}&status=actual'
    data = _get(url)

    severity_order = {
        'Extreme': 0, 'Severe': 1, 'Moderate': 2, 'Minor': 3, 'Unknown': 4,
    }

    alerts = []
    for feature in data.get('features', []):
        props = feature.get('properties', {})
        alerts.append({
            'event': props.get('event', ''),
            'headline': props.get('headline', ''),
            'description': props.get('description', ''),
            'instruction': props.get('instruction', ''),
            'severity': props.get('severity', 'Unknown'),
            'urgency': props.get('urgency', 'Unknown'),
            'expires': props.get('expires', ''),
            'sender_name': props.get('senderName', ''),
        })

    alerts.sort(key=lambda a: severity_order.get(a['severity'], 99))
    return alerts


def severity(condition_code):
    """Numeric severity for a condition code (higher = worse)."""
    return _SEVERITY.get(condition_code, 0)


def parse_icon_code(icon_url):
    """Parse an NWS icon URL to its most severe condition code and the night flag."""
    if not icon_url:
        return 'na', False

    match = re.search(r'/icons/land/(day|night)/(.+?)(?:\?|$)', icon_url)
    if not match:
        return 'na', False

    is_night = match.group(1) == 'night'
    path = match.group(2)

    codes = []
    for seg in path.split('/'):
        code = seg.split(',')[0]  # ',40' is the chance of precipitation
        if code:
            codes.append(code)

    if not codes:
        return 'na', is_night
    if len(codes) == 1:
        return codes[0], is_night

    best = codes[0]
    best_sev = _SEVERITY.get(best, 0)
    for code in codes[1:]:
        sev = _SEVERITY.get(code, 0)
        if sev > best_sev:
            best, best_sev = code, sev
    return best, is_night


_SEVERITY = {
    'skc': 0, 'few': 0, 'sct': 0, 'bkn': 0, 'ovc': 1,
    'wind_skc': 1, 'wind_few': 1, 'wind_sct': 2, 'wind_bkn': 2, 'wind_ovc': 2,
    'fog': 3, 'haze': 3, 'smoke': 3, 'dust': 3,
    'hot': 4, 'cold': 4,
    'rain_showers_hi': 5, 'rain_showers': 6, 'rain': 7,
    'fzra': 8, 'rain_fzra': 8, 'snow_fzra': 8,
    'sleet': 8, 'rain_sleet': 8, 'snow_sleet': 8,
    'snow': 8, 'rain_snow': 8,
    'blizzard': 9,
    'tsra_hi': 9, 'tsra_sct': 10, 'tsra': 11,
    'tropical_storm': 12, 'hurricane': 13, 'tornado': 14,
}

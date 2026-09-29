"""Open-Meteo forecast API for UV index, sun times and the location's UTC offset."""

from datetime import datetime, timezone
from urllib.parse import urlencode

from . import http

API_URL = 'https://api.open-meteo.com/v1/forecast'
SYNODIC_MONTH = 29.530588853
NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc).timestamp()


def get_conditions(lat, lon):
    """Get the current UV index, daily UV maximum and sun times by local date, and UTC offset."""
    params = urlencode({'latitude': lat, 'longitude': lon, 'current': 'uv_index',
                        'daily': 'uv_index_max,sunrise,sunset', 'timezone': 'auto',
                        'forecast_days': 8})
    data = http.get_json(f'{API_URL}?{params}')
    daily = data.get('daily', {})
    days = daily.get('time', [])

    def by_day(field):
        values = daily.get(field, [])
        return {day: values[i] for i, day in enumerate(days) if i < len(values)}

    return {
        'utc_offset': data.get('utc_offset_seconds'),
        'current': data.get('current', {}).get('uv_index'),
        'daily': by_day('uv_index_max'),
        'sunrise': by_day('sunrise'),
        'sunset': by_day('sunset'),
    }


def uv_level(uv_index):
    """WHO scale level for a UV index, 0 for low up to 4 for extreme."""
    for level, limit in enumerate((3, 6, 8, 11)):
        if uv_index < limit:
            return level
    return 4


def moon_phase(dt):
    """Moon phase at a time, 0 for new moon through 7 for waning crescent."""
    age = (dt.timestamp() - NEW_MOON) / 86400 % SYNODIC_MONTH
    # quarters and full moon cover the day either side, crescents and gibbous the rest
    for phase, end in enumerate((1, 6.38, 8.38, 13.76, 15.76, 21.15, 23.15, 28.53)):
        if age < end:
            return phase
    return 0

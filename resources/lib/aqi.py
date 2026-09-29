"""Air quality from EPA AirNow with the user's key, else from the Open-Meteo air quality model."""

from urllib.error import URLError
from urllib.parse import urlencode

from . import http

AIRNOW_URL = 'https://www.airnowapi.org/aq/observation/current/ziplatlong/'
OPENMETEO_URL = 'https://air-quality-api.open-meteo.com/v1/air-quality'

_AIRNOW_POLLUTANTS = {'OZONE': 'O3'}
_OPENMETEO_POLLUTANTS = {'us_aqi_pm2_5': 'PM2.5', 'us_aqi_ozone': 'O3', 'us_aqi_pm10': 'PM10',
                         'us_aqi_nitrogen_dioxide': 'NO2', 'us_aqi_sulphur_dioxide': 'SO2',
                         'us_aqi_carbon_monoxide': 'CO'}
_LEVEL_LIMITS = (50, 100, 150, 200, 300)


def get_aqi(lat, lon, airnow_key=''):
    """Current AQI, level and pollutant from AirNow when a key works, else Open-Meteo, or None."""
    if airnow_key:
        try:
            return _airnow(lat, lon, airnow_key)
        except (URLError, OSError, ValueError):
            pass
    return _openmeteo(lat, lon)


def _airnow(lat, lon, key):
    """Get the worst current pollutant reading from the nearest AirNow monitors."""
    params = urlencode({'format': 'application/json', 'latitude': lat, 'longitude': lon,
                        'API_KEY': key})
    data = http.get_json(f'{AIRNOW_URL}?{params}')
    if not data or not isinstance(data, list):
        raise ValueError('AirNow returned no readings')

    worst = max(data, key=lambda x: x.get('nowcastAQI') or 0)
    pollutant = worst.get('parameterName') or ''
    value = worst.get('nowcastAQI') or 0
    return {
        'aqi': value,
        'level': aqi_level(value),
        'pollutant': _AIRNOW_POLLUTANTS.get(pollutant, pollutant),
        'source': 'AirNow',
    }


def _openmeteo(lat, lon):
    """Get the modeled current US AQI and the pollutant driving it."""
    params = urlencode({'latitude': lat, 'longitude': lon,
                        'current': ','.join(['us_aqi', *_OPENMETEO_POLLUTANTS])})
    current = http.get_json(f'{OPENMETEO_URL}?{params}').get('current', {})
    value = current.get('us_aqi')
    if value is None:
        return None

    readings = {k: current[k] for k in _OPENMETEO_POLLUTANTS if current.get(k) is not None}
    pollutant = max(readings, key=lambda k: readings[k]) if readings else ''
    return {
        'aqi': round(value),
        'level': aqi_level(value),
        'pollutant': _OPENMETEO_POLLUTANTS.get(pollutant, ''),
        'source': 'Open-Meteo',
    }


def aqi_level(value):
    """EPA category level for an AQI value, 0 for good up to 5 for hazardous."""
    for level, limit in enumerate(_LEVEL_LIMITS):
        if value <= limit:
            return level
    return 5

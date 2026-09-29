"""US geocoding, sending street addresses to the Census geocoder and the rest to Nominatim."""

import re
from urllib.parse import quote_plus

from . import http

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
CENSUS_URL = 'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress'
CENSUS_BENCHMARK = 'Public_AR_Current'


def search(query):
    """Search for US locations by ZIP, street address or place name."""
    query = query.strip()
    if not query:
        return []

    if re.match(r'^\d{5}$', query):
        return _nominatim_zip(query)

    # a leading house number marks a street address
    if re.match(r'^\d+\s+\S', query):
        results = _census_address(query)
        if results:
            return results

    return _nominatim_freeform(query)


def _census_address(query):
    """Search the Census geocoder for a street address."""
    url = (
        f'{CENSUS_URL}'
        f'?address={quote_plus(query)}'
        f'&benchmark={CENSUS_BENCHMARK}'
        f'&format=json'
    )
    data = http.get_json(url)
    matches = data.get('result', {}).get('addressMatches', [])

    results = []
    for m in matches[:5]:
        coords = m.get('coordinates', {})
        components = m.get('addressComponents', {})
        lat = coords.get('y')
        lon = coords.get('x')
        try:
            lat_str = str(round(float(lat), 4))
            lon_str = str(round(float(lon), 4))
        except (TypeError, ValueError):
            continue

        city = components.get('city', '')
        state = components.get('state', '')
        zipcode = components.get('zip', '')
        addr = m.get('matchedAddress', '')

        results.append({
            'name': addr or (f'{city}, {state}' if city and state else ''),
            'city': city,
            'state': state,
            'lat': lat_str,
            'lon': lon_str,
            'zip': zipcode,
        })
    return results


def _nominatim_zip(zipcode):
    """Search Nominatim for a US ZIP code."""
    url = (
        f'{NOMINATIM_URL}'
        f'?postalcode={zipcode}'
        f'&countrycodes=us'
        f'&format=json'
        f'&limit=5'
        f'&addressdetails=1'
    )
    return _parse_nominatim(http.get_json(url))


def _nominatim_freeform(query):
    """Search Nominatim for a US place name."""
    url = (
        f'{NOMINATIM_URL}'
        f'?q={quote_plus(query)}'
        f'&countrycodes=us'
        f'&format=json'
        f'&limit=5'
        f'&addressdetails=1'
    )
    return _parse_nominatim(http.get_json(url))


def _parse_nominatim(data):
    """Parse Nominatim results into locations, skipping entries without usable coordinates."""
    if not data or not isinstance(data, list):
        return []

    results = []
    for entry in data:
        addr = entry.get('address', {})
        lat = entry.get('lat', '')
        lon = entry.get('lon', '')
        display = entry.get('display_name', '')

        try:
            lat_str = str(round(float(lat), 4)) if lat else ''
            lon_str = str(round(float(lon), 4)) if lon else ''
        except (TypeError, ValueError):
            continue

        city = (addr.get('city') or addr.get('town') or
                addr.get('village') or addr.get('hamlet') or '')
        state = addr.get('state', '')
        postcode = addr.get('postcode', '')

        name = f'{city}, {state}' if city and state else display

        results.append({
            'name': name,
            'city': city,
            'state': state,
            'lat': lat_str,
            'lon': lon_str,
            'zip': postcode,
        })

    return results

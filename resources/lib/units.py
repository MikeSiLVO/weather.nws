"""Unit conversion and formatting in the user's Kodi region settings."""

import re

import xbmc

_YEAR = re.compile(r'%[Yy][^%]*')
# Windows and Linux spell the unpadded fields %#m and %-m
_MONTH = re.compile(r'%[-#]?m')
_DAY = re.compile(r'%[-#]?d')


def imperial():
    """Whether the user reads Fahrenheit, which also picks inches, miles and US forecast text."""
    return '°F' in xbmc.getRegion('tempunit')


def convert_temp(celsius):
    """Convert Celsius to a rounded int in the user's temperature unit, passing None through."""
    if celsius is None:
        return None
    c = float(celsius)
    if imperial():
        return round(c * 1.8 + 32)
    if xbmc.getRegion('tempunit') == 'K':
        return round(c + 273.15)
    return round(c)


def convert_speed(kmh):
    """Convert km/h to a rounded int in the user's wind speed unit, passing None through."""
    if kmh is None:
        return None
    v = float(kmh)
    unit = xbmc.getRegion('speedunit').lower()
    if unit == 'mph':
        return round(v / 1.609344)
    if unit == 'm/s':
        return round(v / 3.6)
    if unit in ('kts', 'kn', 'knots'):
        return round(v / 1.852)
    if unit == 'ft/s':
        return round(v / 1.09728)
    if unit == 'beaufort':
        return _beaufort(v)
    return round(v)


def _beaufort(kmh):
    """Beaufort force for a km/h speed."""
    cutoffs = [1, 5.5, 11.9, 19.7, 28.7, 38.8, 49.9, 61.8, 74.6, 88.1, 102.4, 117.7]
    for i, c in enumerate(cutoffs):
        if kmh < c:
            return i
    return 12


def format_pct(value):
    """Format a value as a rounded percent, or empty when missing."""
    if value is None or value == '':
        return ''
    try:
        return f'{round(float(value))}%'
    except (TypeError, ValueError):
        return ''


def format_temp(celsius):
    """Format Celsius in the user's temperature unit with its symbol."""
    if celsius is None:
        return ''
    return f'{convert_temp(celsius)}{xbmc.getRegion("tempunit")}'


def format_speed(kmh):
    """Format km/h in the user's wind speed unit with its label."""
    if kmh is None:
        return ''
    return f'{convert_speed(kmh)} {xbmc.getRegion("speedunit")}'


def format_time(dt):
    """Format a time in the user's clock format without seconds, padding the hour as they chose."""
    fmt = xbmc.getRegion('time').replace(':%S', '')
    if '%p' in fmt:
        am, _, pm = xbmc.getRegion('meridiem').partition('/')
        fmt = fmt.replace('%p', pm if dt.hour >= 12 else am)
    text = dt.strftime(fmt)
    raw = xbmc.getRegion('timeraw')
    padded = 'hh' in raw or 'HH' in raw
    if not padded and fmt.startswith(('%I', '%H')) and text.startswith('0') and text[1:2].isdigit():
        return text[1:]
    return text


def format_day(dt):
    """Format the weekday name in the user's language."""
    return xbmc.getLocalizedString(11 + dt.weekday())


def format_short_day(dt):
    """Format the abbreviated weekday name in the user's language."""
    return xbmc.getLocalizedString(41 + dt.weekday())


def format_short_date(dt):
    """Format an abbreviated weekday and date in the user's language and month and day order."""
    month = xbmc.getLocalizedString(50 + dt.month)
    region = xbmc.getRegion('dateshort')
    month_at, day_at = _MONTH.search(region), _DAY.search(region)
    if month_at and day_at and month_at.start() < day_at.start():
        return f'{format_short_day(dt)} {month} {dt.day}'
    return f'{format_short_day(dt)} {dt.day} {month}'


def format_long_date(dt):
    """Format a date in the user's language and long date format without the year."""
    fmt = _YEAR.sub('', xbmc.getRegion('datelong')).strip(', ')
    names = {'%A': format_day(dt), '%a': format_short_day(dt),
             '%B': xbmc.getLocalizedString(20 + dt.month),
             '%b': xbmc.getLocalizedString(50 + dt.month)}
    for token, name in names.items():
        fmt = fmt.replace(token, name.replace('%', '%%'))
    return dt.strftime(fmt)


def format_precip(mm):
    """Format a precipitation amount in inches or millimeters."""
    if mm is None:
        return ''
    return f'{mm / 25.4:.2f} in' if imperial() else f'{mm:.1f} mm'


def format_distance(meters):
    """Format a distance in miles or kilometers."""
    if meters is None:
        return ''
    return f'{meters / 1609.344:.1f} mi' if imperial() else f'{meters / 1000:.1f} km'

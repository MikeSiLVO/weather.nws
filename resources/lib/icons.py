"""Map NWS conditions to Kodi weather icons (Yahoo Weather codes) and short outlooks."""

NWS_TO_KODI = {
    'skc':          ('32', '31'),
    'few':          ('34', '33'),
    'sct':          ('30', '29'),
    'bkn':          ('28', '27'),
    'ovc':          ('26', '26'),

    'wind_skc':     ('32', '31'),
    'wind_few':     ('34', '33'),
    'wind_sct':     ('24', '24'),
    'wind_bkn':     ('24', '24'),
    'wind_ovc':     ('24', '24'),

    'rain':         ('12', '12'),
    'rain_showers': ('11', '11'),
    'rain_showers_hi': ('40', '40'),

    'tsra':         ('4',  '45'),
    'tsra_sct':     ('38', '47'),
    'tsra_hi':      ('37', '47'),

    'snow':         ('16', '16'),
    'rain_snow':    ('5',  '5'),
    'rain_sleet':   ('6',  '6'),
    'snow_sleet':   ('7',  '7'),
    'fzra':         ('10', '10'),
    'rain_fzra':    ('10', '10'),
    'snow_fzra':    ('10', '10'),
    'sleet':        ('18', '18'),
    'blizzard':     ('15', '15'),

    'fog':          ('20', '20'),
    'haze':         ('21', '21'),
    'smoke':        ('22', '22'),
    'dust':         ('19', '19'),

    'tornado':      ('0',  '0'),
    'hurricane':    ('2',  '2'),
    'tropical_storm': ('1', '1'),
    'hot':          ('36', '36'),
    'cold':         ('25', '25'),
}


def nws_to_kodi_icon(condition_code, is_night=False):
    """Convert NWS condition code to Kodi icon filename like '28.png'."""
    pair = NWS_TO_KODI.get(condition_code)
    if not pair:
        return 'na.png'
    idx = 1 if is_night else 0
    return f'{pair[idx]}.png'


_FORECAST_QUALIFIERS = (
    'Slight Chance ', 'Chance ', 'Likely ',
    'Isolated ', 'Scattered ', 'Numerous ',
    'Patchy ', 'Areas Of ', 'Widespread ', 'Few ',
)


def shorten_forecast(text):
    """Shorten an NWS forecast string for skins, dropping qualifiers and repeated conditions."""
    if not text:
        return ''

    parts = [p.strip() for p in text.split(' then ')]
    shortened = []
    for part in parts:
        for prefix in _FORECAST_QUALIFIERS:
            if part.startswith(prefix):
                part = part[len(prefix):]
                break

        part = part.replace('Showers And Thunderstorms', 'Thunderstorms')
        part = part.replace('Rain Showers', 'Rain')
        part = part.replace('Snow Showers', 'Snow')

        if part and part not in shortened:
            shortened.append(part)

    return ' / '.join(shortened)

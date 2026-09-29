"""Kodi weather window property setter and orchestration."""

import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import aqi, http, icons, maps, meteo, nws, units

WEATHER_WINDOW = xbmcgui.Window(12600)
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = ADDON.getAddonInfo('name')
MEDIA = os.path.join(xbmcvfs.translatePath(ADDON.getAddonInfo('path')), 'resources', 'media')

FETCH_DEADLINE = 15

# Kodi's own strings for the WHO UV scale, low to extreme
UV_LABELS = (391, 1420, 393, 1421, 1381)
AQI_LABELS = (30120, 30121, 30122, 30123, 30124, 30125)
OUTLOOK_LABELS = (30130, 30131, 30132, 30133, 30134, 30135)
MOON_LABELS = tuple(range(30140, 30148))
MAP_HEADINGS = {'local_radar': 30100, 'regional_radar': 30101, 'satellite': 30102,
                'temperature': 30103, 'outlook': 30104}
STORM_HEADINGS = {'HU': 30105, 'TS': 30106, 'TD': 30107}


def lang(string_id):
    """Localized text for an add-on or Kodi string id."""
    if string_id >= 30000:
        return ADDON.getLocalizedString(string_id)
    return xbmc.getLocalizedString(string_id)


def log(msg, level=xbmc.LOGDEBUG):
    """Log to the Kodi log, tagged with the addon id."""
    xbmc.log(f'[{ADDON_ID}] {msg}', level)


def set_property(name, value):
    """Set a weather window property, storing None as empty."""
    WEATHER_WINDOW.setProperty(name, str(value) if value is not None else '')


def main():
    """Configure a location slot for a loc argument, else fetch weather for a location index."""
    param = sys.argv[1] if len(sys.argv) > 1 else ''
    log(f'Invoked with param: {param}')

    if param.startswith('loc'):
        from . import location  # location imports this module
        location.configure(param)
    else:
        fetch_weather(param)


def fetch_weather(param):
    """Fetch and set all weather data for a location, running each source in parallel."""
    # Kodi waits on this script with no time limit and shows nothing until it exits
    http.set_deadline(FETCH_DEADLINE)
    try:
        loc_index = int(param) if param else 1
    except ValueError:
        loc_index = 1

    prefix = f'loc{loc_index}'
    name = ADDON.getSetting(prefix)
    lat = ADDON.getSetting(f'{prefix}lat')
    lon = ADDON.getSetting(f'{prefix}lon')
    wfo = ADDON.getSetting(f'{prefix}gridwfo')
    grid_x = ADDON.getSetting(f'{prefix}gridx')
    grid_y = ADDON.getSetting(f'{prefix}gridy')

    if not lat or not lon:
        log(f'Location {loc_index} not configured')
        return

    log(f'Fetching weather for location {loc_index}: {name} '
        f'({lat},{lon}) WFO:{wfo} grid:{grid_x},{grid_y}')

    set_property('WeatherProvider', ADDON_NAME)
    set_property('Current.Location', name)
    set_property('Forecast.City', name.split(',')[0].strip() if name else '')
    set_property('Forecast.Country', 'US')
    set_property('Forecast.Latitude', lat)
    set_property('Forecast.Longitude', lon)
    now = datetime.now()
    set_property('Forecast.Updated', f'{units.format_short_date(now)} {units.format_time(now)}')
    _set_location_properties()

    grid = None
    if wfo and grid_x and grid_y:
        grid = _Shared('gridpoint', _get_grid, prefix, lat, lon, wfo, int(grid_x), int(grid_y))
    conditions = _Shared('conditions', meteo.get_conditions, lat, lon)

    fetches = [
        ('current and hourly', _fetch_current_and_hourly, (wfo, grid_x, grid_y, grid)),
        ('forecast', _fetch_forecast, (wfo, grid_x, grid_y, grid, conditions)),
        ('sun and moon', _fetch_sun_moon, (prefix, conditions)),
        ('uv', _fetch_uv, (conditions, prefix)),
        ('aqi', _fetch_aqi, (lat, lon)),
        ('maps', _fetch_maps, (lat, lon)),
        ('alerts', _fetch_alerts, (lat, lon, prefix, conditions)),
    ]
    threads = [threading.Thread(target=_run_fetch, args=(label, func, *args))
               for label, func, args in fetches]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    log('Weather fetch complete')


def _run_fetch(label, func, *args):
    """Run one fetch and return its result, logging a failure so the other sources complete."""
    try:
        return func(*args)
    except http.Aborted:
        log(f'{label} fetch aborted by shutdown', xbmc.LOGINFO)
    except (URLError, OSError) as e:
        log(f'{label} fetch failed: {e}', xbmc.LOGWARNING)
    except Exception as e:
        import traceback
        log(f'{label} fetch crashed: {e}', xbmc.LOGERROR)
        log(traceback.format_exc(), xbmc.LOGERROR)
    return None


class _Shared:
    """Fetch started on its own thread so several fetches can wait on one download."""

    def __init__(self, label, func, *args):
        self._result = None
        self._thread = threading.Thread(target=self._run, args=(label, func, args))
        self._thread.start()

    def _run(self, label, func, args):
        """Run the fetch on the thread, keeping its result for get."""
        self._result = _run_fetch(label, func, *args)

    def get(self):
        """Wait for the fetch and return its result, or an empty dict when it failed."""
        self._thread.join()
        return self._result or {}


def _get_grid(prefix, lat, lon, wfo, grid_x, grid_y):
    """Get gridpoint data, re-resolving and saving the grid cell when NWS answers 404."""
    try:
        return nws.get_grid_data(wfo, grid_x, grid_y)
    except HTTPError as e:
        if e.code != 404:
            raise
    point = nws.get_point(lat, lon)
    ADDON.setSetting(f'{prefix}gridwfo', point['wfo'])
    ADDON.setSetting(f'{prefix}gridx', str(point['grid_x']))
    ADDON.setSetting(f'{prefix}gridy', str(point['grid_y']))
    log(f'NWS grid moved from {wfo} {grid_x},{grid_y} to '
        f'{point["wfo"]} {point["grid_x"]},{point["grid_y"]}', xbmc.LOGWARNING)
    return nws.get_grid_data(point['wfo'], point['grid_x'], point['grid_y'])


def _fetch_current_and_hourly(wfo, grid_x, grid_y, grid):
    """Current conditions and hourly forecast from one NWS hourly request."""
    if not (wfo and grid_x and grid_y and grid):
        return
    now = time.time()
    # the hourly feed can still carry the hour that just ended
    periods = [p for p in nws.get_forecast_hourly(wfo, int(grid_x), int(grid_y), units.imperial())
               if not _hour_ended(p, now)]
    series = grid.get()
    _run_fetch('current', _fetch_current, periods, series)
    _run_fetch('hourly', _fetch_hourly, periods, series)


def _hour_ended(period, now):
    """True when an hourly period is already over."""
    try:
        return datetime.fromisoformat(period['start_time']).timestamp() + 3600 <= now
    except (ValueError, TypeError):
        return False


def _set_location_properties():
    """Set Location1 to Location5 and the Locations count from the configured slots."""
    count = 0
    for i in range(1, 6):
        loc_name = ADDON.getSetting(f'loc{i}')
        if loc_name:
            count += 1
        set_property(f'Location{i}', loc_name)
    set_property('Locations', str(count))


def _fetch_current(periods, grid):
    """Current conditions from the first NWS hourly period and gridpoint data for right now."""
    if not periods:
        log('No hourly forecast available for current conditions')
        return

    p = periods[0]
    log(f'Current from forecast: temp={p["temperature"]}C, '
        f'{p["short_forecast"]}, wind={p["wind_speed"]}km/h {p["wind_direction"]}')

    # bare Celsius, km/h and percent; Kodi converts these to the user unit
    temp = p['temperature']
    if temp is not None:
        set_property('Current.Temperature', f'{temp:.1f}')

    now = time.time()
    feels_like = nws.grid_value(grid.get('apparentTemperature', []), now)
    if feels_like is None:
        feels_like = temp
    if feels_like is not None:
        set_property('Current.FeelsLike', f'{feels_like:.1f}')

    sky = nws.grid_value(grid.get('skyCover', []), now)
    if sky is not None:
        set_property('Current.Cloudiness', str(round(sky)))
    gust = nws.grid_value(grid.get('windGust', []), now)
    if gust is not None:
        set_property('Current.WindGust', units.format_speed(gust))
    visibility = nws.grid_value(grid.get('visibility', []), now)
    if visibility is not None:
        set_property('Current.Visibility', units.format_distance(visibility))

    dewpoint = p.get('dewpoint')
    if dewpoint is not None:
        set_property('Current.DewPoint', f'{dewpoint:.1f}')

    humidity = p.get('humidity')
    if humidity is not None:
        set_property('Current.Humidity', str(round(humidity)))

    wind_speed = p.get('wind_speed')
    if wind_speed is not None:
        set_property('Current.Wind', str(round(wind_speed)))
        set_property('Current.WindSpeed', str(round(wind_speed)))
    wind_dir = p.get('wind_direction', '')
    if wind_dir:
        set_property('Current.WindDirection', wind_dir)

    set_property('Current.Precipitation', str(round(p.get('pop', 0))))
    set_property('Current.Condition', p.get('short_forecast', ''))

    code, is_night = nws.parse_icon_code(p['icon_url'])
    icon = icons.nws_to_kodi_icon(code, is_night)
    set_property('Current.OutlookIcon', icon)
    set_property('Current.FanartCode', icon.replace('.png', ''))

    set_property('Current.IsFetched', 'true')


def _fetch_forecast(wfo, grid_x, grid_y, grid, conditions):
    """Daily forecast from NWS, setting Daily.N.*, Day0 to Day6 and Weekend.{1,2}."""
    if not (wfo and grid_x and grid_y and grid):
        return

    periods = nws.get_forecast(wfo, int(grid_x), int(grid_y), units.imperial())
    series = grid.get()
    uv_daily = conditions.get().get('daily', {})
    if not periods:
        log('Forecast returned no periods')
        return

    p0 = periods[0]
    log(f'Forecast: {len(periods)} periods, '
        f'first: name={p0.get("name")}, temp={p0["temperature"]}, '
        f'daytime={p0["is_daytime"]}')

    # current conditions already cover tonight
    i = 1 if not periods[0]['is_daytime'] else 0
    if i:
        log(f'Skipping night-only first period: {periods[0].get("name")}')

    day_index = 1
    weekend_index = 1
    while i < len(periods) and day_index <= 31:
        period = periods[i]
        try:
            dt = datetime.fromisoformat(period['start_time'])
        except (ValueError, TypeError):
            i += 1
            continue

        condition_code, is_night = nws.parse_icon_code(period['icon_url'])
        icon = icons.nws_to_kodi_icon(condition_code, is_night)

        if period['is_daytime']:
            high = period['temperature']
            low = None
            night = None
            if i + 1 < len(periods) and not periods[i + 1]['is_daytime']:
                night = periods[i + 1]
                low = night['temperature']
                i += 2
            else:
                i += 1
                # the feed can end on a day; that night's low comes from the gridpoint data
                lows = nws.grid_values(series.get('minTemperature', []),
                                       dt.timestamp() + 10 * 3600, dt.timestamp() + 30 * 3600)
                low = min(lows) if lows else None
        else:
            i += 1
            continue

        _set_daily(day_index, period, dt, icon, high, low)
        _set_daily_grid(day_index, dt.timestamp(), series)
        _set_daily_details(day_index, period, night, uv_daily.get(dt.date().isoformat()))

        if dt.weekday() in (5, 6) and weekend_index <= 2:
            _set_weekend(weekend_index, period, dt, icon, high, low)
            weekend_index += 1

        day_index += 1

    set_property('Daily.IsFetched', 'true')
    if weekend_index > 1:
        set_property('Weekend.IsFetched', 'true')


def _fetch_hourly(periods, grid):
    """Hourly forecast from NWS, setting Hourly.N.* and 36Hour.{1,2,3}."""
    if not periods:
        log('Hourly forecast returned no periods')
        return

    h0 = periods[0]
    log(f'Hourly forecast: {len(periods)} periods, first: temp={h0["temperature"]}')

    hour_index = 1
    block_index = 1
    block_buf: list[dict] = []
    block_start = None
    for period in periods:
        if hour_index > 72:
            break
        try:
            dt = datetime.fromisoformat(period['start_time'])
        except (ValueError, TypeError):
            continue

        condition_code, is_night = nws.parse_icon_code(period['icon_url'])
        icon = icons.nws_to_kodi_icon(condition_code, is_night)

        prefix = f'Hourly.{hour_index}'
        set_property(f'{prefix}.Time', units.format_time(dt))
        set_property(f'{prefix}.LongDate', units.format_long_date(dt))
        set_property(f'{prefix}.ShortDate', units.format_short_date(dt))
        set_property(f'{prefix}.Outlook', period['short_forecast'])
        set_property(f'{prefix}.OutlookIcon', icon)
        set_property(f'{prefix}.FanartCode', icon.replace('.png', ''))

        temp = period['temperature']
        if temp is not None:
            set_property(f'{prefix}.Temperature', units.format_temp(temp))
            # bare, the skin appends System.TemperatureUnits
            set_property(f'{prefix}.TemperatureGraph', str(units.convert_temp(temp)))

        dewpoint = period.get('dewpoint')
        if dewpoint is not None:
            set_property(f'{prefix}.DewPoint', units.format_temp(dewpoint))

        humidity = period.get('humidity')
        if humidity is not None:
            set_property(f'{prefix}.Humidity', units.format_pct(humidity))

        set_property(f'{prefix}.Precipitation', units.format_pct(period['pop']))
        set_property(f'{prefix}.WindSpeed', units.format_speed(period['wind_speed']))
        set_property(f'{prefix}.WindDirection', period['wind_direction'])

        ts = dt.timestamp()
        feels_like = nws.grid_value(grid.get('apparentTemperature', []), ts)
        if feels_like is not None:
            set_property(f'{prefix}.FeelsLike', units.format_temp(feels_like))
        sky = nws.grid_value(grid.get('skyCover', []), ts)
        if sky is not None:
            set_property(f'{prefix}.Cloudiness', units.format_pct(sky))
        gust = nws.grid_value(grid.get('windGust', []), ts)
        if gust is not None:
            set_property(f'{prefix}.WindGust', units.format_speed(gust))

        if block_start is None:
            block_start = dt
        block_buf.append(period)
        if len(block_buf) >= 12 and block_index <= 3:
            _set_36hour(block_index, block_buf, block_start, grid)
            block_index += 1
            block_buf = []
            block_start = None

        hour_index += 1

    # the hourly feed can end mid-block
    if block_buf and block_index <= 3 and block_start is not None:
        _set_36hour(block_index, block_buf, block_start, grid)
        block_index += 1

    set_property('Hourly.IsFetched', 'true')
    if block_index > 1:
        set_property('36Hour.IsFetched', 'true')


def _fetch_sun_moon(prefix, conditions):
    """Today's sunrise, sunset and moon phase in the location's time zone."""
    now = datetime.now(_location_tz(prefix, conditions))
    set_property('Today.MoonPhase', lang(MOON_LABELS[meteo.moon_phase(now)]))
    today = now.strftime('%Y-%m-%d')
    data = conditions.get()
    set_property('Today.Sunrise', _clock(data.get('sunrise', {}).get(today)))
    set_property('Today.Sunset', _clock(data.get('sunset', {}).get(today)))


def _location_tz(prefix, conditions):
    """Location's time zone from its saved UTC offset, else from Open-Meteo, else Kodi's own."""
    saved = ADDON.getSetting(f'{prefix}utcoffset')
    offset = int(saved) if saved.lstrip('-').isdigit() else conditions.get().get('utc_offset')
    if offset is None:
        return datetime.now().astimezone().tzinfo
    return timezone(timedelta(seconds=offset))


def _local_datetime(value, tz):
    """Reformat an ISO timestamp as a date and time in a time zone, or empty when unparseable."""
    try:
        dt = datetime.fromisoformat(value).astimezone(tz)
    except (ValueError, TypeError):
        return ''
    return f'{units.format_short_date(dt)} {units.format_time(dt)}'


def _clock(value):
    """Reformat a local ISO time in the user's clock format, or empty when unparseable."""
    try:
        return units.format_time(datetime.fromisoformat(value or ''))
    except ValueError:
        return ''


def _fetch_uv(conditions, prefix):
    """Current UV index from Open-Meteo, saving the location's UTC offset when it changes."""
    offset = conditions.get().get('utc_offset')
    if offset is not None and ADDON.getSetting(f'{prefix}utcoffset') != str(offset):
        ADDON.setSetting(f'{prefix}utcoffset', str(offset))
    uv_index = conditions.get().get('current')
    log(f'UV: {uv_index}')
    if uv_index is not None:
        set_property('Current.UVIndex', lang(UV_LABELS[meteo.uv_level(round(uv_index))]))
        set_property('Current.UVIndexValue', str(round(uv_index)))


def _fetch_aqi(lat, lon):
    """Air quality from AirNow with the user's key, else from Open-Meteo."""
    if not lat or not lon:
        return

    data = aqi.get_aqi(lat, lon, ADDON.getSetting('airnow_key').strip())
    if not data:
        log('AQI returned no data')
        return

    log(f'AQI from {data["source"]}: {data["aqi"]} (level {data["level"]}) - {data["pollutant"]}')

    set_property('Current.AQI', str(data.get('aqi', '')))
    set_property('Current.AQICategory', lang(AQI_LABELS[data['level']]))
    set_property('Current.AQIPollutant', data.get('pollutant', ''))


def _fetch_maps(lat, lon):
    """Radar, satellite, forecast temperature and hazard maps centered on the location."""
    found = maps.get_maps(float(lat), float(lon), [lang(i) for i in OUTLOOK_LABELS])
    for index, entry in enumerate(found, start=1):
        set_property(f'Map.{index}.Area', entry['area'])
        set_property(f'Map.{index}.Layer', entry['layer'])
        legend = _legend_name(entry['legend'])
        set_property(f'Map.{index}.Legend', os.path.join(MEDIA, f'{legend}.png') if legend else '')
        set_property(f'Map.{index}.LegendOverlay',
                     os.path.join(MEDIA, f'{legend}_overlay.png') if legend else '')
        set_property(f'Map.{index}.Heading', _map_heading(entry))

    log(f'Maps: {", ".join(entry["kind"] for entry in found) or "none"}')
    if found:
        set_property('Map.IsFetched', 'true')


def _legend_name(kind):
    """Shipped legend image name for a legend kind, the temperature one in the user's unit."""
    if kind == 'temperature':
        return f'legend_temperature_{"f" if units.imperial() else "c"}'
    return f'legend_{kind}' if kind else ''


def _map_heading(entry):
    """Heading for a map, naming the storm on a tropical cyclone map."""
    if entry['kind'] == 'storm':
        return lang(STORM_HEADINGS.get(entry['type'], 30108)) % entry['name']
    return lang(MAP_HEADINGS[entry['kind']])


def _fetch_alerts(lat, lon, loc_prefix, conditions):
    """Active weather alerts from NWS, expiry in the location's time zone."""
    if not lat or not lon:
        return

    alerts = nws.get_alerts(lat, lon)
    if not alerts:
        log('No active alerts')
        set_property('Alerts.Count', '0')
        set_property('Alerts.IsFetched', 'true')
        return

    tz = _location_tz(loc_prefix, conditions)
    log(f'Alerts: {len(alerts)} active')
    set_property('Alerts.Count', str(len(alerts)))

    for i, alert in enumerate(alerts, start=1):
        prefix = f'Alerts.{i}'
        set_property(f'{prefix}.Event', alert['event'])
        set_property(f'{prefix}.Headline', alert['headline'])
        set_property(f'{prefix}.Description', alert['description'])
        set_property(f'{prefix}.Severity', alert['severity'])
        set_property(f'{prefix}.Urgency', alert['urgency'])
        set_property(f'{prefix}.Expires', _local_datetime(alert['expires'], tz))
        set_property(f'{prefix}.SenderName', alert['sender_name'])
        set_property(f'{prefix}.Instruction', alert.get('instruction', ''))

    set_property('Alerts.IsFetched', 'true')


def _set_daily_details(day_index, day, night, uv_max):
    """Set Daily.N forecaster text for the day and night and the day's peak UV index."""
    d = f'Daily.{day_index}'
    set_property(f'{d}.DetailedOutlook', day.get('detailed_forecast', ''))
    if night:
        set_property(f'{d}.NightDetailedOutlook', night.get('detailed_forecast', ''))
    if uv_max is not None:
        set_property(f'{d}.UVIndex', lang(UV_LABELS[meteo.uv_level(round(uv_max))]))
        set_property(f'{d}.UVIndexValue', str(round(uv_max)))


def _set_daily_grid(day_index, start, grid):
    """Set Daily.N cloud cover, peak gust and 24 hour precipitation from gridpoint data."""
    d = f'Daily.{day_index}'
    sky = nws.grid_values(grid.get('skyCover', []), start, start + 12 * 3600)
    if sky:
        set_property(f'{d}.Cloudiness', units.format_pct(sum(sky) / len(sky)))
    gusts = nws.grid_values(grid.get('windGust', []), start, start + 12 * 3600)
    if gusts:
        set_property(f'{d}.WindGust', units.format_speed(max(gusts)))
    rain = nws.grid_values(grid.get('quantitativePrecipitation', []), start, start + 24 * 3600)
    if rain:
        set_property(f'{d}.PrecipitationAmount', units.format_precip(sum(rain)))


def _set_daily(day_index, period, dt, icon, high, low):
    """Set Daily.N.* and, for the first seven days, Day{N-1}.* for one forecast day."""
    short_date = units.format_short_date(dt)
    short_day = units.format_short_day(dt)
    long_date = units.format_long_date(dt)
    outlook = icons.shorten_forecast(period['short_forecast'])
    fanart = icon.replace('.png', '')

    # Kodi converts Day{N} temps from Celsius; Daily.N.* reach the skin as set
    high_c = f'{high:.1f}' if high is not None else ''
    low_c = f'{low:.1f}' if low is not None else ''
    pop_bare = str(round(period['pop']))

    d = f'Daily.{day_index}'
    set_property(f'{d}.LongDate', long_date)
    set_property(f'{d}.ShortDate', short_date)
    set_property(f'{d}.LongDay', units.format_day(dt))
    set_property(f'{d}.ShortDay', short_day)
    set_property(f'{d}.Outlook', outlook)
    set_property(f'{d}.OutlookIcon', icon)
    set_property(f'{d}.FanartCode', fanart)
    set_property(f'{d}.Precipitation', units.format_pct(period['pop']))
    set_property(f'{d}.WindSpeed', units.format_speed(period['wind_speed']))
    set_property(f'{d}.WindDirection', period['wind_direction'])
    if high is not None:
        set_property(f'{d}.HighTemperature', units.format_temp(high))
    if low is not None:
        set_property(f'{d}.LowTemperature', units.format_temp(low))

    if day_index <= 7:
        g = f'Day{day_index - 1}'
        set_property(f'{g}.Title', period['name'] or short_day)
        set_property(f'{g}.Outlook', outlook)
        set_property(f'{g}.OutlookIcon', icon)
        set_property(f'{g}.FanartCode', fanart)
        set_property(f'{g}.Precipitation', pop_bare)
        set_property(f'{g}.WindSpeed', units.format_speed(period['wind_speed']))
        set_property(f'{g}.WindDirection', period['wind_direction'])
        if high_c:
            set_property(f'{g}.HighTemp', high_c)
        if low_c:
            set_property(f'{g}.LowTemp', low_c)

    log(f'{d}: high={high_c}C, low={low_c}C, day={short_day}, outlook={outlook}')


def _set_weekend(weekend_index, period, dt, icon, high, low):
    """Set Weekend.{1,2}.* for skins that show a separate weekend block."""
    w = f'Weekend.{weekend_index}'
    set_property(f'{w}.LongDay', units.format_day(dt))
    set_property(f'{w}.LongDate', units.format_long_date(dt))
    set_property(f'{w}.Outlook', icons.shorten_forecast(period['short_forecast']))
    set_property(f'{w}.OutlookIcon', icon)
    set_property(f'{w}.FanartCode', icon.replace('.png', ''))
    pop = units.format_pct(period['pop'])
    set_property(f'{w}.Precipitation', pop)
    set_property(f'{w}.ChancePrecipitation', pop)
    set_property(f'{w}.WindSpeed', units.format_speed(period['wind_speed']))
    set_property(f'{w}.WindDirection', period['wind_direction'])
    if period.get('humidity') is not None:
        set_property(f'{w}.Humidity', units.format_pct(period['humidity']))
    if high is not None:
        set_property(f'{w}.HighTemperature', units.format_temp(high))
    if low is not None:
        set_property(f'{w}.LowTemperature', units.format_temp(low))


def _set_36hour(block_index, periods, start_dt, grid):
    """Aggregate up to 12 hourly periods into one 36Hour.N entry led by the most severe period."""
    if not periods:
        return

    rep = max(periods, key=lambda p: nws.severity(
        nws.parse_icon_code(p['icon_url'])[0]))
    code, is_night = nws.parse_icon_code(rep['icon_url'])
    icon = icons.nws_to_kodi_icon(code, is_night)

    temps = [p['temperature'] for p in periods if p.get('temperature') is not None]
    hums = [p['humidity'] for p in periods if p.get('humidity') is not None]
    winds = [p['wind_speed'] for p in periods if p.get('wind_speed') is not None]
    pops = [p['pop'] for p in periods]

    avg_temp = sum(temps) / len(temps) if temps else None
    avg_hum = sum(hums) / len(hums) if hums else None
    avg_wind = sum(winds) / len(winds) if winds else 0
    max_pop = max(pops) if pops else 0

    h = f'36Hour.{block_index}'
    heading = f'{units.format_short_day(start_dt)} {units.format_time(start_dt)}'
    set_property(f'{h}.Heading', heading)
    set_property(f'{h}.Outlook', icons.shorten_forecast(rep['short_forecast']))
    set_property(f'{h}.OutlookIcon', icon)
    set_property(f'{h}.FanartCode', icon.replace('.png', ''))
    set_property(f'{h}.Precipitation', units.format_pct(max_pop))
    set_property(f'{h}.WindSpeed', units.format_speed(avg_wind))
    set_property(f'{h}.WindDirection', rep['wind_direction'])
    if avg_temp is not None:
        set_property(f'{h}.Temperature', units.format_temp(avg_temp))
        set_property(f'{h}.TemperatureHeading', heading)
    start = start_dt.timestamp()
    feels = nws.grid_values(grid.get('apparentTemperature', []), start, start + len(periods) * 3600)
    if feels:
        set_property(f'{h}.FeelsLike', units.format_temp(sum(feels) / len(feels)))
    elif avg_temp is not None:
        set_property(f'{h}.FeelsLike', units.format_temp(avg_temp))
    if avg_hum is not None:
        set_property(f'{h}.Humidity', units.format_pct(avg_hum))

"""Location slot setup from a keyboard search."""

import xbmc
import xbmcgui

from . import geocode, http, nws
from .weather import ADDON, ADDON_NAME, lang, log


def configure(param):
    """Configure a location slot from a keyboard search and store its NWS grid in settings."""
    loc_index = param.replace('loc', '')

    current = ADDON.getSetting(f'loc{loc_index}')
    keyboard = xbmc.Keyboard(current, lang(30110))
    keyboard.doModal()
    if not keyboard.isConfirmed():
        return

    query = keyboard.getText().strip()
    if not query:
        return

    log(f'Searching for: {query}')

    try:
        results = geocode.search(query)
    except http.Aborted:
        return
    except Exception as e:
        log(f'Geocode error: {e}', xbmc.LOGERROR)
        xbmcgui.Dialog().notification(ADDON_NAME, lang(30111), xbmcgui.NOTIFICATION_ERROR)
        return

    if not results:
        log(f'No results for query: {query}')
        xbmcgui.Dialog().notification(ADDON_NAME, lang(30112), xbmcgui.NOTIFICATION_WARNING)
        return

    log(f'Found {len(results)} results for: {query}')

    labels: list = [
        f'{r["name"]} (ZIP {r["zip"]})  [{r["lat"]}, {r["lon"]}]'
        if r.get('zip') else
        f'{r["name"]}  [{r["lat"]}, {r["lon"]}]'
        for r in results
    ]
    selected = xbmcgui.Dialog().select(lang(30113), labels)
    if selected < 0:
        return
    location = results[selected]

    lat = location['lat']
    lon = location['lon']

    try:
        point = nws.get_point(lat, lon)
    except http.Aborted:
        return
    except Exception as e:
        log(f'NWS point lookup failed: {e}', xbmc.LOGERROR)
        xbmcgui.Dialog().notification(ADDON_NAME, lang(30114), xbmcgui.NOTIFICATION_ERROR)
        return

    # geocoder city matches USPS/ZIP; NWS names the nearest place
    geo_city = location.get('city', '')
    geo_state = location.get('state', '')
    nws_city = point.get('city', '')
    nws_state = point.get('state', '')
    if geo_city and geo_state:
        display_name = f'{geo_city}, {geo_state}'
    elif nws_city and nws_state:
        display_name = f'{nws_city}, {nws_state}'
    else:
        display_name = location['name']

    prefix = f'loc{loc_index}'
    ADDON.setSetting(prefix, display_name)
    ADDON.setSetting(f'{prefix}lat', lat)
    ADDON.setSetting(f'{prefix}lon', lon)
    ADDON.setSetting(f'{prefix}gridwfo', point['wfo'])
    ADDON.setSetting(f'{prefix}gridx', str(point['grid_x']))
    ADDON.setSetting(f'{prefix}gridy', str(point['grid_y']))

    log(f'Location {loc_index} set: {display_name} ({lat},{lon}) WFO:{point["wfo"]}')

    xbmcgui.Dialog().notification(ADDON_NAME, lang(30115) % display_name,
                                  xbmcgui.NOTIFICATION_INFO)

"""NWS radar layers from the NCEP map server, with warning outlines drawn over the reflectivity."""

WMS = 'https://opengeo.ncep.noaa.gov/geoserver'

# CONUS first, its box overlaps the Caribbean one
REGIONS = (
    ('conus', -130, -60, 20, 55),
    ('alaska', -176, -126, 50, 72),
    ('hawaii', -164, -151, 15, 26),
    ('carib', -90, -60, 10, 25),
    ('guam', 140, 150, 9, 18),
)


def region_for(lat, lon):
    """NWS radar region covering a location, or None outside all of them."""
    for name, lon_min, lon_max, lat_min, lat_max in REGIONS:
        if lon_min <= lon <= lon_max and lat_min <= lat <= lat_max:
            return name
    return None


def caps_url(region):
    """Capabilities address listing a region's radar frame times."""
    return (f'{WMS}/{region}/{region}_bref_qcd/ows'
            '?service=WMS&version=1.3.0&request=GetCapabilities')


def layers(region):
    """Map layers and matching styles for a region's radar with warning outlines."""
    return f'{region}:{region}_bref_qcd,wwa:warnings', ',wwa_warnings'
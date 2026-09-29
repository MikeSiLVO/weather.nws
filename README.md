# NWS Weather

US weather for Kodi from the National Weather Service and other US government sources.

## What it shows

- Current conditions, a 72 hour hourly forecast and a 7 day forecast, including the local
  forecaster's written forecast for each day and night
- Radar and satellite loops centered on your location, forecast highs across the lower 48 states,
  and a hurricane or severe weather map when one applies
- Active NWS alerts for your location
- Air quality, UV index, sunrise, sunset and moon phase

Temperatures, wind, times and dates follow your Kodi region settings.

## Setup

Choose **NWS Weather** as the weather service in Kodi's settings, then set up to five locations in
the add-on's settings by US city and state, ZIP code or street address.

Air quality works without any setup. To use EPA monitor readings instead of the Open-Meteo
air quality model, add a free key from [airnowapi.org](https://docs.airnowapi.org/) under
**Air quality**.

## Coverage

The 50 states, Puerto Rico, the US Virgin Islands and Guam. The forecast highs and severe weather
maps cover the lower 48 states only.

## Requirements

Kodi 22 (Piers).

## For skinners

Every property the add-on sets is listed in [DOCS/skinning.md](DOCS/skinning.md).

## Data sources

- Forecasts, alerts, radar and weather maps: National Weather Service and NOAA
- Base maps: US Geological Survey
- UV index, sunrise, sunset and air quality: [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0),
  or AirNow with your own key for air quality
- Location search: US Census geocoder and Nominatim, © OpenStreetMap contributors

## License

GPL-3.0-only. See [LICENSE.txt](LICENSE.txt).

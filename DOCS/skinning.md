# Skinning reference

Every property weather.nws sets on the weather window. Read them with
`$INFO[Weather.Data(Name)]`. An empty property means the value is not available for the
current location.

## Value formats

Values come in the user's units with the unit included (`61°F`, `10 mph`, `40%`, `0.11 in`,
`5.0 mi`), except the few marked bare below, which Kodi converts itself. Read those through
`Weather.Data()` too and they carry the unit as well.

Rain amounts and visibility are in inches and miles when the temperature unit is Fahrenheit,
millimeters and kilometers otherwise.

Times and dates follow the user's region settings (`3:00 PM` or `15:00`, `Thu Sep 24` or
`Thu 24 Sep`).

Day and month names, UV and air quality levels and map headings are in the user's language.
Forecast, condition and alert text comes from NWS in English.

Icons are file names such as `28.png` from the active weather icon pack. `FanartCode` is the
same number without the extension.

## Location

| Property | Value |
|---|---|
| `Current.Location` | Location name |
| `Location1` to `Location5` | Names of the configured locations |
| `Locations` | How many locations are configured |
| `Forecast.City`, `Forecast.Country` | City part of the name, `US` |
| `Forecast.Latitude`, `Forecast.Longitude` | Coordinates |
| `Forecast.Updated` | Date and time of the forecast data |
| `WeatherProvider` | `NWS Weather` |

## Current conditions

Set when `Current.IsFetched` is `true`.

| Property | Value |
|---|---|
| `Temperature`, `FeelsLike`, `DewPoint` | Bare, converted by Kodi |
| `Humidity`, `Cloudiness`, `Precipitation` | Bare percent |
| `Wind` | Bare; Kodi shows it as "From NW at 10 mph" |
| `WindSpeed` | Bare |
| `WindDirection` | Cardinal, `NW` |
| `WindGust` | `18 mph` |
| `Visibility` | `5.0 mi` |
| `Condition` | `Chance Rain Showers` |
| `OutlookIcon`, `FanartCode` | `28.png`, `28` |
| `UVIndex` | `Low`, `Moderate`, `High`, `Very high`, `Extreme` |
| `UVIndexValue` | UV index number, `6` |
| `AQI` | US Air Quality Index, `16` |
| `AQICategory` | `Good` to `Hazardous` |
| `AQIPollutant` | Pollutant with the highest index: `PM2.5`, `PM10`, `O3`, `NO2`, `SO2`, `CO` |

## Hourly

`Hourly.1` to `Hourly.72`, starting with the current hour. Set when `Hourly.IsFetched` is `true`.

| Property | Value |
|---|---|
| `Time` | `3:00 PM` |
| `ShortDate`, `LongDate` | `Thu Sep 24`, `Thursday, September 24` |
| `Temperature`, `FeelsLike`, `DewPoint` | `61°F` |
| `TemperatureGraph` | Temperature as a bare number in the user's unit |
| `Humidity`, `Precipitation`, `Cloudiness` | `93%` |
| `WindSpeed`, `WindGust` | `11 mph` |
| `WindDirection` | `NNE` |
| `Outlook` | `Rain Showers Likely` |
| `OutlookIcon`, `FanartCode` | `12.png`, `12` |

## Daily

`Daily.1` to `Daily.7`, starting with the next daytime period. Set when `Daily.IsFetched` is `true`.

| Property | Value |
|---|---|
| `ShortDay`, `LongDay` | `Thu`, `Thursday` |
| `ShortDate`, `LongDate` | `Thu Sep 24`, `Thursday, September 24` |
| `HighTemperature`, `LowTemperature` | `72°F` |
| `Precipitation` | Chance of precipitation, `40%` |
| `PrecipitationAmount` | Total over the day and night, `0.11 in` |
| `Cloudiness` | Daytime cloud cover, `81%` |
| `WindSpeed` | `10 mph` |
| `WindGust` | Highest daytime gust, `26 mph` |
| `WindDirection` | `SW` |
| `Outlook` | Short summary, `Rain / Fog` |
| `OutlookIcon`, `FanartCode` | `12.png`, `12` |
| `DetailedOutlook` | Forecaster's text for the day, `Sunny, with a high near 73. North wind around 10 mph.` |
| `NightDetailedOutlook` | Forecaster's text for the night that follows |
| `UVIndex` | Peak UV for the day, `Low` to `Extreme` |
| `UVIndexValue` | Peak UV index number, `6` |

`Day0` to `Day6` hold the same seven days.

| Property | Value |
|---|---|
| `Title` | Period name, `Thursday` |
| `HighTemp`, `LowTemp` | Bare, converted by Kodi |
| `Precipitation` | Bare percent |
| `WindSpeed` | `10 mph` |
| `WindDirection` | `SW` |
| `Outlook` | Short summary, `Rain / Fog` |
| `OutlookIcon`, `FanartCode` | `12.png`, `12` |

## 36 hour

`36Hour.1` to `36Hour.3`, the next three 12 hour blocks. Set when `36Hour.IsFetched` is `true`.

| Property | Value |
|---|---|
| `Heading`, `TemperatureHeading` | Block start, `Thu 3:00 PM` |
| `Temperature`, `FeelsLike` | Block average, `60°F` |
| `Humidity` | Block average, `90%` |
| `Precipitation` | Highest chance in the block, `70%` |
| `WindSpeed` | Block average, `12 mph` |
| `WindDirection` | `NE` |
| `Outlook` | Most severe condition in the block |
| `OutlookIcon`, `FanartCode` | `4.png`, `4` |

## Weekend

`Weekend.1` and `Weekend.2`, the coming Saturday and Sunday. Set when `Weekend.IsFetched` is
`true`.

| Property | Value |
|---|---|
| `LongDay`, `LongDate` | `Saturday`, `Saturday, September 26` |
| `HighTemperature`, `LowTemperature` | `84°F` |
| `Precipitation`, `ChancePrecipitation` | Chance of precipitation, `20%` |
| `Humidity` | `55%` |
| `WindSpeed` | `6 mph` |
| `WindDirection` | `S` |
| `Outlook` | Short summary, `Sunny` |
| `OutlookIcon`, `FanartCode` | `32.png`, `32` |

## Sun and moon

| Property | Value |
|---|---|
| `Today.Sunrise`, `Today.Sunset` | `7:13 AM`, `7:17 PM` |
| `Today.MoonPhase` | `Waxing gibbous` |

## Maps

Up to five 16:9 maps, numbered from `Map.1` in the order below with no gaps. A map that does
not apply to the location or the day is left out. Set when `Map.IsFetched` is `true`.

| `Heading` | Shows | When |
|---|---|---|
| Local radar | The last hour of radar, animated, about 100 miles across | Always |
| Regional radar | The last hour of radar, animated, about 400 miles across | Always |
| Satellite | Recent infrared cloud imagery, animated, same area as regional radar; cold storm tops are colored except in Alaska, Guam and along the Canadian border | Always |
| Forecast highs | Today's forecast high temperatures across the lower 48 states | Lower 48 states only |
| Hurricane Odalys, Tropical Storm Fay, and so on | Forecast cone, track and watches and warnings, about 700 miles across | A tropical cyclone forecast reaches the area |
| Severe weather outlook | Today's severe thunderstorm risk areas, labeled Marginal to High, same area | No tropical cyclone, and a Marginal or higher risk in the area |

| Property | Value |
|---|---|
| `Area` | Background image: a base map with state lines, highways and city names, or the satellite loop or temperature map |
| `Layer` | Transparent image the same size as `Area`: radar with warning outlines, the storm or outlook, or state lines and city names over the satellite and temperature maps |
| `Legend` | Color scale for the map, 700x110: rain from light to heavy on radar, clouds to storm tops on a colored satellite map, temperatures in the user's unit on forecast highs; empty otherwise |
| `LegendOverlay` | The same scale in the bottom right corner of a transparent image the size of `Area`; empty when `Legend` is |
| `Heading` | Map name |

## Alerts

Active NWS alerts for the location, most severe first. `Alerts.IsFetched` is `true` whenever
alerts were checked, including when there are none.

| Property | Value |
|---|---|
| `Alerts.Count` | Number of active alerts |
| `Alerts.N.Event` | `Tornado Warning` |
| `Alerts.N.Headline` | One line summary |
| `Alerts.N.Description` | Full alert text |
| `Alerts.N.Instruction` | What to do, when NWS gives it |
| `Alerts.N.Severity` | `Extreme`, `Severe`, `Moderate`, `Minor`, `Unknown` |
| `Alerts.N.Urgency` | `Immediate`, `Expected`, `Future`, `Past`, `Unknown` |
| `Alerts.N.SenderName` | Issuing NWS office |
| `Alerts.N.Expires` | `Thu Sep 24 10:00 PM` |

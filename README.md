# OpenCARWINGS Home Assistant Integration

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

![Project Maintenance][maintenance-shield]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![Community Forum][forum-shield]][forum]

Home Assistant integration for the [OpenCARWINGS][opencarwings] server. Each Nissan (or
compatible) car on your account becomes a device carrying the readings the car uploads
and the remote commands its TCU accepts.

## Support the project

This is my first integration for HA. If you find it useful, you can
[buy me a coffee][buymecoffee].

## What you get

One device per car. Entity IDs are built from the car's nickname, so a car called
"DKL" gets `sensor.dkl_odometer`, `switch.dkl_climate`, and so on.

### Sensors

| Entity | Notes |
|---|---|
| State of charge | Percentage, recorded for statistics |
| State of charge display | What the dashboard shows, which can differ |
| Range (climate on) / Range (climate off) | Kilometres |
| Charge bars | The dashboard's bar count |
| Odometer | Kilometres, recorded as a total for long-term statistics |
| Charge time (3kW / 1.4kW / 6.6kW) | Minutes remaining, empty when the car has no estimate |
| State of health | Percentage the car reports for the pack |
| Battery energy | Energy left in the pack, shown in kWh |
| GIDs | Energy units the car counts in |
| Capacity bars | The dashboard's capacity bars, out of 12 |
| Gear | `park`, `drive` or `reverse` |
| Status | One of `charging`, `running`, `ac_on`, `idle` |
| VIN | Diagnostic |
| Last updated | When the car last reported. Diagnostic |
| Last requested | When a command was last sent to the car. Diagnostic |
| Signal level, Carrier | The TCU's mobile connection. Diagnostic |
| Max GIDs, Update counter | Diagnostic |

Odometer, state of health and max GIDs read as unknown until the car has reported them.
The server stores 0 or -1 for a field it has never received.

### Binary sensors

Charge cable, Charging, Quick charging, Charge finish, Climate status, Eco mode, Running,
Battery heater. Battery heater fitted and 6.6kW charger fitted are diagnostic.

### Controls

| Entity | What it does |
|---|---|
| Climate (switch) | Sends climate on/off. Follows the car's reported state |
| Requested temperature (number) | 0–31 °C, sent with the next climate on |
| Remote start (switch) | Paired start/stop commands |
| Horn and lights (switch) | Paired on/off commands |
| Lock, Unlock, Horn, Lights (buttons) | One command per press |
| Charge start, Charge to 80% (buttons) | |
| Request data refresh (button) | Wakes the car and asks it to upload |
| Read configuration (button) | Diagnostic |

### Device tracker

The car's position, from the server's last location fix. It sits on the same device as
the sensors and buttons.

## What it cannot do

The integration can only report what the OpenCARWINGS API returns, and the API only
knows what the car's TCU uploads.

- The TCU never reports whether the doors are locked. Lock and unlock are buttons, and
  there is no `lock` entity.
- The server takes a temperature with the climate on command but never reports back what
  the car settled on. Requested temperature holds your request, and the car may be doing
  something else.
- Cabin temperature is in the API, but on the car this was developed against it always
  reads as the no-data sentinel. No sensor is exposed for it.
- Remote start and Horn and lights have no state at all in the API. They show as
  assumed-state toggles holding the last command sent.
- Sending a temperature needs a Ficosa 2016 TCU. Older Continental units reject the
  payload.

## How it stays up to date

Two paths, both running at once:

1. A websocket to the server's `/ws/notif/` endpoint. The server pushes each object as
   it writes it, so entities follow the car live.
2. Polling on your configured interval, as a safety net if the socket drops.

Neither wakes the car. Only a command does that, and the one for this job is the
per-car **Request data refresh** button.

The server gives the car up to five minutes to answer a command. The integration
follows each one in the background and fires
`ha_opencarwings_command_finished` on the event bus when it resolves, with `vin`,
`command_type`, `result` (`success`, `error` or `timeout`) and `seconds`. Alerts pushed
by the server fire as `ha_opencarwings_alert`.

## Installation

### HACS

HACS → Integrations → three dots → Custom repositories → add this repository with
category "Integration" → Install → restart Home Assistant.

### Manual

Copy `custom_components/ha_opencarwings` into `<config>/custom_components/` and restart
Home Assistant.

Then: Settings → Devices & Services → Add Integration → **OpenCARWINGS**.

## Configuration

Everything is set in the UI, and every field can be changed later under the
integration's Configure button.

| Field | |
|---|---|
| API key | Required. Sign in to the server in a browser, open your account settings and copy the personal API key |
| Scan interval | How often to re-read the server. Default 15 minutes |
| API base URL | Optional. Defaults to the public instance |
| Command PIN | Your account PIN, if you set one on the server. Without it the server refuses lock, unlock, horn, lights and remote start |
| GPS radius | Kilometres from Home. Fixes beyond it are ignored and the last good one held. See below. Set 0 to accept every fix |

The key goes out as `Authorization: Token <key>` on every request. It does not expire;
resetting it on the server invalidates the old one.

### The GPS radius

Some head units hold the wrong map region or stale map data and report a position
hundreds of kilometres from where the car actually is, while the TCU has it right.
Setting a radius drops those fixes and keeps the last good position on the map. Off by
default.

### Upgrading from username and password

Versions up to 0.6.0 signed in with a username and password. On upgrade, Home Assistant
shows a reauthentication prompt asking for your API key; the old credentials are deleted
once the new key is accepted.

## Actions

`ha_opencarwings.refresh` re-reads the server, optionally for one account only.

`ha_opencarwings.ac_on` turns the climate on at a temperature you pass in, overriding the
Requested temperature entity. Takes `temp` (0–31), `unit` (celsius or fahrenheit), and
optionally `vin` and `entry_id`.

## Development

```
pytest
```

Home Assistant stubs live under `tests/stubs/`, so the suite runs without installing
Home Assistant.

## Issues and contributions

Bugs and pull requests: https://github.com/czapeczek/ha_opencarwings

## Thanks

To the [OpenCARWINGS project][opencarwings] for the reverse-engineered API this is
built on.

<!-- Badges -->
[opencarwings]: https://github.com/developerfromjokela/opencarwings

[releases-shield]: https://img.shields.io/github/v/release/czapeczek/ha_opencarwings?style=for-the-badge
[releases]: https://github.com/czapeczek/ha_opencarwings/releases

[commits-shield]: https://img.shields.io/github/commit-activity/y/czapeczek/ha_opencarwings?style=for-the-badge
[commits]: https://github.com/czapeczek/ha_opencarwings/commits/main

[license-shield]: https://img.shields.io/github/license/czapeczek/ha_opencarwings?style=for-the-badge

[maintenance-shield]: https://img.shields.io/badge/maintained-yes-green.svg?style=for-the-badge

[buymecoffeebadge]: https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support-yellow.svg?style=for-the-badge
[buymecoffee]: https://www.buymeacoffee.com/czapeczek

[forum-shield]: https://img.shields.io/badge/community-forum-blue.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/

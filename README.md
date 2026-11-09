# Adaptive Tone for Omarchy

Gentle display warmth that responds to your laptop's ambient light sensor. Cooler in bright surroundings, a little warmer in dim rooms, with smooth transitions instead of an abrupt day/night switch.

**This is an approximation inspired by True Tone, not a recreation of it.** A lux sensor measures light level, not the color of room lighting. The warmth curve is a comfort preference: it cannot distinguish equally bright warm lamplight and cool daylight. Apple and True Tone are trademarks of Apple Inc.; this project is independent.

## Features

- A bar panel with current light level, display temperature, and automatic target.
- Auto and Pause controls; Pause holds the current tone and survives restarts.
- Adjustable dim-room warmth and Responsive, Gentle, or Slow transitions.
- The stock Night Light/Day Light control still works: a detected manual change pauses adaptation for one hour.
- One background worker per user, owned by the plugin. Disable/remove the plugin to stop adaptation. No separate systemd installation is needed.
- Entirely local: no camera, weather requests, telemetry, downloaded code, or root access.
- Theme-aware controls and English strings with Omarchy's translation fallback.

## Requirements and compatibility

- Omarchy's Quickshell shell and its built-in bar. Tested with Omarchy **4.5.0-3**; earlier Quattro releases and replacement bars have not been tested.
- Python 3.10 or newer, `hyprsunset`, `hyprctl`, and `pgrep` (procps-ng). The Omarchy CLI/shell and these dependencies are normally present on Omarchy; this plugin installs no packages.
- A readable Linux IIO sensor exposing `in_illuminance_input` in **lux** under `/sys/bus/iio/devices/iio:device*/`. Raw-only sensors are deliberately unsupported because their scale and units vary.

| Hardware | Status |
| --- | --- |
| 2017 12-inch MacBook (`MacBook10,1`), `acpi-als` | Tested on real hardware; covering/uncovering the sensor changed 303 → 0 → 302 lux |
| 2015/2016 12-inch MacBooks | Not yet tested |
| Other laptops with a compatible readable IIO lux input | Expected to work; not yet tested |
| Apple Silicon/Asahi | Not yet tested; may require sensor calibration or different channels |

The first readable IIO lux input is selected. If none is available, the panel reports the problem and makes no display changes. Please include your model, Omarchy version, sensor name, and observed behavior when reporting compatibility.

## Install

```bash
omarchy plugin add https://github.com/doctor/omarchy-adaptive-tone.git --enable
```

Place Adaptive Tone in the right side of the bar when prompted. You can move it later:

```bash
omarchy bar move io.github.doctor.adaptive-tone --section right
```

Only one automatic color-temperature controller should be active. Disable scheduled hyprsunset profiles and other automatic temperature tools first. The plugin reuses a running hyprsunset instance, or starts a neutral instance if needed.

If migrating from the original standalone service, stop it before enabling the plugin:

```bash
systemctl --user disable --now omarchy-adaptive-tone.service
```

The plugin detects that legacy service and refuses to compete with it. Existing Adaptive Tone settings are retained.

## Use

Click the sun icon to open the panel. Right-click the icon to pause or resume. Within the panel, **A** resumes automatic tone, **P** pauses, **Left/Right** changes the dim-room tone, **Up/Down** selects transition speed, and **Escape** closes it. All controls also work with the mouse.

Lower Kelvin values mean warmer tones. Defaults are **5000K at or below 5 lux** and **6500K at or above 1000 lux**, with logarithmic interpolation between them. Gentle uses a 45-second smoothing time constant: a large change settles over roughly 2–3 minutes. Responsive uses 20 seconds; Slow uses 90 seconds. Changes are additionally limited to 20K per second.

A manual Night Light/Day Light change is detected by reading hyprsunset's temperature. A click that leaves that value unchanged cannot be detected. Click **Auto** to end the one-hour hold early. On disable, an automatically controlled tint returns to neutral; a detected manual override is preserved.

The temperature filter does not change backlight brightness. Hyprsunset's color transform applies across the active outputs it controls, including external displays.

### Terminal controls

```bash
omarchy-shell io.github.doctor.adaptive-tone status
omarchy-shell io.github.doctor.adaptive-tone pause
omarchy-shell io.github.doctor.adaptive-tone resume
```

### Settings and local state

Settings live in `$XDG_CONFIG_HOME/omarchy/adaptive-tone.json` (normally `~/.config/omarchy/adaptive-tone.json`). The file is created only when a control is changed; installation does not overwrite configuration. Advanced values default to:

```json
{
  "minimum_kelvin": 5000,
  "maximum_kelvin": 6500,
  "dim_lux": 5,
  "bright_lux": 1000,
  "smoothing_seconds": 45,
  "maximum_kelvin_per_second": 20,
  "poll_seconds": 3,
  "manual_override_seconds": 3600,
  "automatic": true
}
```

After hand-editing settings, disable and re-enable the plugin. Settings are validated before use. The latest reading and manual-override deadline are stored in `$XDG_STATE_HOME/omarchy/adaptive-tone.json` (normally `~/.local/state/omarchy/adaptive-tone.json`); there is no history. Sensor failure holds the previous tone and reports an error. Desktop connection failures are retried.

## Disable, remove, and update

```bash
omarchy plugin disable io.github.doctor.adaptive-tone
omarchy plugin enable io.github.doctor.adaptive-tone
omarchy plugin update io.github.doctor.adaptive-tone
omarchy plugin remove io.github.doctor.adaptive-tone
```

Disabling or removing closes the worker and stops adaptation. Saved preferences and the latest state remain so reinstalling preserves your choices. To erase those too, remove only `~/.config/omarchy/adaptive-tone.json` and `~/.local/state/omarchy/adaptive-tone.json` (or their XDG equivalents). No packaged Omarchy files are modified.

## Development

```bash
python -m unittest discover -s tests -v
node tests/model.test.cjs
omarchy plugin validate .
python backend.py preview
```

Node is used only for developer checks, not at runtime. The checks exercise bounded monotonic mapping, smoothing, manual override expiry, suspend timing, configuration and sensor validation, telemetry with markup-shaped strings, single-worker locking, persistent controls, and cleanup on EOF/SIGTERM. Worker lifecycle tests use fake display commands and never touch the real display.

Before a release, also check the real panel, Escape, Auto/Pause, both warmth buttons, all transition speeds, manual Night Light/Day Light, disable/re-enable, shell restart, and removal. The plugin ships a local Python worker and does not fetch or execute external code.

## License

MIT. See [LICENSE](LICENSE).

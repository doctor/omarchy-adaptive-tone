#!/usr/bin/python
"""Local ambient-light tone worker, owned by the Omarchy plugin lifecycle."""

import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time

from model import Controller, target_kelvin

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'omarchy/adaptive-tone.json'
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'omarchy/adaptive-tone.json'
DEFAULTS = {
    'minimum_kelvin': 5000, 'maximum_kelvin': 6500,
    'dim_lux': 5, 'bright_lux': 1000, 'smoothing_seconds': 45,
    'maximum_kelvin_per_second': 20, 'poll_seconds': 3,
    'manual_override_seconds': 3600,
}
ERRORS = (OSError, ValueError, RuntimeError, subprocess.SubprocessError)


def validate(config):
    for key in DEFAULTS:
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{key} must be a finite number')
    if not 3500 <= config['minimum_kelvin'] < config['maximum_kelvin'] <= 6500:
        raise ValueError('Kelvin range must satisfy 3500 <= minimum < maximum <= 6500')
    if not 0 <= config['dim_lux'] < config['bright_lux'] <= 200000:
        raise ValueError('Lux thresholds must satisfy 0 <= dim < bright <= 200000')
    if not 1 <= config['poll_seconds'] <= 60:
        raise ValueError('poll_seconds must be between 1 and 60')
    for key in ('smoothing_seconds', 'maximum_kelvin_per_second', 'manual_override_seconds'):
        if not 1 <= config[key] <= 86400:
            raise ValueError(f'{key} must be between 1 and 86400')
    if not isinstance(config.get('automatic', True), bool):
        raise ValueError('automatic must be true or false')
    return config


def read_json(path):
    if path.stat().st_size > 16384:
        raise ValueError('Settings file is too large')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value


def settings():
    config = dict(DEFAULTS, automatic=True)
    if CONFIG.exists():
        supplied = read_json(CONFIG)
        config.update({key: supplied[key] for key in config if key in supplied})
    return validate(config)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def sensor_path():
    for device in sorted(Path('/sys/bus/iio/devices').glob('iio:device*')):
        candidate = device / 'in_illuminance_input'
        if candidate.is_file() and os.access(candidate, os.R_OK):
            return candidate
    raise RuntimeError('No readable IIO illuminance sensor with a lux input was found')


def read_lux(path):
    lux = float(path.read_text().strip())
    if not math.isfinite(lux) or not 0 <= lux <= 200000:
        raise ValueError('Invalid illuminance reading')
    return lux


def command(args, check=True):
    return subprocess.run(args, capture_output=True, text=True, timeout=5, check=check)


def temperature():
    text = command(['hyprctl', 'hyprsunset', 'temperature']).stdout
    match = re.fullmatch(r'\s*(\d+)\s*', text)
    if not match or not 1000 <= int(match[1]) <= 20000:
        raise RuntimeError('Unrecognized hyprsunset temperature response')
    return int(match[1])


def apply_temperature(value):
    command(['hyprctl', 'hyprsunset', 'temperature', str(value)])
    if value == 6500:
        command(['hyprctl', 'hyprsunset', 'identity'])


def refresh_indicator():
    try:
        command(['omarchy-shell', '-q', 'nightlight', 'refresh'], check=False)
    except ERRORS:
        pass


def emit(data):
    print(json.dumps(data, separators=(',', ':')), flush=True)


def acquire_lock():
    directory = Path(os.environ.get('XDG_RUNTIME_DIR', STATE.parent))
    directory.mkdir(parents=True, exist_ok=True)
    handle = (directory / 'omarchy-adaptive-tone.lock').open('a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise RuntimeError('Another Adaptive Tone worker is already running')
    return handle


def control(message, config, controller, actual):
    if not isinstance(message, dict):
        raise ValueError('Expected a control object')
    action = message.get('action')
    updated = config.copy()
    if action == 'pause':
        updated['automatic'] = False
    elif action == 'resume':
        updated['automatic'] = True
    elif action == 'settings':
        values = message.get('values')
        if not isinstance(values, dict) or set(values) - {'minimum_kelvin', 'smoothing_seconds'}:
            raise ValueError('Only dim-room tone and smoothing can be changed from the panel')
        updated.update(values)
    else:
        raise ValueError('Unknown control action')
    validate(updated)
    # Commit settings before changing the live controller.
    write_json(CONFIG, updated)
    config.update(updated)
    if action == 'resume' and controller is not None:
        controller.resume(actual)


def run(sensor_override=None):
    os.umask(0o077)
    lock = acquire_lock()
    config = settings()
    for dependency in ('hyprctl', 'hyprsunset', 'pgrep'):
        if not shutil.which(dependency):
            raise RuntimeError(f'Missing dependency: {dependency}')
    if shutil.which('systemctl'):
        legacy = command(['systemctl', '--user', 'is-active', 'omarchy-adaptive-tone.service'], check=False)
        if legacy.stdout.strip() in ('active', 'activating'):
            raise RuntimeError('Stop the legacy omarchy-adaptive-tone.service before enabling this plugin')
    sensor = Path(sensor_override) if sensor_override else sensor_path()
    read_lux(sensor)
    stopping = False
    child = None
    controller = None
    active_control = None
    pending = b''
    poll = selectors.DefaultSelector()
    poll.register(sys.stdin, selectors.EVENT_READ)
    previous = time.monotonic()
    last_refresh = 0
    try:
        old_state = read_json(STATE)
    except (OSError, ValueError):
        old_state = {}

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping:
            now = time.time()
            elapsed = time.monotonic() - previous
            previous = time.monotonic()
            try:
                try:
                    actual = temperature()
                except ERRORS:
                    if command(['pgrep', '-u', str(os.getuid()), '-x', 'hyprsunset'], check=False).returncode:
                        if child is None or child.poll() is not None:
                            child = subprocess.Popen(['hyprsunset', '--identity'], stdout=sys.stderr, stderr=sys.stderr)
                    raise RuntimeError('Waiting for hyprsunset to connect')
                if controller is None:
                    until = old_state.get('override_until', 0)
                    if not isinstance(until, (int, float)) or not math.isfinite(until):
                        until = 0
                    if actual < config['minimum_kelvin']:
                        until = max(until, now + config['manual_override_seconds'])
                    controller = Controller(config, actual, min(until, now + config['manual_override_seconds']))
                control_error = ''
                if active_control is not None:
                    try:
                        control(active_control, config, controller, actual)
                    except ERRORS as error:
                        control_error = str(error)
                    active_control = None
                sensor_error = ''
                try:
                    lux = read_lux(sensor)
                except (OSError, ValueError) as error:
                    lux = None
                    sensor_error = str(error)
                next_value = controller.step(lux if config['automatic'] else None, actual, now, elapsed)
                if next_value is not None:
                    apply_temperature(next_value)
                    actual = controller.expected = next_value
                if now - last_refresh >= 15:
                    refresh_indicator()
                    last_refresh = now
                mode = 'paused' if not config['automatic'] else ('manual' if now < controller.override_until else 'automatic')
                data = {
                    'updated_at': now, 'mode': mode, 'lux': lux,
                    'target_kelvin': target_kelvin(lux, config) if lux is not None else None,
                    'temperature_kelvin': actual, 'override_until': controller.override_until,
                    'sensor': str(sensor), 'error': sensor_error or control_error,
                    'settings': config.copy(),
                }
                write_json(STATE, data)
                emit(data)
            except ERRORS as error:
                emit({'mode': 'error', 'error': str(error), 'settings': config.copy()})

            deadline = time.monotonic() + config['poll_seconds']
            while not stopping and time.monotonic() < deadline:
                if not poll.select(min(0.2, max(0, deadline - time.monotonic()))):
                    continue
                chunk = os.read(sys.stdin.fileno(), 4096)
                if not chunk:
                    # The owning plugin closed/died: never leave a controller behind.
                    stopping = True
                    break
                pending += chunk
                if len(pending) > 8192:
                    pending = b''
                    emit({'mode': 'error', 'error': 'Control message too large'})
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    try:
                        active_control = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        emit({'mode': 'error', 'error': 'Invalid control message'})
                if active_control is not None:
                    break
    finally:
        poll.close()
        try:
            if controller and temperature() == controller.expected and time.time() >= controller.override_until:
                apply_temperature(6500)
                refresh_indicator()
        except ERRORS:
            pass
        # Leave an owned hyprsunset alive during a manual hold, preserving the user's tint.
        if child is not None and child.poll() is None and (not controller or time.time() >= controller.override_until):
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'preview'])
    parser.add_argument('--sensor', help='Explicit lux input path; default: discover a readable IIO input')
    args = parser.parse_args()
    if args.action == 'preview':
        config = settings()
        sensor = Path(args.sensor) if args.sensor else sensor_path()
        lux = read_lux(sensor)
        emit({'lux': lux, 'sensor': str(sensor), 'target_kelvin': target_kelvin(lux, config), 'settings': config})
    else:
        run(args.sensor)


if __name__ == '__main__':
    try:
        main()
    except ERRORS as error:
        emit({'mode': 'error', 'error': str(error)})
        sys.exit(1)

import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import backend

ROOT = Path(__file__).resolve().parents[1]


class SettingsTests(unittest.TestCase):
    def test_rejects_invalid_numeric_settings(self):
        for value in [True, float('nan'), float('inf'), '5000', None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                backend.validate(dict(backend.DEFAULTS, minimum_kelvin=value))

    def test_control_validation_does_not_mutate_configuration(self):
        config = dict(backend.DEFAULTS, automatic=True)
        with self.assertRaises(ValueError):
            backend.control({'action': 'settings', 'values': {'minimum_kelvin': 9999}}, config, None, 6500)
        self.assertEqual(config['minimum_kelvin'], 5000)

    def test_invalid_sensor_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'lux'
            for value in ['nan', 'inf', '-1', '200001', '<img src=x>']:
                path.write_text(value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    backend.read_lux(path)


class WorkerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        self.sensor = self.home / 'lux'
        self.sensor.write_text('5')
        self.temperature = self.home / 'temperature'
        self.temperature.write_text('6500')
        self.config = self.home / 'config/omarchy/adaptive-tone.json'
        self.config.parent.mkdir(parents=True)
        self.config.write_text(json.dumps(dict(backend.DEFAULTS, poll_seconds=1)))
        fake = '#!' + sys.executable + '\n' + '''
import os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
if name == 'hyprctl':
    path = Path(os.environ['FAKE_TEMPERATURE'])
    if sys.argv[2] == 'temperature':
        if len(sys.argv) > 3: path.write_text(sys.argv[3])
        else: print(path.read_text())
elif name == 'systemctl':
    print('inactive')
    sys.exit(3)
'''
        for name in ('hyprctl', 'hyprsunset', 'systemctl', 'omarchy-shell'):
            path = self.bin / name
            path.write_text(fake)
            path.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / 'config'),
                        XDG_STATE_HOME=str(self.home / 'state'), XDG_RUNTIME_DIR=str(self.home / 'runtime'),
                        PATH=str(self.bin) + os.pathsep + os.environ['PATH'], FAKE_TEMPERATURE=str(self.temperature))
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=8)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream and not stream.closed:
                    stream.close()
        self.temp.cleanup()

    def start(self):
        process = subprocess.Popen([sys.executable, str(ROOT / 'backend.py'), 'run', '--sensor', str(self.sensor)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=self.env)
        self.processes.append(process)
        return process

    def read_until(self, process, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                if not selector.select(0.2):
                    continue
                line = process.stdout.readline()
                if not line:
                    self.fail('Worker exited unexpectedly: ' + process.stderr.read())
                data = json.loads(line)
                if predicate(data):
                    return data
        self.fail('Timed out waiting for worker state')

    def send(self, process, message):
        process.stdin.write(json.dumps(message) + '\n')
        process.stdin.flush()

    def test_controls_persist_and_eof_stops_worker_and_restores_neutral(self):
        process = self.start()
        self.read_until(process, lambda data: data.get('temperature_kelvin', 6500) < 6500)
        self.send(process, {'action': 'pause'})
        paused = self.read_until(process, lambda data: data.get('mode') == 'paused')
        self.assertFalse(json.loads(self.config.read_text())['automatic'])
        self.send(process, {'action': 'settings', 'values': {'minimum_kelvin': 5250, 'smoothing_seconds': 90}})
        self.read_until(process, lambda data: data.get('settings', {}).get('minimum_kelvin') == 5250)
        self.send(process, {'action': 'resume'})
        self.read_until(process, lambda data: data.get('mode') == 'automatic')
        process.stdin.close()
        self.assertEqual(process.wait(timeout=8), 0)
        self.assertEqual(self.temperature.read_text(), '6500')

    def test_manual_override_is_preserved_on_sigterm(self):
        process = self.start()
        self.read_until(process, lambda data: data.get('temperature_kelvin', 6500) < 6500)
        self.temperature.write_text('4000')
        self.read_until(process, lambda data: data.get('mode') == 'manual')
        process.terminate()
        self.assertEqual(process.wait(timeout=8), 0)
        self.assertEqual(self.temperature.read_text(), '4000')

    def test_duplicate_worker_is_rejected(self):
        first = self.start()
        self.read_until(first, lambda data: data.get('mode') == 'automatic')
        second = self.start()
        output, errors = second.communicate(timeout=8)
        self.assertEqual(second.returncode, 1)
        self.assertIn('already running', json.loads(output)['error'])
        self.assertEqual(first.poll(), None)


if __name__ == '__main__':
    unittest.main()

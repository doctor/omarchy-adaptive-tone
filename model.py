"""Pure light-to-tone mapping and transition controller."""

import math

def target_kelvin(lux, config):
    low, high = math.log1p(config['dim_lux']), math.log1p(config['bright_lux'])
    fraction = min(1.0, max(0.0, (math.log1p(lux) - low) / (high - low)))
    return round(config['minimum_kelvin'] + fraction * (config['maximum_kelvin'] - config['minimum_kelvin']))


class Controller:
    def __init__(self, config, actual, override_until=0):
        self.config = config
        self.expected = actual
        self.value = float(actual)
        self.override_until = override_until

    def resume(self, actual):
        self.expected = actual
        self.value = float(actual)
        self.override_until = 0

    def step(self, lux, actual, now, elapsed):
        # The stock button and CLI can keep using hyprsunset directly.
        if actual != self.expected:
            self.resume(actual)
            self.override_until = now + self.config['manual_override_seconds']
        if now < self.override_until or lux is None:
            return None
        target = target_kelvin(lux, self.config)
        elapsed = min(elapsed, self.config['poll_seconds'] * 2)
        delta = (target - self.value) * -math.expm1(-elapsed / self.config['smoothing_seconds'])
        limit = self.config['maximum_kelvin_per_second'] * elapsed
        self.value += min(limit, max(-limit, delta))
        if abs(self.value - target) < 2:
            self.value = float(target)
        next_value = round(self.value)
        changed = abs(next_value - actual) >= 5
        neutral = next_value == 6500 and actual != 6500
        return next_value if changed or neutral else None



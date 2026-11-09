import unittest
import backend as tone


class AdaptiveToneTests(unittest.TestCase):
    def setUp(self):
        self.config = tone.DEFAULTS.copy()

    def test_lux_curve_is_bounded_and_monotonic(self):
        lux_values = [0, 1, 5, 10, 50, 100, 303, 500, 1000, 10000, 200000]
        targets = [tone.target_kelvin(lux, self.config) for lux in lux_values]
        self.assertEqual(targets[0], 5000)
        self.assertEqual(targets[-1], 6500)
        self.assertEqual(targets, sorted(targets))
        self.assertTrue(6000 < tone.target_kelvin(303, self.config) < 6500)

    def test_large_light_change_is_smooth_and_settles(self):
        control = tone.Controller(self.config, 6500)
        actual = 6500
        values = [actual]
        for elapsed in range(3, 303, 3):
            next_value = control.step(0, actual, elapsed, 3)
            if next_value is not None:
                self.assertLessEqual(abs(next_value - actual), 60)
                actual = control.expected = next_value
            values.append(actual)
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertLessEqual(abs(actual - 5000), 10)

    def test_manual_night_choice_holds_then_resumes_gradually(self):
        control = tone.Controller(self.config, 6200)
        self.assertIsNone(control.step(300, 4000, 100, 3))
        self.assertEqual(control.override_until, 3700)
        self.assertIsNone(control.step(1000, 4000, 3699, 3))
        next_value = control.step(1000, 4000, 3701, 3)
        self.assertGreater(next_value, 4000)
        self.assertLessEqual(next_value, 4060)

    def test_daylight_button_and_second_manual_choice_extend_hold(self):
        control = tone.Controller(self.config, 5700)
        self.assertIsNone(control.step(5, 6500, 100, 3))
        self.assertEqual(control.override_until, 3700)
        self.assertIsNone(control.step(5, 4000, 200, 3))
        self.assertEqual(control.override_until, 3800)

    def test_missing_sensor_does_not_change_tone(self):
        control = tone.Controller(self.config, 6000)
        self.assertIsNone(control.step(None, 6000, 100, 3))
        self.assertEqual(control.expected, 6000)

    def test_resume_and_suspend_do_not_jump(self):
        control = tone.Controller(self.config, 4000, override_until=3700)
        control.resume(4000)
        self.assertEqual(control.override_until, 0)
        next_value = control.step(1000, 4000, 200, 5000)
        self.assertLessEqual(next_value - 4000, 120)

    def test_bright_light_eventually_restores_exact_neutral(self):
        control = tone.Controller(self.config, 6496)
        actual = 6496
        for now in range(3, 303, 3):
            next_value = control.step(1000, actual, now, 3)
            if next_value is not None:
                actual = control.expected = next_value
        self.assertEqual(actual, 6500)


if __name__ == '__main__':
    unittest.main()
